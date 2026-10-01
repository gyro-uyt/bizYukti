"""Resident demand: publish, support, share; plus business interest and fulfilment (R1-R3)."""

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import taxonomy
from ..config import settings
from ..db import get_db
from ..events import emit
from ..geo import distance, resolve_locality, within
from ..models import (BusinessProfile, Demand, DemandInterest, DemandSupport, Match, OpportunityArea, Property, User)
from ..ratelimit import limiter
from ..security import current_user, ip_hash, optional_user, require_role, utcnow
from ..serializers import demand_out, match_out
from ..services import demands as svc
from ..services import matching, rewards, trust
from ..services.notify import notify
from ..worker import tasks
from ..worker.queue import enqueue
from .deps import clamp, device_id, get_or_404, throttle

router = APIRouter(prefix="/demands", tags=["demands"])
STATES = ["draft", "published", "growing", "matched", "fulfilled"]


class AssistIn(BaseModel):
    text: str = Field(min_length=2, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class DemandIn(BaseModel):
    text: str = Field(min_length=2, max_length=200, description="What residents want, in their own words")
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = None
    reason: Literal["daily_need", "commute", "students", "family", "other"] = "daily_need"
    reason_note: str | None = Field(default=None, max_length=200)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    publish: bool = True
    skip_duplicate_check: bool = False
    client_lat: float | None = Field(default=None, ge=-90, le=90)
    client_lng: float | None = Field(default=None, ge=-180, le=180)


class DemandPatch(BaseModel):
    text: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    reason: Literal["daily_need", "commute", "students", "family", "other"] | None = None
    reason_note: str | None = Field(default=None, max_length=200)


class SupportIn(BaseModel):
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class InterestIn(BaseModel):
    note: str | None = Field(default=None, max_length=280)


def _center(user: User | None, lat: float | None, lng: float | None) -> tuple[float, float]:
    if lat is not None and lng is not None:
        return lat, lng
    if user and user.home_lat is not None:
        return user.home_lat, user.home_lng
    return settings.default_lat, settings.default_lng


def _my_supports(db: Session, user: User | None, ids: list[uuid.UUID]) -> dict:
    if not user or not ids:
        return {}
    rows = db.execute(select(DemandSupport.demand_id, DemandSupport.status).where(
        DemandSupport.user_id == user.id, DemandSupport.demand_id.in_(ids))).all()
    return {r.demand_id: r.status for r in rows}


def _similar_out(rows) -> list[dict]:
    return [{**demand_out(d, distance_m=dist), "similarity": round(sim, 2)} for d, sim, dist in rows]


def _schedule_recompute(demand_id: uuid.UUID, force: bool = False) -> None:
    if force or limiter.hit(f"recompute-demand:{demand_id}", 1, 30):
        enqueue(tasks.recompute_demand, str(demand_id))


@router.get("")
def list_demands(lat: float | None = Query(default=None, ge=-90, le=90), lng: float | None = Query(default=None, ge=-180, le=180),
                 radius_km: float = Query(default=5, gt=0, le=50), category: str | None = None,
                 q: str | None = Query(default=None, max_length=80),
                 sort: Literal["support", "recent", "near"] = "support",
                 scope: Literal["radius", "city"] = "radius",
                 limit: int = 20, offset: int = 0,
                 user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    clat, clng = _center(user, lat, lng)
    dist = distance("demands", clat, clng).label("d")
    stmt = select(Demand, dist).where(Demand.status.in_(trust.LIVE_STATES), Demand.verification_status != "rejected")
    city = None
    if scope == "city":
        # City-wide ranking: every live request whose area belongs to the city around the given centre.
        city = resolve_locality(db, clat, clng)["city"]
        stmt = stmt.join(OpportunityArea, OpportunityArea.id == Demand.area_id).where(func.lower(OpportunityArea.city) == city.lower())
    else:
        stmt = stmt.where(within("demands", clat, clng, radius_km * 1000))
    if category and category in taxonomy.BY_SLUG:
        stmt = stmt.where(Demand.category == category)
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(Demand.title.ilike(term) | Demand.category.ilike(term) | Demand.locality.ilike(term))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {"support": (Demand.verified_support_count.desc(), dist), "recent": (Demand.published_at.desc(),),
             "near": (dist,)}[sort]
    rows = db.execute(stmt.order_by(*order).limit(clamp(limit, 1, 50)).offset(max(offset, 0))).all()
    mine = _my_supports(db, user, [d.id for d, _ in rows])
    return {"total": total, "center": {"lat": clat, "lng": clng}, "city": city, "items": [
        demand_out(d, distance_m=float(dd), my_support=mine.get(d.id), mine=bool(user and d.author_id == user.id))
        for d, dd in rows]}


@router.post("/assist")
def assist(body: AssistIn, request: Request, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """Step 1 of R2: clean title + suggested category + 'similar request already exists'."""
    throttle(request, "assist", 60, 60, user.id if user else None)
    from ..services import ai

    meta = ai.categorize(body.text)
    cat = taxonomy.get(meta["category"])
    out = {"title": taxonomy.clean_title(body.text), "category": cat.slug, "category_name": cat.name,
           "confidence": meta["confidence"], "why": cat.why, "tags": meta.get("tags", []), "similar": []}
    if body.lat is not None and body.lng is not None:
        out["similar"] = _similar_out(svc.find_similar(db, body.text, body.lat, body.lng, cat.slug))
    return out


@router.post("", status_code=201)
def create(body: DemandIn, request: Request, device: str | None = Depends(device_id),
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    throttle(request, "demand-create", 10, 3600, user.id)
    if body.publish and not body.skip_duplicate_check:
        cat = body.category if body.category in taxonomy.BY_SLUG else taxonomy.classify(body.text)[0]
        similar = [r for r in svc.find_similar(db, body.text, body.lat, body.lng, cat, radius_m=800)
                   if r[1] >= 0.45 or (cat != "other" and r[0].category == cat)]
        if similar:
            raise HTTPException(409, {"code": "duplicate", "message": "A similar request already exists nearby. "
                                      "Support it to add your voice, or publish yours anyway.",
                                      "similar": _similar_out(similar)})
    demand = svc.create_demand(db, user, text_in=body.text, description=body.description, category=body.category,
                               reason=body.reason, reason_note=body.reason_note, lat=body.lat, lng=body.lng,
                               publish=body.publish, device=device, client_lat=body.client_lat,
                               client_lng=body.client_lng)
    emit(db, "demand.created", user.id, "demand", demand.id, ip_hash=ip_hash(request))
    db.commit()
    support = db.scalar(select(DemandSupport).where(DemandSupport.demand_id == demand.id,
                                                    DemandSupport.user_id == user.id))
    if demand.status in trust.LIVE_STATES:
        _schedule_recompute(demand.id, force=True)
    return {"demand": demand_out(demand, my_support=support.status if support else None, mine=True),
            "support": {"status": support.status, "reason": support.reason} if support else None,
            "reward": {"points": rewards.RULES["demand_published"]["points"], "max_points": rewards.DEMAND_MAX_POINTS,
                       "status": "pending"}}


@router.get("/mine")
def mine(user: User = Depends(current_user), db: Session = Depends(get_db)):
    created = db.scalars(select(Demand).where(Demand.author_id == user.id).order_by(Demand.created_at.desc()).limit(100)).all()
    supported = db.execute(select(Demand, DemandSupport.status).join(DemandSupport, DemandSupport.demand_id == Demand.id)
                           .where(DemandSupport.user_id == user.id, Demand.author_id != user.id)
                           .order_by(DemandSupport.created_at.desc()).limit(100)).all()
    counts = _space_counts(db, [d.id for d in created])
    return {
        "created": [{**demand_out(d, mine=True), "matched_spaces": counts.get(d.id, 0)} for d in created],
        "supported": [demand_out(d, my_support=status) for d, status in supported],
    }


_TREND_SQL = text("""
SELECT date_trunc('week', s.created_at) AS wk, COUNT(*) AS n
FROM demand_supports s JOIN demands d ON d.id = s.demand_id
WHERE s.status = 'verified' AND d.status IN ('published', 'growing', 'matched', 'fulfilled')
  AND ST_DWithin(d.geog, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :r)
  AND s.created_at >= now() - make_interval(weeks => :weeks)
GROUP BY wk ORDER BY wk""")


def _weekly(db: Session, lat: float, lng: float, radius_m: float, weeks: int = 8) -> list[dict]:
    counts = {r.wk.date(): int(r.n) for r in db.execute(_TREND_SQL, {"lat": lat, "lng": lng, "r": radius_m, "weeks": weeks})}
    today = utcnow().date()
    start = today - timedelta(days=today.weekday())
    return [{"week": (start - timedelta(weeks=i)).isoformat(), "supporters": counts.get(start - timedelta(weeks=i), 0)}
            for i in range(weeks - 1, -1, -1)]


def _insight(locality: str, cats: list[dict], series: list[dict]) -> str:
    if not cats:
        return f"No one near {locality} has asked for a business yet. Your request could be the first."
    top = cats[0]
    out = f"{top['name']} is the most wanted business near {locality}, backed by {top['supporters']:,} verified neighbours."
    recent = sum(s["supporters"] for s in series[-2:])
    prior = sum(s["supporters"] for s in series[-4:-2])
    if prior and recent > prior:
        out += f" Support grew {round((recent - prior) / prior * 100)}% over the last two weeks."
    elif recent:
        out += f" {recent:,} neighbours added their support in the last two weeks."
    return out


@router.get("/for-you")
def for_you(lat: float | None = Query(default=None, ge=-90, le=90), lng: float | None = Query(default=None, ge=-180, le=180),
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Resident home feed: neighbourhood pulse, charts, explained recommendations and recent wins."""
    clat, clng = _center(user, lat, lng)
    radius = settings.local_radius_km * 1000
    now = utcnow()
    locality = resolve_locality(db, clat, clng)["locality"]
    dist = distance("demands", clat, clng).label("d")
    live = db.execute(select(Demand, dist).where(Demand.status.in_(trust.LIVE_STATES), Demand.verification_status != "rejected",
                                                 within("demands", clat, clng, radius)).order_by(dist).limit(200)).all()

    by_cat: dict[str, dict] = {}
    for d, _ in live:
        c = by_cat.setdefault(d.category, {"category": d.category, "name": taxonomy.get(d.category).name, "supporters": 0, "demands": 0})
        c["supporters"] += d.verified_support_count
        c["demands"] += 1
    cats = sorted(by_cat.values(), key=lambda c: c["supporters"], reverse=True)[:6]
    series = _weekly(db, clat, clng, radius)

    # Recommendations: live requests you haven't backed yet, where your support counts (within the local radius).
    mine = _my_supports(db, user, [d.id for d, _ in live])
    affinity = set(db.scalars(select(Demand.category).join(DemandSupport, DemandSupport.demand_id == Demand.id)
                              .where(DemandSupport.user_id == user.id)).all())
    candidates = [(d, float(dd)) for d, dd in live if d.id not in mine and d.author_id != user.id]
    recent = dict(db.execute(select(DemandSupport.demand_id, func.count(DemandSupport.id)).where(
        DemandSupport.demand_id.in_([d.id for d, _ in candidates]), DemandSupport.status == "verified",
        DemandSupport.created_at >= now - timedelta(days=14)).group_by(DemandSupport.demand_id)).all()) if candidates else {}
    picks = []
    for d, dd in candidates:
        n_recent = int(recent.get(d.id, 0))
        to_verify = max(0, settings.demand_verify_min_supporters + 1 - d.verified_support_count) if not d.verification_status == "verified" else 0
        to_grow = settings.growing_threshold - d.verified_support_count if d.status == "published" else 0
        score = (0.35 * max(0.0, 1 - dd / radius) + 0.25 * min(1.0, n_recent / 20) + 0.2 * (d.category in affinity)
                 + 0.2 * (1.0 if to_verify else 0.6 if 0 < to_grow <= 3 else 0) + 0.1 * taxonomy.demand_strength(d.verified_support_count))
        reasons, tag = [], None
        if to_verify:
            reasons.append(f"Only {to_verify} more {'neighbour' if to_verify == 1 else 'neighbours'} needed to make this verified demand")
            tag = "Help verify"
        elif 0 < to_grow <= 3:
            reasons.append(f"{to_grow} more {'supporter' if to_grow == 1 else 'supporters'} to reach Growing")
            tag = "Almost growing"
        if n_recent >= 3:
            reasons.append(f"{n_recent} neighbours joined in the last two weeks")
            tag = tag or "Trending"
        if d.status == "matched":
            reasons.append("A business is already interested in opening this")
            tag = tag or "Business interested"
        if d.category in affinity:
            reasons.append("Similar to requests you already back")
            tag = tag or "For you"
        # Two strongest signals, then always the distance (it's why the support will count).
        where = "Right in your area" if dd < 100 else f"{matching.fmt_distance(dd)} from you"
        reasons = reasons[:2] + [f"{where}, so your support counts"]
        picks.append((score, d, dd, reasons, tag or "Popular nearby"))
    picks.sort(key=lambda p: p[0], reverse=True)

    opened = db.execute(select(Demand, dist).where(Demand.status == "fulfilled", within("demands", clat, clng, radius * 2),
                                                   Demand.fulfilled_at >= now - timedelta(days=365))
                        .order_by(Demand.fulfilled_at.desc()).limit(3)).all()
    created = db.scalar(select(func.count(Demand.id)).where(Demand.author_id == user.id)) or 0
    backed = db.scalar(select(func.count(DemandSupport.id)).join(Demand, Demand.id == DemandSupport.demand_id).where(
        DemandSupport.user_id == user.id, Demand.author_id != user.id)) or 0
    return {
        "center": {"lat": clat, "lng": clng, "locality": locality, "radius_km": settings.local_radius_km},
        "stats": {"live_requests": len(live), "supporters": sum(d.verified_support_count for d, _ in live),
                  "new_supporters_14d": sum(s["supporters"] for s in series[-2:]),
                  "opened": db.scalar(select(func.count(Demand.id)).where(
                      Demand.status == "fulfilled", within("demands", clat, clng, radius * 2))) or 0},
        "categories": cats,
        "trend": series,
        "insight": _insight(locality, cats, series),
        "recommendations": [{"demand": demand_out(d, distance_m=dd), "reasons": r, "tag": t, "score": round(s, 3)}
                            for s, d, dd, r, t in picks[:4]],
        "opened": [demand_out(d, distance_m=float(dd)) for d, dd in opened],
        "me": {"created": int(created), "supported": int(backed)},
    }


def _space_counts(db: Session, ids: list[uuid.UUID]) -> dict:
    if not ids:
        return {}
    rows = db.execute(select(Match.demand_id, func.count(Match.id)).join(Property, Property.id == Match.property_id)
                      .where(Match.demand_id.in_(ids), Property.status == "published").group_by(Match.demand_id)).all()
    return {r[0]: int(r[1]) for r in rows}


def _timeline(d: Demand) -> list[dict]:
    if d.status in ("expired", "rejected"):
        return [{"state": s, "reached": True} for s in ("draft", "published")] + [{"state": d.status, "reached": True}]
    reached = STATES.index(d.status) if d.status in STATES else 0
    return [{"state": s, "reached": i <= reached} for i, s in enumerate(STATES)]


@router.get("/{demand_id}")
def detail(demand_id: uuid.UUID, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id, "This request doesn't exist or was removed.")
    is_author = bool(user and d.author_id == user.id)
    is_admin = bool(user and "admin" in user.role_names)
    if (d.status in ("draft", "rejected")) and not (is_author or is_admin):
        raise HTTPException(404, "This request doesn't exist or was removed.")
    support = db.scalar(select(DemandSupport).where(DemandSupport.demand_id == d.id,
                                                    DemandSupport.user_id == user.id)) if user else None
    interests = db.execute(select(DemandInterest, BusinessProfile).join(
        BusinessProfile, BusinessProfile.user_id == DemandInterest.user_id, isouter=True)
        .where(DemandInterest.demand_id == d.id).order_by(DemandInterest.created_at)).all()
    matches = db.execute(select(Match, Property).join(Property, Property.id == Match.property_id)
                         .where(Match.demand_id == d.id, Property.status == "published")
                         .order_by(Match.score.desc())).all()
    author = db.get(User, d.author_id) if d.author_id else None
    out = demand_out(d, my_support=support.status if support else None, author=author, mine=is_author,
                     interested=bool(user and any(i.user_id == user.id for i, _ in interests)))
    out.update(
        matched_spaces=len(matches),
        interested_businesses=len(interests),
        spaces=[match_out(m, prop=p) for m, p in matches[:3]],
        businesses=[{"interest_id": str(i.id), "name": b.name if b else "A business",
                     "verified": bool(b and b.verification_status == "verified"),
                     "note": i.note} for i, b in interests] if user else [],
        my_support_reason=support.reason if support else None,
        timeline=_timeline(d),
        share_path=f"/demands/{d.id}",
        reward_hint={"points": rewards.RULES["demand_supported"]["points"]},
    )
    if is_author or is_admin:
        out["private"] = {"risk_score": d.risk_score, "risk_reasons": d.risk_reasons or [],
                          "pending_supporters": d.pending_support_count}
    return out


@router.get("/{demand_id}/spaces")
def spaces(demand_id: uuid.UUID, db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id)
    rows = db.execute(select(Match, Property).join(Property, Property.id == Match.property_id)
                      .where(Match.demand_id == d.id, Property.status == "published").order_by(Match.score.desc())
                      .limit(30)).all()
    return {"items": [match_out(m, prop=p) for m, p in rows]}


@router.patch("/{demand_id}")
def patch(demand_id: uuid.UUID, body: DemandPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id)
    if d.author_id != user.id:
        raise HTTPException(403, "Only the person who posted this can edit it.")
    if body.text is not None:
        if d.status != "draft":
            raise HTTPException(409, "The request itself can't change after publishing. Edit the details instead.")
        d.title = taxonomy.clean_title(body.text)
    if body.description is not None:
        d.description = body.description.strip() or None
    if body.reason is not None:
        d.reason = body.reason
    if body.reason_note is not None:
        d.reason_note = body.reason_note.strip() or None
    d.risk_score, d.risk_reasons = trust.demand_risk(db, user, d.title, d.description)
    db.commit()
    return demand_out(d, mine=True)


@router.post("/{demand_id}/publish")
def publish(demand_id: uuid.UUID, device: str | None = Depends(device_id), user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id)
    if d.author_id != user.id:
        raise HTTPException(403, "Only the person who posted this can publish it.")
    if d.status != "draft":
        raise HTTPException(409, "This request is already published.")
    svc.publish_demand(db, d, user, device)
    db.commit()
    _schedule_recompute(d.id, force=True)
    return demand_out(d, mine=True)


@router.post("/{demand_id}/support")
def support(demand_id: uuid.UUID, request: Request, body: SupportIn | None = None,
            device: str | None = Depends(device_id), user: User = Depends(current_user), db: Session = Depends(get_db)):
    throttle(request, "support", 120, 3600, user.id)
    d = get_or_404(db, Demand, demand_id)
    before = d.verified_support_count
    s = svc.support(db, d, user, device, body.lat if body else None, body.lng if body else None)
    db.commit()
    if d.verified_support_count != before:
        _schedule_recompute(d.id)
    return {"support": {"status": s.status, "reason": s.reason},
            "demand": demand_out(d, my_support=s.status, mine=d.author_id == user.id),
            "reward": {"points": rewards.RULES["demand_supported"]["points"], "status": "pending"}
            if s.status != "rejected" else None}


@router.delete("/{demand_id}/support")
def unsupport(demand_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id)
    svc.withdraw(db, d, user)
    db.commit()
    _schedule_recompute(d.id)
    return {"demand": demand_out(d)}


@router.post("/{demand_id}/share")
def share(demand_id: uuid.UUID, request: Request, user: User | None = Depends(optional_user),
          db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id)
    if limiter.hit(f"share:{d.id}:{user.id if user else ip_hash(request)}", 1, 3600):
        d.share_count += 1
        emit(db, "demand.shared", user.id if user else None, "demand", d.id)
        db.commit()
    return {"url": f"{settings.public_web_url.rstrip('/')}/demands/{d.id}",
            "text": f"{d.verified_support_count} neighbours want {taxonomy.get(d.category).noun} near {d.locality}. "
                    f"Add your support on BizYukti."}


@router.post("/{demand_id}/view")
def view(demand_id: uuid.UUID, request: Request, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id)
    if limiter.hit(f"view:d:{d.id}:{user.id if user else ip_hash(request)}", 1, 1800):
        d.view_count += 1
        emit(db, "demand.viewed", user.id if user else None, "demand", d.id)
        db.commit()
    return {"views": d.view_count}


@router.post("/{demand_id}/interest")
def interest(demand_id: uuid.UUID, body: InterestIn | None = None, user: User = Depends(require_role("business")),
             db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id)
    if d.status not in trust.LIVE_STATES:
        raise HTTPException(409, "This request is no longer open.")
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.user_id == user.id))
    if not profile:
        raise HTTPException(409, "Set up your business profile first.")
    exists = db.scalar(select(DemandInterest).where(DemandInterest.demand_id == d.id, DemandInterest.user_id == user.id))
    if not exists:
        db.add(DemandInterest(demand_id=d.id, user_id=user.id, note=(body.note or "").strip() or None if body else None))
        db.flush()
        trust.evaluate_demand(db, d)
        notify(db, d.author_id, "demand.interest", f"{profile.name} is interested in your request",
               f"{d.title} near {d.locality}", f"/demands/{d.id}")
        emit(db, "demand.interest", user.id, "demand", d.id, {"business": str(profile.id)})
        db.commit()
    return {"demand": demand_out(d, interested=True)}


@router.delete("/{demand_id}/interest")
def withdraw_interest(demand_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id)
    row = db.scalar(select(DemandInterest).where(DemandInterest.demand_id == d.id, DemandInterest.user_id == user.id))
    if row:
        db.delete(row)
        db.flush()
        trust.evaluate_demand(db, d)
        db.commit()
    return {"demand": demand_out(d, interested=False)}


@router.post("/{demand_id}/fulfil")
def fulfil(demand_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id)
    interested = db.scalar(select(DemandInterest.id).where(DemandInterest.demand_id == d.id,
                                                           DemandInterest.user_id == user.id))
    if not (d.author_id == user.id or "admin" in user.role_names or interested):
        raise HTTPException(403, "Only the requester, an interested business or the BizYukti team can mark this opened.")
    svc.fulfil(db, d, user)
    db.commit()
    _schedule_recompute(d.id, force=True)
    return demand_out(d, mine=d.author_id == user.id)


@router.post("/{demand_id}/close")
def close(demand_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id)
    if d.author_id != user.id:
        raise HTTPException(403, "Only the person who posted this can close it.")
    if d.status in ("fulfilled", "expired", "rejected"):
        raise HTTPException(409, "This request is already closed.")
    d.status = "expired"
    emit(db, "demand.closed", user.id, "demand", d.id)
    db.commit()
    _schedule_recompute(d.id, force=True)
    return demand_out(d, mine=True)
