"""Data model. Mirrors the PRD's core entities: User, Role, Demand, DemandSupport, Property,
PropertyMedia, BusinessProfile, OpportunityArea, Match, RewardLedger, Inquiry, Verification,
Notification, AuditEvent - plus the tables needed to run them (sessions, OTP, interests,
saved items, messages).

Every located table also has a PostGIS `geog geography(Point,4326)` column that is GENERATED
from lat/lng in the migration (with a GiST index). It is intentionally not mapped here, so the
ORM never writes it and queries reference it through app.geo helpers."""

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from .db import Base


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


def _fk(target: str, ondelete: str = "CASCADE", nullable: bool = False, index: bool = True):
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index)


class OpportunityArea(Base):
    __tablename__ = "opportunity_areas"
    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[int] = mapped_column(Integer, default=1500)
    # {"competition": {"pharmacy": 2}, "access": {"transit": "high", "road": "...", "footfall_index": 0.7, "notes": "..."}}
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created()


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    name: Mapped[str | None] = mapped_column(String(80))
    active_role: Mapped[str] = mapped_column(String(16), default="resident")
    home_lat: Mapped[float | None] = mapped_column(Float)
    home_lng: Mapped[float | None] = mapped_column(Float)
    home_label: Mapped[str | None] = mapped_column(String(120))
    home_area_id: Mapped[uuid.UUID | None] = _fk("opportunity_areas.id", "SET NULL", nullable=True, index=False)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | suspended
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list["UserRole"]] = relationship(lazy="selectin", cascade="all, delete-orphan")

    @property
    def role_names(self) -> list[str]:
        return sorted(r.role for r in self.roles)

    @property
    def identity_verified(self) -> bool:
        return bool(self.phone_verified or self.email_verified)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), primary_key=True)  # resident | owner | business | admin
    created_at: Mapped[datetime] = _created()


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    device_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created()
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    id: Mapped[uuid.UUID] = _pk()
    channel: Mapped[str] = mapped_column(String(8))  # phone | email
    destination: Mapped[str] = mapped_column(String(254), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Demand(Base):
    __tablename__ = "demands"
    id: Mapped[uuid.UUID] = _pk()
    author_id: Mapped[uuid.UUID | None] = _fk("users.id", "SET NULL", nullable=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    reason: Mapped[str] = mapped_column(String(24), default="daily_need")
    reason_note: Mapped[str | None] = mapped_column(String(200))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    locality: Mapped[str] = mapped_column(String(120))
    area_id: Mapped[uuid.UUID | None] = _fk("opportunity_areas.id", "SET NULL", nullable=True)
    # draft -> published -> growing -> matched -> fulfilled | expired   (rejected by moderation)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    verification_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | verified | rejected
    support_count: Mapped[int] = mapped_column(Integer, default=0)
    verified_support_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_support_count: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    ai_meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    embedding = deferred(mapped_column(Vector(), nullable=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_support_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DemandSupport(Base):
    __tablename__ = "demand_supports"
    __table_args__ = (UniqueConstraint("demand_id", "user_id", name="uq_support_once"),)
    id: Mapped[uuid.UUID] = _pk()
    demand_id: Mapped[uuid.UUID] = _fk("demands.id")
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | verified | rejected
    reason: Mapped[str | None] = mapped_column(String(80))
    distance_m: Mapped[float | None] = mapped_column(Float)
    device_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DemandInterest(Base):
    """A business saying 'we might open this here' - drives the Matched state."""

    __tablename__ = "demand_interests"
    __table_args__ = (UniqueConstraint("demand_id", "user_id", name="uq_interest_once"),)
    id: Mapped[uuid.UUID] = _pk()
    demand_id: Mapped[uuid.UUID] = _fk("demands.id")
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    note: Mapped[str | None] = mapped_column(String(280))
    created_at: Mapped[datetime] = _created()


class Property(Base):
    __tablename__ = "properties"
    id: Mapped[uuid.UUID] = _pk()
    owner_id: Mapped[uuid.UUID] = _fk("users.id")
    title: Mapped[str | None] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(16), default="shop")  # shop | office | land | warehouse | other
    size_value: Mapped[float | None] = mapped_column(Float)
    size_unit: Mapped[str] = mapped_column(String(8), default="sqft")  # sqft | sqm
    size_sqft: Mapped[float | None] = mapped_column(Float)
    price_type: Mapped[str] = mapped_column(String(8), default="rent")  # rent | sale
    price_amount: Mapped[int | None] = mapped_column(BigInteger)  # INR; monthly when rent
    price_negotiable: Mapped[bool] = mapped_column(Boolean, default=False)
    availability: Mapped[str] = mapped_column(String(8), default="now")  # now | future
    available_from: Mapped[date | None] = mapped_column(Date)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(String(240))
    locality: Mapped[str | None] = mapped_column(String(120))
    area_id: Mapped[uuid.UUID | None] = _fk("opportunity_areas.id", "SET NULL", nullable=True)
    description: Mapped[str | None] = mapped_column(Text)
    amenities: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)  # draft | published | paused | archived | rejected
    verification_status: Mapped[str] = mapped_column(String(16), default="unverified")  # unverified | pending | verified | rejected
    verification_level: Mapped[str] = mapped_column(String(16), default="none")  # none | basic | documents
    quality_score: Mapped[int] = mapped_column(Integer, default=0)
    quality_flags: Mapped[list] = mapped_column(JSONB, default=list)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    media: Mapped[list["PropertyMedia"]] = relationship(
        lazy="selectin", order_by="PropertyMedia.sort_order", cascade="all, delete-orphan"
    )


class PropertyMedia(Base):
    __tablename__ = "property_media"
    id: Mapped[uuid.UUID] = _pk()
    property_id: Mapped[uuid.UUID] = _fk("properties.id")
    storage_key: Mapped[str] = mapped_column(String(300))
    thumb_key: Mapped[str] = mapped_column(String(300))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    phash: Mapped[str] = mapped_column(String(16))
    blur_score: Mapped[float] = mapped_column(Float)
    is_blurry: Mapped[bool] = mapped_column(Boolean, default=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


class BusinessProfile(Base):
    __tablename__ = "business_profiles"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    categories: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    preferred_cities: Mapped[list[str]] = mapped_column(ARRAY(String(80)), default=list)
    budget_min: Mapped[int | None] = mapped_column(Integer)
    budget_max: Mapped[int | None] = mapped_column(Integer)
    size_min_sqft: Mapped[int | None] = mapped_column(Integer)
    size_max_sqft: Mapped[int | None] = mapped_column(Integer)
    registration_id: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(200))
    verification_status: Mapped[str] = mapped_column(String(16), default="unverified")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("demand_id", "property_id", name="uq_match_pair"),
        Index("ix_matches_property_score", "property_id", "score"),
    )
    id: Mapped[uuid.UUID] = _pk()
    demand_id: Mapped[uuid.UUID] = _fk("demands.id")
    property_id: Mapped[uuid.UUID] = _fk("properties.id", index=False)
    score: Mapped[int] = mapped_column(Integer)
    distance_m: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list] = mapped_column(JSONB, default=list)
    components: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="suggested")  # suggested | viewed | contacted | dismissed
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class SavedItem(Base):
    __tablename__ = "saved_items"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref_id", "category", name="uq_saved_item"),)
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    kind: Mapped[str] = mapped_column(String(12))  # area | property | demand
    ref_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    category: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = _created()


class Inquiry(Base):
    __tablename__ = "inquiries"
    id: Mapped[uuid.UUID] = _pk()
    from_user_id: Mapped[uuid.UUID] = _fk("users.id")
    to_user_id: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True)  # None = BizYukti team (market brief)
    kind: Mapped[str] = mapped_column(String(20))  # space | business | market_brief
    property_id: Mapped[uuid.UUID | None] = _fk("properties.id", "SET NULL", nullable=True)
    demand_id: Mapped[uuid.UUID | None] = _fk("demands.id", "SET NULL", nullable=True)
    area_id: Mapped[uuid.UUID | None] = _fk("opportunity_areas.id", "SET NULL", nullable=True, index=False)
    category: Mapped[str | None] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(12), default="open")  # open | replied | closed
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    last_message_at: Mapped[datetime] = _created()

    messages: Mapped[list["Message"]] = relationship(lazy="selectin", order_by="Message.created_at", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = _pk()
    inquiry_id: Mapped[uuid.UUID] = _fk("inquiries.id")
    sender_id: Mapped[uuid.UUID | None] = _fk("users.id", "SET NULL", nullable=True, index=False)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RewardLedger(Base):
    __tablename__ = "reward_ledger"
    __table_args__ = (UniqueConstraint("user_id", "action", "ref_id", name="uq_reward_once"),)
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    action: Mapped[str] = mapped_column(String(32))
    points: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | available | reversed
    ref_type: Mapped[str | None] = mapped_column(String(16))
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(String(200))
    voucher_code: Mapped[str | None] = mapped_column(String(24))
    expected_unlock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Verification(Base):
    __tablename__ = "verifications"
    id: Mapped[uuid.UUID] = _pk()
    subject_type: Mapped[str] = mapped_column(String(16))  # demand | property | business | support
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # ownership_document | kyb | risk_review | manual
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)  # pending | approved | rejected
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    submitted_by: Mapped[uuid.UUID | None] = _fk("users.id", "SET NULL", nullable=True, index=False)
    reviewed_by: Mapped[uuid.UUID | None] = _fk("users.id", "SET NULL", nullable=True, index=False)
    reason: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = _created()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str | None] = mapped_column(String(400))
    link: Mapped[str | None] = mapped_column(String(240))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class AuditEvent(Base):
    """Append-only event log: audit trail + the interaction stream used for ranking models."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(48), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    subject_type: Mapped[str | None] = mapped_column(String(16))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
