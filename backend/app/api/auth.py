"""Passwordless sign-in: one-time codes by phone or email, short-lived access tokens,
rotating refresh tokens in an httpOnly cookie."""

import re
from datetime import timedelta
from typing import Literal

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..events import emit
from ..models import AuthSession, BusinessProfile, OtpChallenge, User, UserRole
from ..ratelimit import enforce
from ..security import (REFRESH_COOKIE, client_key, create_access_token, device_hash, ip_hash, keyed_hash,
                        new_otp, new_refresh_token, utcnow)
from ..serializers import user_private
from ..services.notify import deliver_otp
from .deps import device_id

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE_PATH = "/api/v1/auth"


class OtpRequest(BaseModel):
    channel: Literal["phone", "email"]
    destination: str = Field(min_length=3, max_length=254)


class OtpVerify(OtpRequest):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


def normalise_destination(channel: str, raw: str) -> str:
    value = raw.strip()
    if channel == "email":
        try:
            return validate_email(value, check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            raise HTTPException(422, "Enter a valid email address.")
    digits = re.sub(r"[^\d+]", "", value)
    if digits.startswith("+"):
        if not re.fullmatch(r"\+\d{8,15}", digits):
            raise HTTPException(422, "Enter a valid phone number.")
        return digits
    digits = digits.lstrip("0")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise HTTPException(422, "Enter a valid 10-digit mobile number.")
    return f"+91{digits}"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(REFRESH_COOKIE, token, max_age=settings.refresh_token_days * 86400, httponly=True,
                        secure=settings.cookie_secure, samesite="lax", path=COOKIE_PATH)


def _session_payload(db: Session, user: User) -> dict:
    business = db.scalar(select(BusinessProfile).where(BusinessProfile.user_id == user.id))
    return {"access_token": create_access_token(user), "token_type": "bearer",
            "expires_in": settings.access_token_minutes * 60, "user": user_private(user, business)}


@router.post("/otp/request")
def request_otp(body: OtpRequest, request: Request, db: Session = Depends(get_db)):
    dest = normalise_destination(body.channel, body.destination)
    enforce(f"otp-dest:{dest}", 5, 900, "Too many codes requested. Try again in 15 minutes.")
    enforce(f"otp-ip:{client_key(request)}", 30, 3600, "Too many codes requested from this network.")
    now = utcnow()
    db.execute(update(OtpChallenge).where(OtpChallenge.destination == dest, OtpChallenge.consumed_at.is_(None))
               .values(consumed_at=now))
    code = new_otp()
    db.add(OtpChallenge(channel=body.channel, destination=dest, code_hash=keyed_hash(f"{dest}:{code}", "otp"),
                        ip_hash=ip_hash(request), expires_at=now + timedelta(minutes=settings.otp_ttl_minutes)))
    deliver_otp(body.channel, dest, code)
    db.commit()
    out = {"sent": True, "destination": dest, "expires_in": settings.otp_ttl_minutes * 60}
    if settings.otp_dev_echo and not settings.is_production:
        out["dev_code"] = code
    return out


@router.post("/otp/verify")
def verify_otp(body: OtpVerify, request: Request, response: Response, device: str | None = Depends(device_id),
               db: Session = Depends(get_db)):
    dest = normalise_destination(body.channel, body.destination)
    enforce(f"otp-verify:{dest}", 10, 900, "Too many attempts. Request a new code in a few minutes.")
    now = utcnow()
    challenge = db.scalar(select(OtpChallenge).where(
        OtpChallenge.destination == dest, OtpChallenge.consumed_at.is_(None), OtpChallenge.expires_at > now)
        .order_by(OtpChallenge.created_at.desc()).limit(1).with_for_update())
    if not challenge:
        raise HTTPException(400, "That code has expired. Request a new one.")
    challenge.attempts += 1
    if challenge.code_hash != keyed_hash(f"{dest}:{body.code}", "otp"):
        if challenge.attempts >= settings.otp_max_attempts:
            challenge.consumed_at = now
        db.commit()
        raise HTTPException(400, "That code isn't right. Check and try again.")
    challenge.consumed_at = now

    field = User.email if body.channel == "email" else User.phone
    user = db.scalar(select(User).where(field == dest))
    is_new = user is None
    if is_new:
        user = User(email=dest if body.channel == "email" else None, phone=dest if body.channel == "phone" else None)
        user.roles = [UserRole(role="resident")]
        db.add(user)
        db.flush()
    if user.status != "active":
        db.commit()
        raise HTTPException(403, "This account is suspended. Contact support if you think this is a mistake.")
    if body.channel == "email":
        user.email_verified = True
    else:
        user.phone_verified = True
    is_admin = (body.channel == "email" and dest in settings.admin_email_list) or \
               (body.channel == "phone" and dest in settings.admin_phone_list)
    if is_admin and "admin" not in user.role_names:
        user.roles.append(UserRole(role="admin"))
    user.last_seen_at = now
    token = new_refresh_token()
    db.add(AuthSession(user_id=user.id, refresh_hash=keyed_hash(token, "refresh"), device_hash=device_hash(device),
                       user_agent=(request.headers.get("user-agent") or "")[:200],
                       expires_at=now + timedelta(days=settings.refresh_token_days), last_used_at=now))
    emit(db, "auth.signed_in", user.id, "user", user.id, {"channel": body.channel, "new": is_new}, ip_hash(request))
    db.commit()
    db.refresh(user)
    _set_refresh_cookie(response, token)
    return {**_session_payload(db, user), "is_new": is_new}


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(401, "Sign in to continue.")
    enforce(f"refresh:{client_key(request)}", 120, 3600)
    now = utcnow()
    session = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == keyed_hash(token, "refresh"))
                        .with_for_update())
    if not session or session.revoked_at or session.expires_at <= now:
        response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
        raise HTTPException(401, "Your session ended. Sign in again.")
    user = db.get(User, session.user_id)
    if not user or user.status != "active":
        session.revoked_at = now
        db.commit()
        raise HTTPException(401, "Sign in to continue.")
    new_token = new_refresh_token()
    session.refresh_hash = keyed_hash(new_token, "refresh")
    session.last_used_at = now
    session.expires_at = now + timedelta(days=settings.refresh_token_days)
    user.last_seen_at = now
    db.commit()
    _set_refresh_cookie(response, new_token)
    return _session_payload(db, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        session = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == keyed_hash(token, "refresh")))
        if session and not session.revoked_at:
            session.revoked_at = utcnow()
            db.commit()
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return {"ok": True}
