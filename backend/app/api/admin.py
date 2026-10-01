"""A1 admin review: verification queue, moderation and the PRD's KPI dashboard.
Risk is handled here so the public product stays simple."""

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..db import get_db
from ..events import emit
from ..models import (AuditEvent, BusinessProfile, Demand, DemandSupport, Property, User, Verification)
from ..security import require_role, utcnow
from ..serializers import business_out, demand_out, iso, property_out
from ..services import rewards, trust
from ..services.notify import notify
from ..storage import get_private_storage
from ..worker import tasks
from ..worker.queue import enqueue
from .deps import get_or_404

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_role("admin")


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=240)


class ModerateIn(BaseModel):
    action: Literal["verify", "reject", "restore"]
    reason: str | None = Field(default=None, max_length=240)


class SuspendIn(BaseModel):
    suspended: bool
    reason: str | None = Field(default=None, max_length=240)


def _subject(db: Session, v: Verification) -> dict | None:
    if v.subject_type == "demand":
        d = db.get(Demand, v.subject_id)
        return {"demand": {**demand_out(d), "risk_score": d.risk_score, "risk_reasons": d.risk_reasons}} if d else None
    if v.subject_type == "property":
        p = db.get(Property, v.subject_id)
        return {"property": property_out(p, private=True)} if p else None
    if v.subject_type == "business":
        b = db.get(BusinessProfile, v.subject_id)
        return {"business": business_out(b)} if b else None
    if v.subject_type == "support":
        s = db.get(DemandSupport, v.subject_id)
        if not s:
            return None
        d = db.get(Demand, s.demand_id)
        return {"support": {"id": str(s.id), "status": s.status, "reason": s.reason, "distance_m": s.distance_m},
                "demand": demand_out(d) if d else None}
    return None


@router.get("/queue")
def queue(status: Literal["pending", "approved", "rejected"] = "pending", subject_type: str | None = None,
          _: User = Depends(admin_only), db: Session = Depends(get_db)):
    stmt = select(Verification).where(Verification.status == status)
    if subject_type:
        stmt = stmt.where(Verification.subject_type == subject_type)
    rows = db.scalars(stmt.order_by(Verification.created_at.asc() if status == "pending" else Verification.reviewed_at.desc())
                      .limit(100)).all()
    counts = dict(db.execute(select(Verification.subject_type, func.count(Verification.id))
                             .where(Verification.status == "pending").group_by(Verification.subject_type)).all())
    return {"counts": counts, "items": [{
        "id": str(v.id), "subject_type": v.subject_type, "subject_id": str(v.subject_id), "kind": v.kind,
        "status": v.status, "reason": v.reason, "created_at": iso(v.created_at), "reviewed_at": iso(v.reviewed_at),
        "evidence": {k: val for k, val in (v.evidence or {}).items() if k != "file_key"},
        "has_document": bool((v.evidence or {}).get("file_key")), "subject": _subject(db, v),
    } for v in rows]}


@router.get("/verifications/{verification_id}/document")
def document(verification_id: uuid.UUID, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    v = get_or_404(db, Verification, verification_id)
    key = (v.evidence or {}).get("file_key")
    if not key:
        raise HTTPException(404, "No document attached.")
    return Response(get_private_storage().read(key), media_type=v.evidence.get("content_type", "application/octet-stream"),
                    headers={"Cache-Control": "no-store", "Content-Disposition": "inline"})


@router.post("/verifications/{verification_id}/decide")
def decide(verification_id: uuid.UUID, body: DecisionIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    v = get_or_404(db, Verification, verification_id)
    if v.status != "pending":
        raise HTTPException(409, "Already reviewed.")
    approve = body.decision == "approve"
    v.status, v.reviewed_by, v.reviewed_at, v.reason = ("approved" if approve else "rejected"), admin.id, utcnow(), body.reason
    recompute: tuple | None = None
    if v.subject_type == "support":
        s = db.get(DemandSupport, v.subject_id)
        if s:
            s.status, s.reason = ("verified", None) if approve else ("rejected", body.reason or "Didn't pass review")
            s.verified_at = utcnow() if approve else None
            d = db.get(Demand, s.demand_id)
            if d:
                trust.evaluate_demand(db, d)
                recompute = (tasks.recompute_demand, str(d.id))
    elif v.subject_type == "demand":
        d = db.get(Demand, v.subject_id)
        if d:
            if approve:
                d.risk_score = min(d.risk_score, 0.4)
                trust.evaluate_demand(db, d)
            else:
                d.status, d.verification_status = "rejected", "rejected"
                notify(db, d.author_id, "demand.rejected", "Your request was removed",
                       body.reason or "It didn't meet our community guidelines.", "/demands/mine")
            recompute = (tasks.recompute_demand, str(d.id))
    elif v.subject_type == "property":
        p = db.get(Property, v.subject_id)
        if p:
            if approve:
                p.verification_status, p.verification_level = "verified", "documents"
                rewards.award(db, p.owner_id, "property_verified", "property", p.id)
                notify(db, p.owner_id, "property.verified", "Your space is now verified",
                       "Verified spaces rank higher in matches.", f"/properties/{p.id}")
            else:
                p.verification_status = "unverified"
                notify(db, p.owner_id, "property.verification_failed", "We couldn't verify your documents",
                       body.reason or "Upload a clearer copy and try again.", f"/properties/{p.id}/edit")
            recompute = (tasks.recompute_property, str(p.id))
    elif v.subject_type == "business":
        b = db.get(BusinessProfile, v.subject_id)
        if b:
            b.verification_status = "verified" if approve else "unverified"
            notify(db, b.user_id, "business.verification", "Your business is verified" if approve else
                   "We couldn't verify your business", body.reason or None, "/profile")
    emit(db, f"{v.subject_type}.{'verified' if approve else 'rejected'}", admin.id, v.subject_type, v.subject_id,
         {"verification_id": str(v.id), "reason": body.reason})
    db.commit()
    if recompute:
        enqueue(*recompute)
    return {"id": str(v.id), "status": v.status}


@router.post("/demands/{demand_id}/moderate")
def moderate_demand(demand_id: uuid.UUID, body: ModerateIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    d = get_or_404(db, Demand, demand_id)
    if body.action == "reject":
        d.status, d.verification_status = "rejected", "rejected"
        notify(db, d.author_id, "demand.rejected", "Your request was removed",
               body.reason or "It didn't meet our community guidelines.", "/demands/mine")
    elif body.action == "verify":
        d.verification_status = "verified"
        d.risk_score = min(d.risk_score, 0.4)
        trust.evaluate_demand(db, d)
    else:
        d.status, d.verification_status = "published", "pending"
        trust.evaluate_demand(db, d)
    emit(db, f"admin.demand.{body.action}", admin.id, "demand", d.id, {"reason": body.reason})
    db.commit()
    enqueue(tasks.recompute_demand, str(d.id))
    return demand_out(d)


@router.post("/properties/{property_id}/moderate")
def moderate_property(property_id: uuid.UUID, body: ModerateIn, admin: User = Depends(admin_only),
                      db: Session = Depends(get_db)):
    p = get_or_404(db, Property, property_id)
    if body.action == "reject":
        p.status = "rejected"
        notify(db, p.owner_id, "property.rejected", "Your listing was removed",
               body.reason or "It didn't meet our listing guidelines.", "/home")
    elif body.action == "verify":
        p.verification_status, p.verification_level = "verified", "documents"
    else:
        p.status = "paused"
    emit(db, f"admin.property.{body.action}", admin.id, "property", p.id, {"reason": body.reason})
    db.commit()
    enqueue(tasks.recompute_property, str(p.id))
    return property_out(p, private=True)


@router.post("/users/{user_id}/suspend")
def suspend(user_id: uuid.UUID, body: SuspendIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = get_or_404(db, User, user_id)
    if u.id == admin.id:
        raise HTTPException(409, "You can't suspend yourself.")
    u.status = "suspended" if body.suspended else "active"
    emit(db, "admin.user.suspend" if body.suspended else "admin.user.restore", admin.id, "user", u.id,
         {"reason": body.reason})
    db.commit()
    return {"id": str(u.id), "status": u.status}


def _rate(num: float, den: float) -> float | None:
    return round(num / den, 3) if den else None


@router.get("/stats")
def stats(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    """PRD section 14 KPIs + the north star (verified local opportunities)."""
    now = utcnow()
    q = lambda sql, **p: db.execute(text(sql), p).scalar() or 0  # noqa: E731
    demands_total = q("SELECT count(*) FROM demands")
    demands_published = q("SELECT count(*) FROM demands WHERE published_at IS NOT NULL")
    supports = q("SELECT count(*) FROM demand_supports")
    supports_verified = q("SELECT count(*) FROM demand_supports WHERE status = 'verified'")
    live = q("SELECT count(*) FROM demands WHERE status IN ('published','growing','matched')")
    with_interest = q("""SELECT count(DISTINCT d.id) FROM demands d WHERE d.published_at IS NOT NULL AND (
        EXISTS (SELECT 1 FROM demand_interests i WHERE i.demand_id = d.id) OR
        EXISTS (SELECT 1 FROM inquiries q WHERE q.demand_id = d.id))""")
    props_total = q("SELECT count(*) FROM properties")
    props_published = q("SELECT count(*) FROM properties WHERE status = 'published'")
    props_fresh = q("SELECT count(*) FROM properties WHERE status = 'published' AND last_confirmed_at > now() - interval '30 days'")
    matches = q("SELECT count(*) FROM matches")
    matches_contacted = q("SELECT count(*) FROM matches WHERE status = 'contacted'")
    hours_to_interest = db.execute(text("""
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (fi - d.published_at)) / 3600)
        FROM demands d JOIN LATERAL (SELECT min(created_at) AS fi FROM demand_interests i WHERE i.demand_id = d.id) x ON x.fi IS NOT NULL
        WHERE d.published_at IS NOT NULL""")).scalar()
    rewards_total = q("SELECT count(*) FROM reward_ledger WHERE action <> 'redeem'")
    rewards_reversed = q("SELECT count(*) FROM reward_ledger WHERE status = 'reversed'")
    rewards_available = q("SELECT count(*) FROM reward_ledger WHERE status = 'available' AND action <> 'redeem'")
    retention = db.execute(text("""
        SELECT r.role, count(DISTINCT u.id) AS cohort,
               count(DISTINCT u.id) FILTER (WHERE u.last_seen_at >= u.created_at + interval '30 days') AS retained
        FROM users u JOIN user_roles r ON r.user_id = u.id
        WHERE u.created_at < now() - interval '30 days' AND r.role <> 'admin'
        GROUP BY r.role""")).all()
    north_star = q("""
        SELECT count(DISTINCT d.id) FROM demands d
        WHERE d.verification_status = 'verified' AND d.status IN ('published','growing','matched','fulfilled')
          AND EXISTS (SELECT 1 FROM matches m JOIN properties p ON p.id = m.property_id
                      WHERE m.demand_id = d.id AND p.status = 'published')
          AND (EXISTS (SELECT 1 FROM demand_interests i WHERE i.demand_id = d.id AND i.created_at > now() - interval '90 days')
               OR EXISTS (SELECT 1 FROM inquiries q WHERE q.demand_id = d.id AND q.created_at > now() - interval '90 days'))""")
    week = db.execute(select(AuditEvent.name, func.count(AuditEvent.id)).where(
        AuditEvent.created_at >= now - timedelta(days=7)).group_by(AuditEvent.name)
        .order_by(func.count(AuditEvent.id).desc()).limit(20)).all()
    return {
        "north_star": {"label": "Verified local opportunities", "value": int(north_star),
                       "definition": "Verified demand + an available matched space + a business action within 90 days"},
        "kpis": [
            {"key": "publish_completion", "label": "Demand publish completion", "value": _rate(demands_published, demands_total)},
            {"key": "verified_support_rate", "label": "Verified support rate", "value": _rate(supports_verified, supports)},
            {"key": "demand_to_inquiry", "label": "Demand to business interest", "value": _rate(with_interest, demands_published)},
            {"key": "listing_completion", "label": "Listing completion", "value": _rate(props_published, props_total)},
            {"key": "listing_freshness", "label": "Listings confirmed in 30 days", "value": _rate(props_fresh, props_published)},
            {"key": "match_to_inquiry", "label": "Match to contact", "value": _rate(matches_contacted, matches)},
            {"key": "hours_to_interest", "label": "Median hours to first business interest",
             "value": round(float(hours_to_interest), 1) if hours_to_interest is not None else None, "unit": "hours"},
            {"key": "reward_abuse", "label": "Rewards reversed", "value": _rate(rewards_reversed, rewards_total)},
            {"key": "reward_completion", "label": "Rewards verified and unlocked", "value": _rate(rewards_available, rewards_total)},
        ],
        "retention_30d": [{"role": r.role, "cohort": int(r.cohort), "rate": _rate(r.retained, r.cohort)} for r in retention],
        "totals": {"demands": int(demands_total), "live_demands": int(live), "supports": int(supports),
                   "properties": int(props_total), "published_properties": int(props_published), "matches": int(matches),
                   "users": int(q("SELECT count(*) FROM users"))},
        "events_7d": [{"name": n, "count": int(c)} for n, c in week],
    }
