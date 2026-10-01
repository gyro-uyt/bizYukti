"""Demand <-> property matching. Rule-based scoring (PRD: start rule-based, move to
learning-to-rank once interaction data exists). Every score ships with plain-language reasons."""

import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .. import taxonomy
from ..config import settings
from ..geo import distance, haversine_m, within
from ..models import Demand, Match, Property
from ..security import utcnow
from .notify import notify

LIVE_STATES = ("published", "growing", "matched")
MIN_SCORE = 45
STRONG_SCORE = 70


def fmt_distance(meters: float) -> str:
    return f"{round(meters / 10) * 10:.0f} m" if meters < 1000 else f"{meters / 1000:.1f} km"


def cluster_of(demands: list[Demand]) -> dict:
    weights = [max(d.verified_support_count, 1) for d in demands]
    total_w = sum(weights) or 1
    return {
        "supporters": sum(d.verified_support_count for d in demands),
        "demands": len(demands),
        "lat": sum(d.lat * w for d, w in zip(demands, weights)) / total_w,
        "lng": sum(d.lng * w for d, w in zip(demands, weights)) / total_w,
    }


def score_pair(category: str, prop: Property, cluster: dict, dist_to_cluster_m: float) -> dict | None:
    type_fit, size_fit = taxonomy.suitability(category, prop.type, prop.size_sqft)
    if type_fit == 0:
        return None
    radius = settings.match_radius_km * 1000
    strength = taxonomy.demand_strength(cluster["supporters"])
    proximity = max(0.0, 1 - (dist_to_cluster_m / radius) ** 2)
    fit = type_fit * size_fit
    age_days = (utcnow() - prop.last_confirmed_at).days if prop.last_confirmed_at else 999
    freshness = 1.0 if age_days <= 30 else 0.6 if age_days <= 60 else 0.3
    readiness = (1.0 if prop.availability == "now" else 0.6) * 0.7 + freshness * 0.3
    total = 0.35 * strength + 0.25 * proximity + 0.25 * fit + 0.15 * readiness
    if prop.verification_status == "verified":
        total += 0.03
    score = round(min(total, 1.0) * 100)

    cat = taxonomy.get(category)
    kind = taxonomy.PROPERTY_TYPES.get(prop.type, "space")
    n = cluster["supporters"]
    lo, hi = cat.size
    reasons = []
    if n:
        reasons.append(f"{n:,} nearby residents asked for {cat.noun}")
    reasons.append(f"This {kind} is {fmt_distance(dist_to_cluster_m)} from where the requests are")
    if prop.size_sqft:
        size = f"{prop.size_sqft:,.0f} sq ft"
        if size_fit >= 1:
            reasons.append(f"{size} fits a typical {cat.name.lower()} ({lo:,}–{hi:,} sq ft)")
        elif prop.size_sqft < lo:
            reasons.append(f"{size} is compact for a {cat.name.lower()} (usually {lo:,}+ sq ft)")
        else:
            reasons.append(f"{size} is roomy for a {cat.name.lower()} (usually up to {hi:,} sq ft)")
    if prop.availability == "now":
        reasons.append("Available now")
    elif prop.available_from:
        reasons.append(f"Available from {prop.available_from:%d %b %Y}")
    if prop.verification_status == "verified":
        reasons.append("Ownership verified")
    summary = (f"Matched because {n:,} nearby residents requested {cat.noun} and this {kind} is within "
               f"{fmt_distance(dist_to_cluster_m)} of the demand cluster.")
    return {
        "score": score,
        "reasons": reasons,
        "summary": summary,
        "components": {"demand": round(strength, 3), "proximity": round(proximity, 3), "fit": round(fit, 3),
                       "readiness": round(readiness, 3), "cluster_supporters": n,
                       "cluster_lat": cluster["lat"], "cluster_lng": cluster["lng"]},
    }


def recompute_for_property(db: Session, property_id: uuid.UUID, notify_owner: bool = True) -> int:
    prop = db.get(Property, property_id)
    if not prop:
        return 0
    if prop.status != "published" or prop.lat is None or prop.lng is None:
        db.execute(delete(Match).where(Match.property_id == prop.id, Match.status == "suggested"))
        return 0
    radius = settings.match_radius_km * 1000
    rows = db.execute(select(Demand, distance("demands", prop.lat, prop.lng).label("d")).where(
        Demand.status.in_(LIVE_STATES), within("demands", prop.lat, prop.lng, radius))).all()
    by_category: dict[str, list[Demand]] = defaultdict(list)
    for demand, _ in rows:
        by_category[demand.category].append(demand)
    clusters = {c: cluster_of(ds) for c, ds in by_category.items()}

    keep: set[uuid.UUID] = set()
    new_strong = 0
    existing = {m.demand_id: m for m in db.scalars(select(Match).where(Match.property_id == prop.id))}
    for demand, dist in rows:
        cl = clusters[demand.category]
        result = score_pair(demand.category, prop, cl, haversine_m(prop.lat, prop.lng, cl["lat"], cl["lng"]))
        if not result or result["score"] < MIN_SCORE:
            continue
        keep.add(demand.id)
        reasons = [result["summary"], *result["reasons"]]
        stmt = insert(Match).values(
            id=uuid.uuid4(), demand_id=demand.id, property_id=prop.id, score=result["score"],
            distance_m=float(dist), reasons=reasons, components=result["components"],
        ).on_conflict_do_update(
            constraint="uq_match_pair",
            set_={"score": result["score"], "distance_m": float(dist), "reasons": reasons,
                  "components": result["components"], "updated_at": utcnow()},
        )
        db.execute(stmt)
        prior = existing.get(demand.id)
        if result["score"] >= STRONG_SCORE and (not prior or prior.score < STRONG_SCORE):
            new_strong += 1
    stale = [d for d in existing if d not in keep]
    if stale:
        db.execute(delete(Match).where(Match.property_id == prop.id, Match.demand_id.in_(stale),
                                       Match.status == "suggested"))
    if notify_owner and new_strong:
        kind = taxonomy.PROPERTY_TYPES.get(prop.type, "space")
        notify(db, prop.owner_id, "match.created",
               f"{new_strong} new demand match{'es' if new_strong > 1 else ''} for your {kind}",
               "See who nearby is asking and why it fits.", f"/properties/{prop.id}/matches")
    return new_strong


def recompute_for_demand(db: Session, demand_id: uuid.UUID) -> None:
    demand = db.get(Demand, demand_id)
    if not demand:
        return
    if demand.status not in LIVE_STATES:
        db.execute(delete(Match).where(Match.demand_id == demand.id, Match.status == "suggested"))
        return
    radius = settings.match_radius_km * 1000
    ids = db.scalars(select(Property.id).where(Property.status == "published",
                                               within("properties", demand.lat, demand.lng, radius))).all()
    for pid in ids:
        recompute_for_property(db, pid)


def density_label(db: Session, lat: float, lng: float, radius_m: float = 2000) -> tuple[str, int]:
    total = sum(db.scalars(select(Demand.verified_support_count).where(
        Demand.status.in_(LIVE_STATES), within("demands", lat, lng, radius_m))).all())
    return ("High" if total >= 150 else "Medium" if total >= 40 else "Low"), int(total)


def availability_text(prop: Property) -> str:
    if prop.availability == "now":
        return "Available now"
    if prop.available_from and prop.available_from > date.today():
        return f"From {prop.available_from:%d %b}"
    return "Available soon"
