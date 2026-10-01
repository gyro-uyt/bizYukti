"""Client interaction events (PRD: collect views, saves, searches for future ranking models)."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..events import emit
from ..models import User
from ..ratelimit import limiter
from ..security import client_key, ip_hash, optional_user

router = APIRouter(tags=["events"])
ALLOWED = {"search.performed", "map.opened", "map.filtered", "opportunity.opened", "demand.share_opened",
           "onboarding.started", "listing.started"}


class EventIn(BaseModel):
    name: str = Field(max_length=48)
    subject_type: Literal["demand", "property", "area", "user"] | None = None
    subject_id: uuid.UUID | None = None
    data: dict = Field(default_factory=dict)


@router.post("/events", status_code=202)
def track(body: EventIn, request: Request, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    if body.name in ALLOWED and limiter.hit(f"events:{user.id if user else client_key(request)}", 240, 3600):
        data = {k: v for k, v in list(body.data.items())[:10] if isinstance(v, (str, int, float, bool))}
        emit(db, body.name, user.id if user else None, body.subject_type, body.subject_id, data, ip_hash(request))
        db.commit()
    return {"accepted": True}
