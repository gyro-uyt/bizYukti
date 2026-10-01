"""Tokens, hashing and request identity.
Access tokens: short-lived HS256 JWTs sent as Bearer headers.
Refresh tokens: random, stored only as HMAC hashes, rotated on every use, delivered as an
httpOnly cookie scoped to /api/v1/auth."""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)
REFRESH_COOKIE = "by_refresh"


def utcnow() -> datetime:
    return datetime.now(UTC)


def keyed_hash(value: str, purpose: str = "general") -> str:
    key = f"{settings.secret_key}:{purpose}".encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def ip_hash(request: Request | None) -> str | None:
    if request is None:
        return None
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    return hashlib.sha256(f"{settings.ip_hash_salt}:{ip}".encode()).hexdigest() if ip else None


def client_key(request: Request) -> str:
    return ip_hash(request) or "anon"


def device_hash(device_id: str | None) -> str | None:
    return keyed_hash(device_id.strip(), "device") if device_id and device_id.strip() else None


def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def create_access_token(user: User) -> str:
    now = utcnow()
    payload = {
        "sub": str(user.id),
        "roles": user.role_names,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _decode(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        if payload.get("typ") != "access":
            return None
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User | None:
    if not creds:
        return None
    uid = _decode(creds.credentials)
    if not uid:
        return None
    user = db.get(User, uid)
    if not user or user.status != "active":
        return None
    return user


def current_user(user: User | None = Depends(optional_user)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if not set(roles) & set(user.role_names):
            raise HTTPException(status_code=403, detail="Your account doesn't have access to this.")
        return user

    return dep


def display_name(user: User | None) -> str:
    if not user or not user.name:
        return "A neighbour"
    parts = user.name.split()
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0]}."
