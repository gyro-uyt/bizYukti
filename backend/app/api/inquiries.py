"""In-app inquiries and messages. Contact details are never exchanged by the platform;
people decide themselves when to share them inside a conversation."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, true, update
from sqlalchemy.orm import Session

from .. import taxonomy
from ..db import get_db
from ..events import emit
from ..models import (Demand, DemandInterest, Inquiry, Match, Message, OpportunityArea, Property, User, UserRole)
from ..security import current_user, display_name, utcnow
from ..serializers import inquiry_out, iso, property_out
from ..services.notify import notify
from .deps import get_or_404, throttle

router = APIRouter(prefix="/inquiries", tags=["inquiries"])


class InquiryIn(BaseModel):
    kind: Literal["space", "business", "market_brief"]
    message: str = Field(min_length=2, max_length=2000)
    property_id: uuid.UUID | None = None
    demand_id: uuid.UUID | None = None
    interest_id: uuid.UUID | None = None
    area_id: uuid.UUID | None = None
    category: str | None = None


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


def _can_see(i: Inquiry, user: User) -> bool:
    return user.id in (i.from_user_id, i.to_user_id) or (i.to_user_id is None and "admin" in user.role_names)


def _context(db: Session, items: list[Inquiry]) -> dict:
    pids = {i.property_id for i in items if i.property_id}
    dids = {i.demand_id for i in items if i.demand_id}
    aids = {i.area_id for i in items if i.area_id}
    props = {p.id: p for p in db.scalars(select(Property).where(Property.id.in_(pids)))} if pids else {}
    dems = {d.id: d for d in db.scalars(select(Demand).where(Demand.id.in_(dids)))} if dids else {}
    areas = {a.id: a for a in db.scalars(select(OpportunityArea).where(OpportunityArea.id.in_(aids)))} if aids else {}
    out = {}
    for i in items:
        ctx = {}
        if i.property_id in props:
            p = property_out(props[i.property_id])
            ctx["property"] = {"id": p["id"], "title": p["display_title"], "cover_url": p["cover_url"],
                               "locality": p["locality"]}
        if i.demand_id in dems:
            d = dems[i.demand_id]
            ctx["demand"] = {"id": str(d.id), "title": f"{d.title} near {d.locality}", "supporters": d.verified_support_count}
        if i.area_id in areas:
            a = areas[i.area_id]
            ctx["area"] = {"id": str(a.id), "name": a.name, "city": a.city}
        out[i.id] = ctx
    return out


def _people(db: Session, items: list[Inquiry]) -> dict:
    ids = {i.from_user_id for i in items} | {i.to_user_id for i in items if i.to_user_id}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def _thread(db: Session, i: Inquiry, user: User) -> dict:
    people = _people(db, [i])
    senders = {m.sender_id for m in i.messages if m.sender_id and m.sender_id not in people}
    if senders:
        people.update({u.id: u for u in db.scalars(select(User).where(User.id.in_(senders)))})
    out = inquiry_out(i, user, people, _context(db, [i])[i.id])
    out["messages"] = [{
        "id": str(m.id), "body": m.body, "mine": m.sender_id == user.id, "created_at": iso(m.created_at),
        "sender": ("BizYukti team" if i.to_user_id is None and m.sender_id != i.from_user_id
                   else display_name(people.get(m.sender_id))),
    } for m in i.messages]
    return out


def _add_message(db: Session, i: Inquiry, sender: User, body: str) -> None:
    now = utcnow()
    i.messages.append(Message(sender_id=sender.id, body=body.strip()))
    i.last_message_at = now
    if sender.id != i.from_user_id and i.status == "open":
        i.status = "replied"
    recipient = i.to_user_id if sender.id == i.from_user_id else i.from_user_id
    if recipient:
        notify(db, recipient, "message.received", f"New message: {i.subject}"[:160], body[:140], f"/inquiries/{i.id}")
    else:
        for admin_id in db.scalars(select(UserRole.user_id).where(UserRole.role == "admin")):
            notify(db, admin_id, "brief.requested", f"Team inbox: {i.subject}"[:160], body[:140], f"/inquiries/{i.id}")


@router.post("", status_code=201)
def create(body: InquiryIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    throttle(request, "inquiry", 30, 86400, user.id)
    to_user, subject, prop_id, demand_id = None, "", body.property_id, body.demand_id
    category = body.category if body.category in taxonomy.BY_SLUG else None
    if body.kind == "space":
        prop = get_or_404(db, Property, body.property_id or uuid.uuid4(), "This space isn't available.")
        if prop.status != "published":
            raise HTTPException(409, "This space isn't available any more.")
        if prop.owner_id == user.id:
            raise HTTPException(409, "This is your own listing.")
        to_user = prop.owner_id
        subject = f"Interest in your {property_out(prop)['display_title'].lower()}"
        if demand_id:
            db.execute(update(Match).where(Match.property_id == prop.id, Match.demand_id == demand_id)
                       .values(status="contacted"))
    elif body.kind == "business":
        interest = get_or_404(db, DemandInterest, body.interest_id or uuid.uuid4(), "That business isn't available.")
        demand = db.get(Demand, interest.demand_id)
        prop = get_or_404(db, Property, body.property_id or uuid.uuid4(), "Choose one of your spaces.")
        if prop.owner_id != user.id:
            raise HTTPException(403, "Choose one of your own spaces.")
        to_user, demand_id, category = interest.user_id, demand.id, demand.category
        subject = f"A space for {demand.title.lower()} near {demand.locality}"
        db.execute(update(Match).where(Match.property_id == prop.id, Match.demand_id == demand.id).values(status="contacted"))
    else:
        area = get_or_404(db, OpportunityArea, body.area_id or uuid.uuid4(), "Area not found.")
        if not category:
            raise HTTPException(422, "Pick a business category for the brief.")
        subject = f"Market brief: {taxonomy.get(category).name} in {area.name}, {area.city}"
    if to_user == user.id:
        raise HTTPException(409, "You can't message yourself.")

    existing = db.scalar(select(Inquiry).where(
        Inquiry.from_user_id == user.id, Inquiry.kind == body.kind, Inquiry.status != "closed",
        Inquiry.to_user_id == to_user if to_user else Inquiry.to_user_id.is_(None),
        Inquiry.property_id == prop_id if prop_id else Inquiry.property_id.is_(None),
        Inquiry.area_id == body.area_id if body.kind == "market_brief" else true(),
        Inquiry.category == category if body.kind == "market_brief" else true()))
    inquiry = existing or Inquiry(from_user_id=user.id, to_user_id=to_user, kind=body.kind, property_id=prop_id,
                                  demand_id=demand_id, area_id=body.area_id, category=category, subject=subject[:160])
    if not existing:
        db.add(inquiry)
        db.flush()
    _add_message(db, inquiry, user, body.message)
    emit(db, "inquiry.sent", user.id, "inquiry", inquiry.id, {"kind": body.kind, "category": category,
                                                              "demand_id": str(demand_id) if demand_id else None})
    db.commit()
    return _thread(db, inquiry, user)


@router.get("")
def list_inquiries(box: Literal["all", "sent", "received", "team"] = "all", user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    stmt = select(Inquiry)
    if box == "sent":
        stmt = stmt.where(Inquiry.from_user_id == user.id)
    elif box == "received":
        stmt = stmt.where(Inquiry.to_user_id == user.id)
    elif box == "team":
        if "admin" not in user.role_names:
            raise HTTPException(403, "Your account doesn't have access to this.")
        stmt = stmt.where(Inquiry.to_user_id.is_(None))
    else:
        stmt = stmt.where(or_(Inquiry.from_user_id == user.id, Inquiry.to_user_id == user.id))
    items = db.scalars(stmt.order_by(Inquiry.last_message_at.desc()).limit(100)).all()
    people, ctx = _people(db, items), _context(db, items)
    return {"items": [inquiry_out(i, user, people, ctx[i.id]) for i in items]}


@router.get("/{inquiry_id}")
def thread(inquiry_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    i = get_or_404(db, Inquiry, inquiry_id, "Conversation not found.")
    if not _can_see(i, user):
        raise HTTPException(404, "Conversation not found.")
    now = utcnow()
    for m in i.messages:
        if m.sender_id != user.id and m.read_at is None and (user.id in (i.from_user_id, i.to_user_id)):
            m.read_at = now
    db.commit()
    return _thread(db, i, user)


@router.post("/{inquiry_id}/messages", status_code=201)
def reply(inquiry_id: uuid.UUID, body: MessageIn, request: Request, user: User = Depends(current_user),
          db: Session = Depends(get_db)):
    throttle(request, "message", 120, 3600, user.id)
    i = get_or_404(db, Inquiry, inquiry_id, "Conversation not found.")
    if not _can_see(i, user):
        raise HTTPException(404, "Conversation not found.")
    if i.status == "closed":
        raise HTTPException(409, "This conversation is closed.")
    _add_message(db, i, user, body.body)
    db.commit()
    return _thread(db, i, user)


@router.post("/{inquiry_id}/close")
def close(inquiry_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    i = get_or_404(db, Inquiry, inquiry_id, "Conversation not found.")
    if not _can_see(i, user):
        raise HTTPException(404, "Conversation not found.")
    i.status = "closed"
    db.commit()
    return _thread(db, i, user)
