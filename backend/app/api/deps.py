"""Shared router helpers."""

import uuid

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..ratelimit import enforce
from ..security import client_key


def get_or_404(db: Session, model, obj_id: uuid.UUID | str, message: str = "Not found."):
    try:
        key = obj_id if isinstance(obj_id, uuid.UUID) else uuid.UUID(str(obj_id))
    except ValueError:
        raise HTTPException(404, message)
    obj = db.get(model, key)
    if obj is None:
        raise HTTPException(404, message)
    return obj


def device_id(x_device_id: str | None = Header(default=None, max_length=80)) -> str | None:
    """Anonymous per-install identifier sent by the web app; only ever stored hashed."""
    return x_device_id


def throttle(request: Request, scope: str, limit: int, window_s: int, user_id: uuid.UUID | None = None) -> None:
    enforce(f"{scope}:{user_id or client_key(request)}", limit, window_s)


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))
