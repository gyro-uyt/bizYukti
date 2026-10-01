"""The signed-in person: profile, onboarding, home locality, roles and account deletion."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import taxonomy
from ..db import get_db
from ..events import emit
from ..geo import resolve_locality
from ..models import (AuthSession, BusinessProfile, Inquiry, Message, Notification, User, UserRole, Verification)
from ..security import REFRESH_COOKIE, current_user, utcnow
from ..serializers import user_private
from ..services import trust

router = APIRouter(prefix="/me", tags=["me"])
PUBLIC_ROLES = ("resident", "owner", "business")


class HomeIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    label: str | None = Field(default=None, max_length=120)


class BusinessIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    categories: list[str] = Field(default_factory=list, max_length=6)
    preferred_cities: list[str] = Field(default_factory=list, max_length=6)
    budget_min: int | None = Field(default=None, ge=0, le=100_000_000)
    budget_max: int | None = Field(default=None, ge=0, le=100_000_000)
    size_min_sqft: int | None = Field(default=None, ge=0, le=1_000_000)
    size_max_sqft: int | None = Field(default=None, ge=0, le=1_000_000)
    registration_id: str | None = Field(default=None, max_length=40)
    website: str | None = Field(default=None, max_length=200)


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    active_role: Literal["resident", "owner", "business", "admin"] | None = None
    home: HomeIn | None = None


class OnboardingIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: Literal["resident", "owner", "business"]
    home: HomeIn
    business: BusinessIn | None = None


def _business(db: Session, user: User) -> BusinessProfile | None:
    return db.scalar(select(BusinessProfile).where(BusinessProfile.user_id == user.id))


def _grant(user: User, role: str) -> None:
    if role not in user.role_names:
        user.roles.append(UserRole(role=role))


def set_home(db: Session, user: User, home: HomeIn) -> None:
    loc = resolve_locality(db, home.lat, home.lng)
    user.home_lat, user.home_lng = home.lat, home.lng
    user.home_label = (home.label or loc["locality"])[:120]
    user.home_area_id = loc["area_id"]
    db.flush()
    trust.reevaluate_user_supports(db, user)


def upsert_business(db: Session, user: User, body: BusinessIn) -> BusinessProfile:
    profile = _business(db, user) or BusinessProfile(user_id=user.id, name=body.name)
    data = body.model_dump()
    data["categories"] = [c for c in data["categories"] if c in taxonomy.BY_SLUG]
    data["preferred_cities"] = [c.strip()[:80] for c in data["preferred_cities"] if c.strip()]
    if data["budget_min"] and data["budget_max"] and data["budget_min"] > data["budget_max"]:
        data["budget_min"], data["budget_max"] = data["budget_max"], data["budget_min"]
    for k, v in data.items():
        setattr(profile, k, v)
    db.add(profile)
    _grant(user, "business")
    return profile


def me_payload(db: Session, user: User) -> dict:
    out = user_private(user, _business(db, user))
    out["unread_notifications"] = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.read_at.is_(None))) or 0
    out["unread_messages"] = db.scalar(select(func.count(Message.id)).join(Inquiry, Inquiry.id == Message.inquiry_id).where(
        (Inquiry.from_user_id == user.id) | (Inquiry.to_user_id == user.id),
        Message.sender_id != user.id, Message.read_at.is_(None))) or 0
    return out


@router.get("")
def get_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return me_payload(db, user)


@router.patch("")
def patch_me(body: ProfilePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.name is not None:
        user.name = body.name.strip()
    if body.active_role is not None:
        if body.active_role == "admin" and "admin" not in user.role_names:
            raise HTTPException(403, "Your account doesn't have access to this.")
        if body.active_role in PUBLIC_ROLES:
            _grant(user, body.active_role)
        user.active_role = body.active_role
    if body.home is not None:
        set_home(db, user, body.home)
    db.commit()
    return me_payload(db, user)


@router.post("/onboarding")
def onboarding(body: OnboardingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.name = body.name.strip()
    _grant(user, body.role)
    user.active_role = body.role
    set_home(db, user, body.home)
    if body.role == "business":
        if not body.business:
            raise HTTPException(422, "Tell us your business name and what you plan to open.")
        upsert_business(db, user, body.business)
    user.onboarded = True
    emit(db, "user.onboarded", user.id, "user", user.id, {"role": body.role})
    db.commit()
    return me_payload(db, user)


@router.put("/business")
def put_business(body: BusinessIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    upsert_business(db, user, body)
    db.commit()
    return me_payload(db, user)


@router.post("/business/verification", status_code=201)
def business_verification(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """KYB-style review for the 'Verified business' badge (PRD section 11)."""
    profile = _business(db, user)
    if not profile:
        raise HTTPException(409, "Set up your business profile first.")
    if not (profile.registration_id or profile.website):
        raise HTTPException(422, "Add your GSTIN / registration number or website so we can verify you.")
    if profile.verification_status in ("pending", "verified"):
        return {"status": profile.verification_status}
    db.add(Verification(subject_type="business", subject_id=profile.id, kind="kyb", submitted_by=user.id,
                        evidence={"registration_id": profile.registration_id, "website": profile.website,
                                  "name": profile.name}))
    profile.verification_status = "pending"
    emit(db, "business.verification_requested", user.id, "business", profile.id)
    db.commit()
    return {"status": "pending"}


@router.delete("")
def delete_me(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Account deletion (DPDP-style right to erasure). Published requests stay as anonymous local
    signals; personal data, listings, sessions, messages and rewards are removed."""
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked_at=utcnow()))
    emit(db, "user.deleted", None, "user", user.id)
    db.delete(user)
    db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    return {"ok": True}
