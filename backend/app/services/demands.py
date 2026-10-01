import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .. import taxonomy
from ..events import emit
from ..geo import area_id_for, resolve_locality
from ..models import Demand, DemandSupport, RewardLedger, User, Verification
from ..security import utcnow
from . import ai, rewards, trust

LIVE_STATES = trust.LIVE_STATES

_SIMILAR_SQL = text("""
SELECT d.id,
  similarity(lower(d.title || ' ' || coalesce(d.description, '')), lower(:q)) AS sim,
  ST_Distance(d.geog, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) AS dist
FROM demands d
WHERE d.status IN ('published', 'growing', 'matched')
  AND ST_DWithin(d.geog, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :radius)
  AND d.created_at > now() - interval '180 days'
  AND (d.category = :cat OR similarity(lower(d.title || ' ' || coalesce(d.description, '')), lower(:q)) > 0.3)
  AND (CAST(:exclude AS uuid) IS NULL OR d.id <> CAST(:exclude AS uuid))
ORDER BY (d.category = :cat) DESC, sim DESC, dist ASC
LIMIT :limit""")


def find_similar(db: Session, query: str, lat: float, lng: float, category: str | None = None,
                 exclude: uuid.UUID | None = None, limit: int = 3, radius_m: float = 1500) -> list[tuple[Demand, float, float]]:
    cat = category or taxonomy.classify(query)[0]
    if cat == "other":
        cat = "__none__"
    rows = db.execute(_SIMILAR_SQL, {"q": query, "lat": lat, "lng": lng, "radius": radius_m, "cat": cat,
                                     "exclude": str(exclude) if exclude else None, "limit": limit}).all()
    if not rows:
        return []
    demands = {d.id: d for d in db.scalars(select(Demand).where(Demand.id.in_([r.id for r in rows])))}
    return [(demands[r.id], float(r.sim), float(r.dist)) for r in rows if r.id in demands]


def create_demand(db: Session, author: User, *, text_in: str, description: str | None, category: str | None,
                  reason: str, reason_note: str | None, lat: float, lng: float, publish: bool,
                  device: str | None, client_lat: float | None, client_lng: float | None) -> Demand:
    now = utcnow()
    title = taxonomy.clean_title(text_in)
    if len(title) < 2:
        raise HTTPException(422, "Tell us what you'd like to see, for example 'a pharmacy'.")
    if category and category in taxonomy.BY_SLUG:
        meta = {"category": category, "confidence": 1.0, "tags": [], "source": "user"}
    else:
        meta = ai.categorize(f"{text_in} {description or ''}")
    repeat = db.scalar(select(Demand.id).where(
        Demand.author_id == author.id, func.lower(Demand.title) == title.lower(),
        Demand.status.notin_(("rejected", "expired")), Demand.created_at >= now - timedelta(days=7)))
    if repeat:
        raise HTTPException(409, "You already requested this recently. Share it to gather support instead.")
    loc = resolve_locality(db, lat, lng)
    risk, risk_reasons = trust.demand_risk(db, author, title, description)
    demand = Demand(
        author_id=author.id, title=title, description=(description or "").strip() or None,
        category=meta["category"], tags=meta.get("tags", []), reason=reason,
        reason_note=(reason_note or "").strip() or None, lat=lat, lng=lng, locality=loc["locality"],
        area_id=loc["area_id"] or area_id_for(db, lat, lng), status="published" if publish else "draft",
        risk_score=risk, risk_reasons=risk_reasons,
        ai_meta={k: meta[k] for k in ("confidence", "source")},
        published_at=now if publish else None, expires_at=now + timedelta(days=180),
    )
    vec = ai.embed(f"{title}. {description or ''}")
    if vec:
        demand.embedding = vec
    db.add(demand)
    db.flush()
    if risk >= 0.7:
        db.add(Verification(subject_type="demand", subject_id=demand.id, kind="risk_review",
                            evidence={"reasons": risk_reasons, "risk_score": risk}))
    if publish:
        publish_demand(db, demand, author, device, client_lat, client_lng)
    else:
        emit(db, "demand.drafted", author.id, "demand", demand.id)
    return demand


def publish_demand(db: Session, demand: Demand, author: User, device: str | None,
                   client_lat: float | None = None, client_lng: float | None = None) -> None:
    from ..security import device_hash

    demand.status = "published"
    demand.published_at = demand.published_at or utcnow()
    support = db.scalar(select(DemandSupport).where(DemandSupport.demand_id == demand.id,
                                                    DemandSupport.user_id == author.id))
    if not support:
        support = DemandSupport(demand_id=demand.id, user_id=author.id, device_hash=device_hash(device))
        db.add(support)
        db.flush()
    trust.evaluate_support(db, support, demand, author, client_lat, client_lng)
    rewards.award(db, author.id, "demand_published", "demand", demand.id)
    trust.evaluate_demand(db, demand)
    emit(db, "demand.published", author.id, "demand", demand.id,
         {"category": demand.category, "source": (demand.ai_meta or {}).get("source")})


def support(db: Session, demand: Demand, user: User, device: str | None,
            client_lat: float | None, client_lng: float | None) -> DemandSupport:
    from ..security import device_hash

    if demand.status not in LIVE_STATES:
        raise HTTPException(409, "This request is no longer collecting support.")
    existing = db.scalar(select(DemandSupport).where(DemandSupport.demand_id == demand.id,
                                                     DemandSupport.user_id == user.id))
    if existing:
        return existing
    s = DemandSupport(demand_id=demand.id, user_id=user.id, device_hash=device_hash(device))
    db.add(s)
    db.flush()
    trust.evaluate_support(db, s, demand, user, client_lat, client_lng)
    if s.status != "rejected":
        rewards.award(db, user.id, "demand_supported", "support", s.id)
    demand.last_support_at = utcnow()
    trust.evaluate_demand(db, demand)
    emit(db, "demand.supported", user.id, "demand", demand.id, {"status": s.status})
    return s


def withdraw(db: Session, demand: Demand, user: User) -> None:
    if demand.author_id == user.id:
        raise HTTPException(409, "You created this request. Close it instead of withdrawing support.")
    s = db.scalar(select(DemandSupport).where(DemandSupport.demand_id == demand.id, DemandSupport.user_id == user.id))
    if not s:
        return
    db.execute(delete(RewardLedger).where(RewardLedger.user_id == user.id, RewardLedger.ref_id == s.id,
                                          RewardLedger.status == "pending"))
    db.delete(s)
    db.flush()
    trust.evaluate_demand(db, demand)
    emit(db, "demand.unsupported", user.id, "demand", demand.id)


def fulfil(db: Session, demand: Demand, actor: User) -> None:
    from .notify import notify

    if demand.status not in LIVE_STATES:
        raise HTTPException(409, "Only live requests can be marked as opened.")
    demand.status = "fulfilled"
    demand.fulfilled_at = utcnow()
    if demand.author_id and demand.verification_status == "verified":
        rewards.award(db, demand.author_id, "demand_fulfilled", "demand", demand.id)
    supporters = db.scalars(select(DemandSupport.user_id).where(
        DemandSupport.demand_id == demand.id, DemandSupport.status == "verified",
        DemandSupport.user_id != demand.author_id)).all()
    for uid in supporters:
        rewards.award(db, uid, "supported_fulfilled", "demand", demand.id)
        notify(db, uid, "demand.fulfilled", f"{demand.title} opened near {demand.locality}",
               "Thanks for backing it. You earned points.", f"/demands/{demand.id}")
    emit(db, "outcome.fulfilled", actor.id, "demand", demand.id, {"supporters": len(supporters)})
