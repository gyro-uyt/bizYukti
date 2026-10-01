"""Background jobs. Each opens its own session and commits its own work."""

import logging
import uuid
from datetime import timedelta

from sqlalchemy import or_, select

from ..config import settings
from ..db import SessionLocal
from ..models import Demand, Property
from ..security import utcnow
from ..services import matching, rewards
from ..services.notify import notify

log = logging.getLogger("bizyukti.tasks")


def recompute_demand(demand_id: str) -> None:
    with SessionLocal() as db:
        matching.recompute_for_demand(db, uuid.UUID(demand_id))
        db.commit()


def recompute_property(property_id: str) -> None:
    with SessionLocal() as db:
        matching.recompute_for_property(db, uuid.UUID(property_id))
        db.commit()


def recompute_all() -> int:
    with SessionLocal() as db:
        ids = db.scalars(select(Property.id).where(Property.status == "published")).all()
        for pid in ids:
            matching.recompute_for_property(db, pid, notify_owner=False)
        db.commit()
        return len(ids)


def settle_rewards() -> int:
    with SessionLocal() as db:
        n = rewards.settle(db)
        db.commit()
        return n


def expire_demands() -> int:
    now = utcnow()
    with SessionLocal() as db:
        rows = db.scalars(select(Demand).where(
            Demand.status.in_(("published", "growing")),
            or_(Demand.expires_at < now,
                (Demand.verified_support_count < settings.growing_threshold)
                & (Demand.published_at < now - timedelta(days=90))
                & or_(Demand.last_support_at.is_(None), Demand.last_support_at < now - timedelta(days=60))),
        )).all()
        for d in rows:
            d.status = "expired"
            notify(db, d.author_id, "demand.expired", f"Your request for {d.title.lower()} expired",
                   "Requests close after a long quiet period. You can post it again any time.", f"/demands/{d.id}")
        db.commit()
        return len(rows)


def freshness_sweep() -> int:
    """PRD: prompt owners to confirm availability; pause listings that go stale."""
    now = utcnow()
    touched = 0
    with SessionLocal() as db:
        rows = db.scalars(select(Property).where(Property.status == "published",
                                                 Property.last_confirmed_at < now - timedelta(days=30))).all()
        for p in rows:
            age = (now - p.last_confirmed_at).days
            if age > 60:
                p.status = "paused"
                notify(db, p.owner_id, "property.paused", "We paused a listing that wasn't confirmed",
                       "Confirm it's still available to show it to businesses again.", f"/properties/{p.id}/edit")
                touched += 1
            elif not p.stale_notified_at or p.stale_notified_at < now - timedelta(days=7):
                p.stale_notified_at = now
                notify(db, p.owner_id, "property.stale", "Is your space still available?",
                       "Confirm in one tap to keep it visible.", f"/properties/{p.id}/edit")
                touched += 1
        db.commit()
    return touched
