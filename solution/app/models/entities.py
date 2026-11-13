from datetime import datetime, time , timezone
from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    Time,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(
        String(100), primary_key=True
    )

    max_concurrent_calls: Mapped[int] = mapped_column(
        Integer, nullable=False
    )


class Campaign(Base):
    __tablename__ = "campaigns"

    campaign_id: Mapped[str] = mapped_column(
        String(100), primary_key=True
    )

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.tenant_id"), nullable=False
    )

    window_start: Mapped[time] = mapped_column(
        Time, nullable=False
    )

    window_end: Mapped[time] = mapped_column(
        Time, nullable=False
    )

    window_days: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False
    )

    timezone: Mapped[str] = mapped_column(
        String(50), default="Asia/Kolkata"
    )


class Lead(Base):
    __tablename__ = "leads"

    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "lead_id",
            name="uq_campaign_lead",
        ),
        Index("ix_leads_schedule", "state", "next_attempt_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.campaign_id"), nullable=False
    )

    lead_id: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    phone: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    customer_name: Mapped[str] = mapped_column(
        String(200), nullable=False
    )

    state: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )

    attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    callback_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    last_status: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    last_disposition: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CallAttempt(Base):
    __tablename__ = "call_attempts"

    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "lead_id",
            "attempt_number",
            name="uq_lead_attempt",
        ),
        Index("ix_calls_active", "state"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    request_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )

    call_sid: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.campaign_id"), nullable=False
    )

    lead_id: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    state: Mapped[str] = mapped_column(
        String(30), default="prepared", nullable=False
    )

    status: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    disposition: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    callback_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    fingerprint: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )

    request_id: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    payload: Mapped[str] = mapped_column(
        String, nullable=False
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class PhoneLock(Base):
    __tablename__ = "phone_locks"

    phone: Mapped[str] = mapped_column(
        String(20), primary_key=True
    )

    request_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )

    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class PhoneSuppression(Base):
    __tablename__ = "phone_suppressions"

    phone: Mapped[str] = mapped_column(
        String(20), primary_key=True
    )

    reason: Mapped[str] = mapped_column(
        String(50), default="dnd"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )