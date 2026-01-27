from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    price_rules: Mapped[list["PriceRule"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    requests: Mapped[list["RequestLog"]] = relationship(back_populates="org", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)

    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    org: Mapped[Organization] = relationship(back_populates="api_keys")


class PriceRule(Base):
    __tablename__ = "price_rules"
    __table_args__ = (
        UniqueConstraint("org_id", "provider", "model", name="uq_price_rules_scope"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)

    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="qwen")
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    markup_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    org: Mapped[Organization] = relationship(back_populates="price_rules")


class RequestLog(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)

    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    org: Mapped[Organization] = relationship(back_populates="requests")
    usage_events: Mapped[list["UsageEvent"]] = relationship(back_populates="request", cascade="all, delete-orphan")


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    org_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)
    request_db_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("requests.id"), nullable=False, index=True)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)

    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    raw_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    billed_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    request: Mapped[RequestLog] = relationship(back_populates="usage_events")
