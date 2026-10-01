import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Notification, User
from ..security import current_user, utcnow
from ..serializers import iso

router = APIRouter(prefix="/notifications", tags=["notifications"])


class ReadIn(BaseModel):
    ids: list[uuid.UUID] | None = None  # None = mark all read


@router.get("")
def list_notifications(unread_only: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(Notification.created_at.desc()).limit(80)).all()
    unread = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id,
                                                                 Notification.read_at.is_(None)))
    return {"unread": unread or 0, "items": [
        {"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
         "read": n.read_at is not None, "created_at": iso(n.created_at)} for n in rows]}


@router.post("/read")
def mark_read(body: ReadIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if body.ids:
        stmt = stmt.where(Notification.id.in_(body.ids))
    db.execute(stmt.values(read_at=utcnow()))
    db.commit()
    return {"ok": True}
