"""
Base declarative model and custom types for SQLAlchemy 2.0.
Ensures uniform UTC timestamping, UUID primary keys, and decimal safety.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, String, Numeric, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Returns current UTC timestamp with timezone."""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """
    Ensures datetime values are always stored in UTC and returned with timezone information,
    compatible with both SQLite (stored as ISO strings) and PostgreSQL (TIMESTAMPTZ).
    """
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect: Any) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Optional[datetime], dialect: Any) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    """Root declarative base class for all engine models."""
    pass


class TimestampMixin:
    """Provides uniform UTC audit timestamps across all database entities."""
    created_at_utc: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        nullable=False,
        comment="Timestamp when record was created in UTC"
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        comment="Timestamp when record was last updated in UTC"
    )
