"""Incentives. Points are earned into a ledger as `pending`, then settle to `available` only
after the action is validated (anti reward-farming), or are `reversed` if it fails review."""

import secrets
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Demand, DemandSupport, Property, RewardLedger, User
from ..security import utcnow
from .notify import notify

RULES: dict[str, dict] = {
    "demand_published": {"points": 20, "unlock_hours": 48, "label": "Published a request",
                         "pending_note": f"Unlocks once {settings.demand_verify_min_supporters} neighbours verify your request"},
    "demand_supported": {"points": 2, "unlock_hours": 24, "label": "Supported a request", "daily_cap": 5,
                         "pending_note": "Unlocks after your support is verified"},
    "demand_growing": {"points": 30, "unlock_hours": 0, "label": "Your request is growing"},
    "demand_fulfilled": {"points": 100, "unlock_hours": 0, "label": "Your request was fulfilled"},
    "supported_fulfilled": {"points": 10, "unlock_hours": 0, "label": "A request you supported opened"},
    "property_listed": {"points": 25, "unlock_hours": 72, "label": "Listed a space",
                        "pending_note": "Unlocks 3 days after listing if the listing passes checks"},
    "property_verified": {"points": 50, "unlock_hours": 0, "label": "Space verified"},
    "redeem": {"points": 0, "unlock_hours": 0, "label": "Redeemed"},
}
DEMAND_MAX_POINTS = RULES["demand_published"]["points"] + RULES["demand_growing"]["points"] + RULES["demand_fulfilled"]["points"]

TIERS = [("Neighbour", 0), ("Local voice", 250), ("Local champion", 750), ("Locality hero", 2000)]

OFFERS = [
    {"id": "partner-coffee", "title": "Free coffee at a partner café", "points": 150, "kind": "partner",
     "detail": "Show the code at any participating café."},
    {"id": "featured-7d", "title": "Featured listing for 7 days", "points": 300, "kind": "fee_discount",
     "detail": "Your space appears first in matching areas."},
    {"id": "brief-50", "title": "50% off a market brief", "points": 400, "kind": "fee_discount",
     "detail": "For businesses planning a new outlet."},
    {"id": "voucher-100", "title": "₹100 local shop voucher", "points": 500, "kind": "voucher",
     "detail": "Spend at participating local stores."},
]
_OFFER_BY_ID = {o["id"]: o for o in OFFERS}


def award(db: Session, user_id: uuid.UUID, action: str, ref_type: str | None, ref_id: uuid.UUID | None,
          available_now: bool = False) -> RewardLedger | None:
    rule = RULES[action]
    now = utcnow()
    if db.scalar(select(RewardLedger.id).where(RewardLedger.user_id == user_id, RewardLedger.action == action,
                                               RewardLedger.ref_id == ref_id)):
        return None
    cap = rule.get("daily_cap")
    if cap:
        today = db.scalar(select(func.count(RewardLedger.id)).where(
            RewardLedger.user_id == user_id, RewardLedger.action == action,
            RewardLedger.created_at >= now - timedelta(hours=24)))
        if today >= cap:
            return None
    pending = not available_now and rule["unlock_hours"] > 0
    entry = RewardLedger(
        user_id=user_id, action=action, points=rule["points"], ref_type=ref_type, ref_id=ref_id,
        status="pending" if pending else "available",
        note=rule.get("pending_note") if pending else None,
        expected_unlock_at=now + timedelta(hours=rule["unlock_hours"]) if pending else None,
        settled_at=None if pending else now,
    )
    try:
        with db.begin_nested():
            db.add(entry)
    except IntegrityError:
        return None
    return entry


def _decide(db: Session, entry: RewardLedger) -> str:
    if entry.ref_type == "demand" and entry.ref_id:
        d = db.get(Demand, entry.ref_id)
        if not d or d.status == "rejected" or d.verification_status == "rejected":
            return "reversed"
        return "available" if d.verification_status == "verified" else "pending"
    if entry.ref_type == "support" and entry.ref_id:
        s = db.get(DemandSupport, entry.ref_id)
        if not s or s.status == "rejected":
            return "reversed"
        return "available" if s.status == "verified" else "pending"
    if entry.ref_type == "property" and entry.ref_id:
        p = db.get(Property, entry.ref_id)
        if not p or p.status == "rejected" or p.verification_status == "rejected":
            return "reversed"
        return "available" if p.status in ("published", "paused") and p.quality_score >= 60 else "pending"
    return "available"


def settle(db: Session, user_id: uuid.UUID | None = None) -> int:
    """Moves due pending entries to available/reversed. Safe to run repeatedly."""
    now = utcnow()
    q = select(RewardLedger).where(RewardLedger.status == "pending", RewardLedger.expected_unlock_at <= now)
    if user_id:
        q = q.where(RewardLedger.user_id == user_id)
    changed = 0
    for entry in db.scalars(q.with_for_update(skip_locked=True)).all():
        outcome = _decide(db, entry)
        if outcome == "pending":
            continue
        entry.status, entry.settled_at = outcome, now
        entry.note = None if outcome == "available" else "Reversed because the action didn't pass verification"
        if outcome == "available":
            notify(db, entry.user_id, "reward.available", f"{entry.points} points unlocked",
                   RULES[entry.action]["label"], "/rewards")
        changed += 1
    return changed


def _tier(lifetime: int) -> dict:
    current, nxt = TIERS[0], None
    for i, (name, threshold) in enumerate(TIERS):
        if lifetime >= threshold:
            current = (name, threshold)
            nxt = TIERS[i + 1] if i + 1 < len(TIERS) else None
    return {"name": current[0], "next_name": nxt[0] if nxt else None, "next_at": nxt[1] if nxt else None,
            "progress": 1.0 if not nxt else round((lifetime - current[1]) / (nxt[1] - current[1]), 3)}


def summary(db: Session, user: User) -> dict:
    settle(db, user.id)
    db.commit()
    rows = db.execute(select(RewardLedger.status, func.coalesce(func.sum(RewardLedger.points), 0))
                      .where(RewardLedger.user_id == user.id).group_by(RewardLedger.status)).all()
    totals = {status: int(total) for status, total in rows}
    lifetime = int(db.scalar(select(func.coalesce(func.sum(RewardLedger.points), 0)).where(
        RewardLedger.user_id == user.id, RewardLedger.status == "available", RewardLedger.points > 0)) or 0)
    entries = db.scalars(select(RewardLedger).where(RewardLedger.user_id == user.id)
                         .order_by(RewardLedger.created_at.desc()).limit(60)).all()
    balance = totals.get("available", 0)
    return {
        "balance": balance,
        "pending": totals.get("pending", 0),
        "lifetime": lifetime,
        "tier": _tier(lifetime),
        "entries": [{
            "id": str(e.id), "action": e.action, "label": RULES.get(e.action, {}).get("label", e.action),
            "points": e.points, "status": e.status, "note": e.note, "voucher_code": e.voucher_code,
            "ref_type": e.ref_type, "ref_id": str(e.ref_id) if e.ref_id else None,
            "expected_unlock_at": e.expected_unlock_at.isoformat() if e.expected_unlock_at else None,
            "created_at": e.created_at.isoformat(),
        } for e in entries],
        "offers": [{**o, "affordable": balance >= o["points"]} for o in OFFERS],
        "rules": {k: {"points": v["points"], "label": v["label"]} for k, v in RULES.items() if k != "redeem"},
    }


def redeem(db: Session, user: User, offer_id: str) -> RewardLedger:
    offer = _OFFER_BY_ID.get(offer_id)
    if not offer:
        raise HTTPException(404, "That reward isn't available.")
    db.execute(select(User.id).where(User.id == user.id).with_for_update())  # serialise redemptions per user
    balance = int(db.scalar(select(func.coalesce(func.sum(RewardLedger.points), 0)).where(
        RewardLedger.user_id == user.id, RewardLedger.status == "available")) or 0)
    if balance < offer["points"]:
        raise HTTPException(409, f"You need {offer['points'] - balance} more points for this reward.")
    entry = RewardLedger(user_id=user.id, action="redeem", points=-offer["points"], status="available",
                         ref_type="offer", note=offer["title"], settled_at=utcnow(),
                         voucher_code="BY-" + secrets.token_hex(4).upper())
    db.add(entry)
    return entry
