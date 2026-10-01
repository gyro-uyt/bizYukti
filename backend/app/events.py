import uuid

from sqlalchemy.orm import Session

from .models import AuditEvent


def emit(db: Session, name: str, actor_id: uuid.UUID | None = None, subject_type: str | None = None,
         subject_id: uuid.UUID | None = None, data: dict | None = None, ip_hash: str | None = None) -> None:
    """Adds an event to the current transaction (committed with the caller's unit of work)."""
    db.add(AuditEvent(name=name, actor_id=actor_id, subject_type=subject_type, subject_id=subject_id,
                      data=data or {}, ip_hash=ip_hash))
