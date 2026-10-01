"""Saved areas, spaces and requests."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import taxonomy
from ..db import get_db
from ..events import emit
from ..models import Demand, OpportunityArea, Property, SavedItem, User
from ..security import current_user
from ..serializers import area_out, demand_out, property_out

router = APIRouter(prefix="/saved", tags=["saved"])
MODELS = {"area": OpportunityArea, "property": Property, "demand": Demand}


class SaveIn(BaseModel):
    kind: Literal["area", "property", "demand"]
    ref_id: uuid.UUID
    category: str = ""


@router.get("")
def list_saved(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(SavedItem).where(SavedItem.user_id == user.id).order_by(SavedItem.created_at.desc())).all()
    out = {"areas": [], "properties": [], "demands": []}
    for kind, model in MODELS.items():
        ids = [i.ref_id for i in items if i.kind == kind]
        objs = {o.id: o for o in db.scalars(select(model).where(model.id.in_(ids)))} if ids else {}
        for i in items:
            if i.kind != kind or i.ref_id not in objs:
                continue
            o = objs[i.ref_id]
            if kind == "area":
                out["areas"].append({"id": str(i.id), "area": area_out(o), "category": i.category,
                                     "category_name": taxonomy.get(i.category).name if i.category else None})
            elif kind == "property":
                out["properties"].append({"id": str(i.id), "property": property_out(o)})
            elif o.status not in ("draft", "rejected"):
                out["demands"].append({"id": str(i.id), "demand": demand_out(o)})
    return out


@router.post("", status_code=201)
def save(body: SaveIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not db.get(MODELS[body.kind], body.ref_id):
        raise HTTPException(404, "Not found.")
    category = body.category if body.kind == "area" and body.category in taxonomy.BY_SLUG else ""
    existing = db.scalar(select(SavedItem).where(SavedItem.user_id == user.id, SavedItem.kind == body.kind,
                                                 SavedItem.ref_id == body.ref_id, SavedItem.category == category))
    if not existing:
        existing = SavedItem(user_id=user.id, kind=body.kind, ref_id=body.ref_id, category=category)
        db.add(existing)
        if body.kind == "area":
            emit(db, "opportunity.saved", user.id, "area", body.ref_id, {"category": category})
        db.commit()
    return {"id": str(existing.id), "saved": True}


@router.delete("")
def unsave(kind: Literal["area", "property", "demand"], ref_id: uuid.UUID, category: str = "",
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(SavedItem).where(SavedItem.user_id == user.id, SavedItem.kind == kind, SavedItem.ref_id == ref_id,
                                       SavedItem.category == (category if kind == "area" else "")))
    db.commit()
    return {"saved": False}
