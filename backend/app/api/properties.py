"""Property owners: list a space with smart assists, see demand matches (P1-P3).
Businesses and residents: browse available spaces."""

import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import taxonomy
from ..config import settings
from ..db import get_db
from ..events import emit
from ..geo import distance, resolve_locality, within
from ..models import (BusinessProfile, Demand, DemandInterest, Inquiry, Match, Property, PropertyMedia, User,
                      UserRole, Verification)
from ..ratelimit import limiter
from ..security import current_user, ip_hash, optional_user, utcnow
from ..serializers import demand_out, match_out, property_out
from ..services import matching, media, rewards
from ..services.notify import notify
from ..storage import get_private_storage, get_storage
from ..worker import tasks
from ..worker.queue import enqueue
from .deps import clamp, get_or_404, throttle

router = APIRouter(prefix="/properties", tags=["properties"])
UNIT_TO_SQFT = {"sqft": 1.0, "sqm": 10.7639, "sqyd": 9.0}
MAX_PHOTOS = 8


class PropertyIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    type: Literal["shop", "office", "land", "warehouse", "other"] | None = None
    size_value: float | None = Field(default=None, gt=0, le=10_000_000)
    size_unit: Literal["sqft", "sqm", "sqyd"] | None = None
    price_type: Literal["rent", "sale"] | None = None
    price_amount: int | None = Field(default=None, ge=0, le=100_000_000_000)
    price_negotiable: bool | None = None
    availability: Literal["now", "future"] | None = None
    available_from: date | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = Field(default=None, max_length=240)
    description: str | None = Field(default=None, max_length=2000)
    amenities: list[str] | None = Field(default=None, max_length=12)


class SuggestIn(BaseModel):
    size_value: float | None = Field(default=None, gt=0)
    size_unit: Literal["sqft", "sqm", "sqyd"] = "sqft"
    description: str | None = Field(default=None, max_length=2000)


class StatusIn(BaseModel):
    action: Literal["pause", "resume", "archive"]


def _owned(db: Session, property_id: uuid.UUID, user: User) -> Property:
    prop = get_or_404(db, Property, property_id, "This space doesn't exist.")
    if prop.owner_id != user.id and "admin" not in user.role_names:
        raise HTTPException(403, "Only the owner can change this listing.")
    return prop


def _apply(db: Session, prop: Property, body: PropertyIn) -> None:
    data = body.model_dump(exclude_unset=True)
    if "amenities" in data and data["amenities"] is not None:
        data["amenities"] = [a for a in data["amenities"] if a in taxonomy.AMENITIES]
    if data.get("price_amount") == 0:
        data["price_amount"] = None
    for k, v in data.items():
        setattr(prop, k, v.strip() if isinstance(v, str) else v)
    if prop.size_value:
        prop.size_sqft = round(prop.size_value * UNIT_TO_SQFT.get(prop.size_unit or "sqft", 1.0), 1)
    else:
        prop.size_sqft = None
    if "lat" in data or "lng" in data:
        if prop.lat is not None and prop.lng is not None:
            loc = resolve_locality(db, prop.lat, prop.lng)
            prop.locality, prop.area_id = loc["locality"], loc["area_id"]
        else:
            prop.locality = prop.area_id = None
    if prop.availability == "now":
        prop.available_from = None
    elif prop.available_from and prop.available_from < date.today():
        raise HTTPException(422, "Pick an available-from date in the future, or choose 'available now'.")
    media.evaluate_quality(prop)


def _schedule(prop: Property, force: bool = False) -> None:
    if force or limiter.hit(f"recompute-property:{prop.id}", 1, 30):
        enqueue(tasks.recompute_property, str(prop.id))


def _top_match(db: Session, ids: list[uuid.UUID]) -> dict:
    if not ids:
        return {}
    rows = db.execute(select(Match, Demand).join(Demand, Demand.id == Match.demand_id)
                      .where(Match.property_id.in_(ids)).order_by(Match.property_id, Match.score.desc())).all()
    out: dict = {}
    for m, d in rows:
        entry = out.setdefault(m.property_id, {"count": 0, "top": None})
        entry["count"] += 1
        if entry["top"] is None:
            entry["top"] = {"category": d.category, "category_name": taxonomy.get(d.category).name,
                            "supporters": (m.components or {}).get("cluster_supporters", d.verified_support_count),
                            "score": m.score, "demand_id": str(d.id), "match_id": str(m.id)}
    return out


@router.post("/suggest-type")
def suggest_type(body: SuggestIn):
    sqft = round(body.size_value * UNIT_TO_SQFT[body.size_unit], 1) if body.size_value else None
    kind = taxonomy.suggest_property_type(sqft, body.description or "")
    return {"type": kind, "type_label": taxonomy.PROPERTY_TYPES[kind], "size_sqft": sqft,
            "size_sqm": round(sqft / UNIT_TO_SQFT["sqm"], 1) if sqft else None}


@router.get("")
def search(lat: float | None = Query(default=None, ge=-90, le=90), lng: float | None = Query(default=None, ge=-180, le=180),
           radius_km: float = Query(default=5, gt=0, le=50), type: str | None = None, category: str | None = None,
           size_min: float | None = Query(default=None, ge=0), size_max: float | None = Query(default=None, ge=0),
           budget: int | None = Query(default=None, ge=0), price_type: Literal["rent", "sale"] | None = None,
           sort: Literal["near", "recent", "size"] = "near", limit: int = 20, offset: int = 0,
           user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    clat = lat if lat is not None else (user.home_lat if user and user.home_lat is not None else settings.default_lat)
    clng = lng if lng is not None else (user.home_lng if user and user.home_lng is not None else settings.default_lng)
    dist = distance("properties", clat, clng).label("d")
    stmt = select(Property, dist).where(Property.status == "published", within("properties", clat, clng, radius_km * 1000))
    if type in taxonomy.PROPERTY_TYPES:
        stmt = stmt.where(Property.type == type)
    if category in taxonomy.BY_SLUG:
        lo, hi = taxonomy.size_window(category)
        stmt = stmt.where(Property.type.in_(taxonomy.get(category).types),
                          (Property.size_sqft.is_(None)) | Property.size_sqft.between(size_min or lo, size_max or hi))
    else:
        if size_min:
            stmt = stmt.where(Property.size_sqft >= size_min)
        if size_max:
            stmt = stmt.where(Property.size_sqft <= size_max)
    if price_type:
        stmt = stmt.where(Property.price_type == price_type)
    if budget:
        stmt = stmt.where((Property.price_amount.is_(None)) | (Property.price_amount <= budget))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {"near": (dist,), "recent": (Property.published_at.desc(),), "size": (Property.size_sqft.desc().nulls_last(),)}[sort]
    rows = db.execute(stmt.order_by(*order).limit(clamp(limit, 1, 50)).offset(max(offset, 0))).all()
    tops = _top_match(db, [p.id for p, _ in rows])
    return {"total": total, "center": {"lat": clat, "lng": clng},
            "items": [{**property_out(p, distance_m=float(d)), "demand": tops.get(p.id)} for p, d in rows]}


@router.get("/mine")
def mine(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """P1 owner home: spaces, demand matches, inquiries, add property."""
    props = db.scalars(select(Property).where(Property.owner_id == user.id, Property.status != "archived")
                       .order_by(Property.created_at.desc())).all()
    ids = [p.id for p in props]
    tops = _top_match(db, ids)
    week_ago = utcnow() - timedelta(days=7)
    new_matches = db.scalar(select(func.count(Match.id)).where(Match.property_id.in_(ids), Match.created_at >= week_ago)) if ids else 0
    inquiries = db.scalar(select(func.count(Inquiry.id)).where(Inquiry.to_user_id == user.id, Inquiry.status == "open")) or 0
    stale = [str(p.id) for p in props if p.status in ("published", "paused") and p.last_confirmed_at
             and p.last_confirmed_at < utcnow() - timedelta(days=30)]
    return {
        "spaces": [{**property_out(p, private=True), "matches": tops.get(p.id, {}).get("count", 0),
                    "top_demand": tops.get(p.id, {}).get("top")} for p in props],
        "new_matches_week": int(new_matches or 0), "open_inquiries": int(inquiries), "needs_confirmation": stale,
    }


@router.post("", status_code=201)
def create(body: PropertyIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    throttle(request, "property-create", 20, 86400, user.id)
    if "owner" not in user.role_names:
        user.roles.append(UserRole(role="owner"))
    prop = Property(owner_id=user.id, status="draft")
    db.add(prop)
    db.flush()
    _apply(db, prop, body)
    emit(db, "property.drafted", user.id, "property", prop.id)
    db.commit()
    return property_out(prop, private=True)


@router.get("/{property_id}")
def detail(property_id: uuid.UUID, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    prop = get_or_404(db, Property, property_id, "This space doesn't exist.")
    is_owner = bool(user and (prop.owner_id == user.id or "admin" in user.role_names))
    if prop.status != "published" and not is_owner:
        raise HTTPException(404, "This space isn't available any more.")
    owner = db.get(User, prop.owner_id)
    out = property_out(prop, private=is_owner, owner=owner)
    tops = _top_match(db, [prop.id]).get(prop.id, {})
    out.update(matches=tops.get("count", 0), top_demand=tops.get("top"), is_owner=is_owner,
               blockers=media.publish_blockers(prop) if is_owner else [],
               availability_text=matching.availability_text(prop))
    if prop.lat is not None:
        label, total = matching.density_label(db, prop.lat, prop.lng)
        out["demand_density"] = {"label": label, "supporters": total, "radius_m": 2000}
    if user and not is_owner:
        out["my_inquiry_id"] = db.scalar(select(Inquiry.id).where(
            Inquiry.from_user_id == user.id, Inquiry.property_id == prop.id).limit(1))
        out["my_inquiry_id"] = str(out["my_inquiry_id"]) if out["my_inquiry_id"] else None
    return out


@router.patch("/{property_id}")
def patch(property_id: uuid.UUID, body: PropertyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    prop = _owned(db, property_id, user)
    if prop.status in ("archived", "rejected"):
        raise HTTPException(409, "This listing is closed.")
    _apply(db, prop, body)
    if prop.status == "published":
        missing = media.publish_blockers(prop)
        if missing:
            raise HTTPException(422, {"code": "incomplete", "message": "A live listing needs " + ", ".join(missing) + ".",
                                      "missing": missing})
        prop.last_confirmed_at = utcnow()
    db.commit()
    if prop.status == "published":
        _schedule(prop)
    return property_out(prop, private=True)


@router.post("/{property_id}/media", status_code=201)
def upload(property_id: uuid.UUID, request: Request, file: UploadFile = File(...), user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    throttle(request, "upload", 60, 3600, user.id)
    prop = _owned(db, property_id, user)
    if len(prop.media) >= MAX_PHOTOS:
        raise HTTPException(409, f"You can add up to {MAX_PHOTOS} photos. Remove one to add another.")
    data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    item = media.process_upload(prop, data, file.content_type or "", list(prop.media))
    prop.media.append(item)
    db.flush()
    media.evaluate_quality(prop)
    db.commit()
    warning = None
    if item.is_duplicate:
        warning = "This looks like a photo you already added, so it won't count. Try a different angle."
    elif item.is_blurry:
        warning = "This photo looks blurry. A sharper one gets more interest."
    return {"media": property_out(prop, private=True)["media"][-1], "warning": warning,
            "quality_score": prop.quality_score, "quality_flags": prop.quality_flags,
            "good_photos": media.good_photos(prop), "blockers": media.publish_blockers(prop)}


@router.delete("/{property_id}/media/{media_id}")
def delete_media(property_id: uuid.UUID, media_id: uuid.UUID, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    prop = _owned(db, property_id, user)
    item = next((m for m in prop.media if m.id == media_id), None)
    if not item:
        raise HTTPException(404, "Photo not found.")
    if prop.status == "published" and media.good_photos(prop) - (0 if item.is_duplicate else 1) < 3:
        raise HTTPException(409, "A live listing needs at least 3 photos. Add another before removing this one.")
    storage = get_storage()
    for key in (item.storage_key, item.thumb_key):
        try:
            storage.delete(key)
        except Exception:
            pass
    prop.media.remove(item)
    db.flush()
    remaining = list(prop.media)
    for i, m in enumerate(remaining):  # re-check duplicates against earlier photos only
        m.is_duplicate = any(media.hamming(m.phash, o.phash) <= media.DUP_DISTANCE for o in remaining[:i])
    media.evaluate_quality(prop)
    db.commit()
    return property_out(prop, private=True)


@router.post("/{property_id}/publish")
def publish(property_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    prop = _owned(db, property_id, user)
    if prop.status == "published":
        return property_out(prop, private=True)
    if prop.status in ("archived", "rejected"):
        raise HTTPException(409, "This listing is closed.")
    media.evaluate_quality(prop)
    missing = media.publish_blockers(prop)
    if missing:
        raise HTTPException(422, {"code": "incomplete", "message": "Add " + ", ".join(missing) + " to publish.",
                                  "missing": missing})
    now = utcnow()
    first = prop.published_at is None
    prop.status, prop.last_confirmed_at = "published", now
    prop.published_at = prop.published_at or now
    owner = db.get(User, prop.owner_id)
    if prop.verification_level == "none" and owner and owner.identity_verified:
        prop.verification_level = "basic"
    if first:
        rewards.award(db, prop.owner_id, "property_listed", "property", prop.id)
    emit(db, "property.listed", user.id, "property", prop.id, {"type": prop.type, "size_sqft": prop.size_sqft})
    db.commit()
    _schedule(prop, force=True)
    db.refresh(prop)
    return {**property_out(prop, private=True), "reward": {"points": rewards.RULES["property_listed"]["points"],
                                                           "status": "pending"} if first else None}


@router.post("/{property_id}/status")
def set_status(property_id: uuid.UUID, body: StatusIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    prop = _owned(db, property_id, user)
    if prop.status == "rejected":
        raise HTTPException(409, "This listing was removed by moderation.")
    if body.action == "pause" and prop.status == "published":
        prop.status = "paused"
    elif body.action == "resume" and prop.status == "paused":
        missing = media.publish_blockers(prop)
        if missing:
            raise HTTPException(422, {"code": "incomplete", "message": "Add " + ", ".join(missing) + " first.",
                                      "missing": missing})
        prop.status, prop.last_confirmed_at = "published", utcnow()
    elif body.action == "archive":
        prop.status = "archived"
    emit(db, f"property.{body.action}", user.id, "property", prop.id)
    db.commit()
    _schedule(prop, force=True)
    return property_out(prop, private=True)


@router.post("/{property_id}/confirm")
def confirm(property_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """'Still available' in one tap: refreshes freshness and un-pauses stale listings."""
    prop = _owned(db, property_id, user)
    prop.last_confirmed_at = utcnow()
    prop.stale_notified_at = None
    if prop.status == "paused" and not media.publish_blockers(prop):
        prop.status = "published"
    emit(db, "property.confirmed", user.id, "property", prop.id)
    db.commit()
    _schedule(prop, force=True)
    return property_out(prop, private=True)


@router.post("/{property_id}/verification", status_code=201)
def request_verification(property_id: uuid.UUID, document_type: str = Form(..., max_length=40),
                         note: str | None = Form(default=None, max_length=240), file: UploadFile | None = File(default=None),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    prop = _owned(db, property_id, user)
    if db.scalar(select(Verification.id).where(Verification.subject_id == prop.id, Verification.status == "pending")):
        raise HTTPException(409, "Verification is already in review.")
    evidence: dict = {"document_type": document_type, "note": note}
    if file is not None:
        data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"Documents must be under {settings.max_upload_mb} MB.")
        if file.content_type not in ("application/pdf", "image/jpeg", "image/png", "image/webp"):
            raise HTTPException(415, "Upload a PDF or a photo of the document.")
        key = f"verifications/{prop.id}/{uuid.uuid4()}"
        get_private_storage().save(key, data, file.content_type)
        evidence.update(file_key=key, content_type=file.content_type, size=len(data))
    db.add(Verification(subject_type="property", subject_id=prop.id, kind="ownership_document", evidence=evidence,
                        submitted_by=user.id))
    prop.verification_status = "pending"
    emit(db, "property.verification_requested", user.id, "property", prop.id)
    db.commit()
    return {"status": "pending"}


@router.get("/{property_id}/matches")
def matches(property_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """P3: demand matched to this space, with a plain-language reason for every match."""
    prop = _owned(db, property_id, user)
    rows = db.execute(select(Match, Demand).join(Demand, Demand.id == Match.demand_id)
                      .where(Match.property_id == prop.id, Match.status != "dismissed")
                      .order_by(Match.score.desc()).limit(30)).all()
    interest_counts = dict(db.execute(select(DemandInterest.demand_id, func.count(DemandInterest.id))
                                      .where(DemandInterest.demand_id.in_([d.id for _, d in rows]))
                                      .group_by(DemandInterest.demand_id)).all()) if rows else {}
    items = []
    for m, d in rows:
        label, total = matching.density_label(db, d.lat, d.lng)
        items.append({**match_out(m, demand=d), "fit_label": "High local fit" if m.score >= 80 else
                      "Good local fit" if m.score >= matching.STRONG_SCORE else "Possible fit",
                      "density": {"label": label, "supporters": total, "radius_m": 2000},
                      "interested_businesses": int(interest_counts.get(d.id, 0))})
    for m, _ in rows:
        if m.status == "suggested":
            m.status = "viewed"
    db.commit()
    return {"property": property_out(prop, private=True), "items": items}


@router.post("/{property_id}/matches/{match_id}/offer")
def offer(property_id: uuid.UUID, match_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """'Contact business' when no business has spoken up yet: tell businesses looking for this category."""
    prop = _owned(db, property_id, user)
    m = get_or_404(db, Match, match_id)
    if m.property_id != prop.id:
        raise HTTPException(404, "Not found.")
    if not limiter.hit(f"offer:{m.id}", 1, 7 * 86400):
        raise HTTPException(429, "You already offered this space for this demand this week.")
    d = db.get(Demand, m.demand_id)
    profiles = db.scalars(select(BusinessProfile).where(BusinessProfile.categories.any(d.category))).all()
    city = resolve_locality(db, d.lat, d.lng)["city"]
    targets = [b for b in profiles if not b.preferred_cities or city in b.preferred_cities][:25]
    cat = taxonomy.get(d.category)
    for b in targets:
        notify(db, b.user_id, "space.offered", f"A space near {d.locality} fits {cat.noun}",
               f"{d.verified_support_count} residents asked for it. {m.reasons[0] if m.reasons else ''}"[:400],
               f"/properties/{prop.id}")
    m.status = "contacted"
    emit(db, "match.offered", user.id, "match", m.id, {"businesses": len(targets)})
    db.commit()
    return {"notified": len(targets)}


@router.post("/{property_id}/view")
def view(property_id: uuid.UUID, request: Request, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    prop = get_or_404(db, Property, property_id)
    if limiter.hit(f"view:p:{prop.id}:{user.id if user else ip_hash(request)}", 1, 1800):
        prop.view_count += 1
        emit(db, "property.viewed", user.id if user else None, "property", prop.id)
        db.commit()
    return {"views": prop.view_count}
