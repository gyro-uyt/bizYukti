"""Anti-abuse and verification rules (PRD section 11).
Supports are verified only when the supporter is identity-verified, local to the demand,
on a device not already used for this demand, and within normal activity velocity."""

import re
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..events import emit
from ..geo import haversine_m
from ..models import Demand, DemandInterest, DemandSupport, User, Verification
from ..security import utcnow
from . import rewards
from .notify import notify

LIVE_STATES = ("published", "growing", "matched")
_SPAM = re.compile(r"(https?://|www\.|\b\d{10}\b|whatsapp|telegram|t\.me/)", re.IGNORECASE)


def evaluate_support(db: Session, support: DemandSupport, demand: Demand, user: User,
                     client_lat: float | None = None, client_lng: float | None = None) -> None:
    now = utcnow()
    status, reason = "verified", None
    ref = None
    if user.home_lat is not None and user.home_lng is not None:
        ref = (user.home_lat, user.home_lng)
    elif client_lat is not None and client_lng is not None:
        ref = (client_lat, client_lng)

    if user.status != "active":
        status, reason = "rejected", "Account suspended"
    elif not user.identity_verified:
        status, reason = "pending", "Verify your phone or email to count"
    elif ref is None:
        status, reason = "pending", "Set your home locality to count"
    else:
        support.distance_m = haversine_m(ref[0], ref[1], demand.lat, demand.lng)
        if support.distance_m > settings.local_radius_km * 1000:
            status, reason = "rejected", f"Only residents within {settings.local_radius_km:g} km are counted"

    if status == "verified" and support.device_hash:
        reused = db.scalar(select(DemandSupport.id).where(
            DemandSupport.demand_id == demand.id, DemandSupport.device_hash == support.device_hash,
            DemandSupport.user_id != user.id, DemandSupport.status == "verified").limit(1))
        if reused:
            status, reason = "rejected", "This device already supported this request"

    if status == "verified":
        recent = db.scalar(select(func.count(DemandSupport.id)).where(
            DemandSupport.user_id == user.id, DemandSupport.created_at >= now - timedelta(hours=1)))
        if recent > settings.support_hourly_limit:
            status, reason = "pending", "Held for review: unusual activity"
            db.add(Verification(subject_type="support", subject_id=support.id, kind="risk_review",
                                evidence={"supports_last_hour": recent, "user_id": str(user.id)}))

    support.status, support.reason = status, reason
    support.verified_at = now if status == "verified" else None


def recount(db: Session, demand: Demand) -> None:
    rows = db.execute(select(DemandSupport.status, func.count(DemandSupport.id))
                      .where(DemandSupport.demand_id == demand.id).group_by(DemandSupport.status)).all()
    counts = {s: int(n) for s, n in rows}
    demand.verified_support_count = counts.get("verified", 0)
    demand.pending_support_count = counts.get("pending", 0)
    demand.support_count = demand.verified_support_count + demand.pending_support_count


def evaluate_demand(db: Session, demand: Demand) -> None:
    """Verification promotion + state machine: published -> growing -> matched."""
    if demand.status not in LIVE_STATES:
        return
    db.flush()
    recount(db, demand)
    if demand.verification_status == "pending" and demand.risk_score < 0.7 and demand.author_id:
        author = db.get(User, demand.author_id)
        author_ok = db.scalar(select(DemandSupport.id).where(
            DemandSupport.demand_id == demand.id, DemandSupport.user_id == demand.author_id,
            DemandSupport.status == "verified"))
        others = db.scalar(select(func.count(DemandSupport.id)).where(
            DemandSupport.demand_id == demand.id, DemandSupport.user_id != demand.author_id,
            DemandSupport.status == "verified"))
        if author and author.identity_verified and author_ok and others >= settings.demand_verify_min_supporters:
            demand.verification_status = "verified"
            emit(db, "demand.verified", subject_type="demand", subject_id=demand.id)
            notify(db, demand.author_id, "demand.verified", "Your request is now verified local demand",
                   f"{demand.title} near {demand.locality}", f"/demands/{demand.id}")

    previous = demand.status
    interests = db.scalar(select(func.count(DemandInterest.id)).where(DemandInterest.demand_id == demand.id))
    if interests:
        demand.status = "matched"
    elif demand.verified_support_count >= settings.growing_threshold:
        demand.status = "growing"
    else:
        demand.status = "published"
    if demand.status != previous:
        emit(db, f"demand.{demand.status}", subject_type="demand", subject_id=demand.id, data={"from": previous})
    if demand.status in ("growing", "matched") and demand.author_id and demand.verification_status == "verified":
        if rewards.award(db, demand.author_id, "demand_growing", "demand", demand.id):
            notify(db, demand.author_id, "demand.growing", f"{demand.verified_support_count} neighbours back your request",
                   "You earned growth points.", f"/demands/{demand.id}")


def demand_risk(db: Session, author: User, title: str, description: str | None) -> tuple[float, list[str]]:
    score, reasons = 0.0, []
    now = utcnow()
    if author.created_at and author.created_at > now - timedelta(hours=1):
        score += 0.2
        reasons.append("New account")
    recent = db.scalar(select(func.count(Demand.id)).where(
        Demand.author_id == author.id, Demand.created_at >= now - timedelta(hours=24)))
    if recent >= 5:
        score += 0.5
        reasons.append("Many requests in 24 hours")
    text = f"{title} {description or ''}"
    if _SPAM.search(text):
        score += 0.5
        reasons.append("Contains links or contact details")
    if len(title.strip()) < 4:
        score += 0.3
        reasons.append("Very short request")
    return round(min(score, 1.0), 2), reasons


def reevaluate_user_supports(db: Session, user: User) -> None:
    """After a user sets their home locality, their pending supports can be verified."""
    pending = db.scalars(select(DemandSupport).where(
        DemandSupport.user_id == user.id, DemandSupport.status == "pending",
        DemandSupport.reason != "Held for review: unusual activity")).all()
    for s in pending:
        demand = db.get(Demand, s.demand_id)
        if demand:
            evaluate_support(db, s, demand, user)
            evaluate_demand(db, demand)
