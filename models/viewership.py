"""
View Events and Qualifying View Records Models.
Covers Tables 9 and 10. Implements raw playback telemetry ingestion, BR-07 qualifying criteria,
BR-08 24h de-duplication, and BR-09 subscriber tier metering.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Numeric,
    Boolean,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UTCDateTime


class ViewEvent(Base, TimestampMixin):
    """
    Table 9: View Events.
    High-throughput raw client telemetry heartbeats captured during active media streaming.
    """
    __tablename__ = "view_events"
    __table_args__ = (
        CheckConstraint("raw_watch_seconds >= 0", name="ck_view_raw_seconds_non_negative"),
        Index("idx_view_session", "session_id"),
        Index("idx_view_title_tier", "title_id", "tier_id"),
        Index("idx_view_playback_time", "playback_start_utc", "playback_end_utc"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Unique client playback session identifier"
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Subscriber account ID (pseudonymized)"
    )
    title_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("titles.title_id"),
        nullable=False
    )
    tier_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("subscriber_tiers.tier_id"),
        nullable=False
    )
    territory_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("territories.country_code"),
        nullable=False
    )
    device_category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="SMART_TV",
        comment="Device form factor: SMART_TV, MOBILE, TABLET, DESKTOP"
    )
    playback_start_utc: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False
    )
    playback_end_utc: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False
    )
    raw_watch_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Total unscrubbed wall-clock playback duration recorded by player"
    )
    ad_impressions: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of advertisements displayed during session"
    )
    ingested_utc: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        comment="Timestamp when playback telemetry arrived at ingestion pipeline"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address used for geo-validation"
    )
    is_vpn_detected: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Threat intelligence flag indicating proxy/VPN exit node"
    )

    # Convenience alias properties
    @property
    def view_id(self) -> str:
        return self.event_id

    @property
    def subscriber_id(self) -> str:
        return self.user_id

    @property
    def territory_id(self) -> str:
        return self.territory_code

    @property
    def tier(self) -> str:
        return self.tier_id

    @property
    def watch_seconds(self) -> int:
        return self.raw_watch_seconds

    @property
    def start_utc(self) -> datetime:
        return self.playback_start_utc

    # Relationships
    title: Mapped["Title"] = relationship("Title")
    tier_rel: Mapped["SubscriberTier"] = relationship("SubscriberTier")
    territory: Mapped["Territory"] = relationship("Territory")
    qualifying_record: Mapped[Optional["QualifyingViewRecord"]] = relationship(
        "QualifyingViewRecord",
        back_populates="view_event",
        uselist=False
    )

    def __repr__(self) -> str:
        return f"<ViewEvent(id='{self.event_id}', sub='{self.user_id}', title='{self.title_id}', raw_secs={self.raw_watch_seconds})>"


class QualifyingViewRecord(Base, TimestampMixin):
    """
    Table 10: Qualifying View Records.
    Scrubbed and validated playback consumption data feeding into pro-rata royalty calculations.
    """
    __tablename__ = "qualifying_view_records"
    __table_args__ = (
        CheckConstraint("qualified_watch_seconds >= 0", name="ck_qualified_seconds_non_negative"),
        UniqueConstraint("view_event_id", name="uq_qualifying_view_event"),
        Index("idx_qualifying_period_title", "period_key", "title_id"),
        Index("idx_qualifying_tier_territory", "period_key", "tier_id", "territory_code"),
    )

    record_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    view_event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("view_events.event_id", ondelete="CASCADE"),
        nullable=False
    )
    period_key: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        comment="Accounting settlement month in 'YYYY-MM' format"
    )
    title_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("titles.title_id"),
        nullable=False
    )
    tier_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("subscriber_tiers.tier_id"),
        nullable=False
    )
    territory_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("territories.country_code"),
        nullable=False
    )
    qualified_watch_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Legitimate continuous watch duration credited to royalty pool"
    )
    threshold_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=120,
        comment="BR-07 qualifying threshold in seconds = min(120, runtime * 0.50)"
    )
    is_qualified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether session passed BR-07 minimum threshold"
    )
    qualification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="QUALIFIED",
        comment="QUALIFIED, UNDER_THRESHOLD, DENIED_PLAYBACK"
    )
    is_counted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="BR-08: Whether view was counted or discarded as a duplicate within 24h"
    )
    view_hours: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Metered consumption in view-hours rounded half-up to 4 decimal places"
    )
    ad_impressions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Counted advertisement impressions for FREE tier views"
    )
    tag: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        default="",
        comment="Operational tags, e.g. LATE_VIEW"
    )
    licence_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        comment="Matched licence contract authorising this playback session"
    )
    playback_decision: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="ALLOWED",
        comment="ALLOWED or DENIED from Playback Eligibility Engine"
    )
    decision_reason: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        default="",
        comment="Reason code if playback denied (e.g. OUTSIDE_WINDOW)"
    )
    local_start_time: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        comment="Playback start time in territory local timezone"
    )

    # Relationships
    view_event: Mapped["ViewEvent"] = relationship("ViewEvent", back_populates="qualifying_record")
    title: Mapped["Title"] = relationship("Title")

    def __repr__(self) -> str:
        return (
            f"<QualifyingViewRecord(event='{self.view_event_id}', qual={self.is_qualified}, "
            f"counted={self.is_counted}, vh={self.view_hours})>"
        )
