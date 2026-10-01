"""Decision reports for businesses planning a new outlet: competitor gap analysis and financial
feasibility, for a high-demand area or a specific vacant space."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import taxonomy
from ..db import get_db
from ..events import emit
from ..models import BusinessProfile, User
from ..ratelimit import limiter
from ..security import require_role
from ..services import reports

router = APIRouter(prefix="/reports", tags=["reports"])
business_only = require_role("business", "admin")


class Assumptions(BaseModel):
    ticket: float | None = Field(default=None, gt=0)
    margin_pct: float | None = Field(default=None, gt=0, lt=100)
    reach: float | None = Field(default=None, gt=0)
    staff: float | None = Field(default=None, ge=0)
    salary: float | None = Field(default=None, ge=0)
    rent: float | None = Field(default=None, ge=0)
    fitout: float | None = Field(default=None, ge=0)
    inventory: float | None = Field(default=None, ge=0)


class FeasibilityIn(BaseModel):
    category: str | None = None
    area_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    assumptions: Assumptions | None = None


def _context(db: Session, user: User, area_id, property_id, category):
    if not area_id and not property_id:
        raise HTTPException(422, "Choose an area or a space to analyse.")
    area, prop = reports.resolve_scope(db, area_id, property_id, user.id, "admin" in user.role_names)
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.user_id == user.id))
    cat = category if category in taxonomy.BY_SLUG else reports.default_category(db, profile, prop, area)
    return area, prop, profile, cat


def _log(db: Session, user: User, name: str, area, prop, cat: str) -> None:
    subject = prop.id if prop else area.id
    if limiter.hit(f"{name}:{user.id}:{subject}:{cat}", 1, 3600):
        emit(db, name, user.id, "property" if prop else "area", subject, {"category": cat})
        db.commit()


@router.get("/competitor-gap")
def competitor_gap(category: str | None = None, area_id: uuid.UUID | None = Query(default=None),
                   property_id: uuid.UUID | None = Query(default=None),
                   user: User = Depends(business_only), db: Session = Depends(get_db)):
    area, prop, _, cat = _context(db, user, area_id, property_id, category)
    out = reports.competitor_gap(db, cat, area, prop)
    _log(db, user, "report.competitor_gap", area, prop, cat)
    return out


@router.post("/feasibility")
def feasibility(body: FeasibilityIn, user: User = Depends(business_only), db: Session = Depends(get_db)):
    area, prop, profile, cat = _context(db, user, body.area_id, body.property_id, body.category)
    overrides = body.assumptions.model_dump(exclude_none=True) if body.assumptions else {}
    out = reports.feasibility(db, cat, area, prop, profile, overrides)
    if not overrides:
        _log(db, user, "report.feasibility", area, prop, cat)
    return out
