"""
Audit Log Model.
Covers Table 20: Audit Logs.
Provides tamper-evident event logging, forensic tracking, and change audit trails.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin, UTCDateTime, utc_now


class AuditLog(Base, TimestampMixin):
    """
    Table 20: Audit Logs.
    Stores immutable system change records for contracts, windows, overrides, and settlements.
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_table_record", "table_name", "record_id"),
        Index("idx_audit_timestamp", "created_at_utc"),
        Index("idx_audit_action", "action"),
    )

    log_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    table_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Database table impacted by operation"
    )
    record_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Primary key value of impacted record"
    )
    action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Action performed: INSERT, UPDATE, DELETE, SETTLEMENT_LOCK, MANUAL_OVERRIDE"
    )
    performed_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="SYSTEM",
        comment="Username, service account, or caller token"
    )
    old_values_json: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="State before mutation formatted as JSON string"
    )
    new_values_json: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="State after mutation formatted as JSON string"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="Caller network address"
    )
    cryptographic_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash chaining this log entry to guarantee immutability"
    )

    def __repr__(self) -> str:
        return f"<AuditLog(table='{self.table_name}', record='{self.record_id}', action='{self.action}', by='{self.performed_by}')>"
