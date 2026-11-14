"""
Licence Window and Holdback Models.
Covers Tables 5 and 7. Supports multiple licence windows per contract and sequential holdback enforcement.
"""
from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    Date,
    ForeignKey,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UTCDateTime


class LicenceWindow(Base, TimestampMixin):
    """
    Table 5: Licence Windows.
    Defines availability time bounds, business models (SVOD, AVOD, TVOD), and exclusivity across territories.
    """
    __tablename__ = "licence_windows"
    __table_args__ = (
        CheckConstraint("end_time_utc > start_time_utc", name="ck_window_dates_valid"),
        Index("idx_window_lookup", "title_id", "territory_code", "window_type", "status"),
        Index("idx_window_contract", "contract_id"),
        Index("idx_window_times", "start_time_utc", "end_time_utc"),
    )

    window_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("licence_contracts.contract_id", ondelete="CASCADE"),
        nullable=False,
        comment="Parent licensing contract"
    )
    title_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("titles.title_id", ondelete="CASCADE"),
        nullable=False,
        comment="Governed audiovisual title"
    )
    territory_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("territories.country_code"),
        nullable=False,
        comment="ISO country code where window is granted"
    )
    window_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="SVOD",
        comment="Distribution window: THEATRICAL, PVOD, TVOD, SVOD, AVOD_FAST, LINEAR_SYNDICATION"
    )
    window_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Sequential window sequence number under licence"
    )
    window_start: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Local window start date (playable from 00:00:00 local)"
    )
    window_end: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Local window end date (playable until 23:59:59 local)"
    )
    start_time_utc: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        comment="Window open timestamp in UTC"
    )
    end_time_utc: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        comment="Window close / takedown timestamp in UTC"
    )
    exclusivity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="NON_EXCLUSIVE",
        comment="Exclusivity level: EXCLUSIVE, NON_EXCLUSIVE, CO_EXCLUSIVE"
    )
    allowed_devices: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ALL",
        comment="Device rights: ALL, MOBILE_ONLY, CONNECTED_TV, WEB_BROWSER"
    )
    grace_period_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=15,
        comment="In-flight stream cutoff grace buffer in minutes post window end"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="SCHEDULED",
        comment="Window lifecycle: SCHEDULED, ACTIVE, EXPIRED, REVOKED, BLACKED_OUT"
    )

    # Relationships
    contract: Mapped["LicenceContract"] = relationship("LicenceContract", back_populates="windows")
    title: Mapped["Title"] = relationship("Title", back_populates="windows")
    territory: Mapped["Territory"] = relationship("Territory")

    def __repr__(self) -> str:
        return f"<LicenceWindow(title='{self.title_id}', type='{self.window_type}', territory='{self.territory_code}', status='{self.status}')>"


class Holdback(Base, TimestampMixin):
    """
    Table 7: Holdback Information.
    Enforces minimum contractual blackout gaps between chronological release windows (e.g. Theatrical -> SVOD).
    """
    __tablename__ = "holdbacks"
    __table_args__ = (
        CheckConstraint("holdback_days >= 0", name="ck_holdback_days_non_negative"),
        Index("idx_holdback_contract_title", "contract_id", "title_id"),
    )

    holdback_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("licence_contracts.contract_id", ondelete="CASCADE"),
        nullable=False
    )
    title_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("titles.title_id", ondelete="CASCADE"),
        nullable=False
    )
    prior_window_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Preceding release window (e.g., THEATRICAL, TVOD)"
    )
    subsequent_window_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Succeeding release window restricted by holdback (e.g., SVOD)"
    )
    holdback_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=90,
        comment="Minimum required gap in calendar days between window close and next window open"
    )
    territory_code: Mapped[Optional[str]] = mapped_column(
        String(3),
        ForeignKey("territories.country_code"),
        nullable=True,
        comment="Specific territory code if regional holdback, NULL if worldwide"
    )
    enforcement_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="STRICT_BLACKOUT",
        comment="STRICT_BLACKOUT or GEO_RESTRICTED"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Relationships
    contract: Mapped["LicenceContract"] = relationship("LicenceContract", back_populates="holdbacks")
    title: Mapped["Title"] = relationship("Title")

    def __repr__(self) -> str:
        return f"<Holdback({self.prior_window_type} -> {self.subsequent_window_type}, days={self.holdback_days})>"
