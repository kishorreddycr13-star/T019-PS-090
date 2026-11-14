"""
Advertisement Revenue and Ad Impressions Models.
Covers Tables 12 and 13. Supports AVOD/FAST ad-supported monetization channels.
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


class AdvertisementRevenue(Base, TimestampMixin):
    """
    Table 12: Advertisement Revenue.
    Aggregates gross programmatic/direct ad billing and deductions for AVOD revenue-share pools.
    """
    __tablename__ = "advertisement_revenues"
    __table_args__ = (
        CheckConstraint("gross_ad_revenue >= 0", name="ck_gross_ad_revenue_non_negative"),
        CheckConstraint("net_distributable_ad_pool >= 0", name="ck_net_ad_pool_non_negative"),
        UniqueConstraint("period_key", "territory_code", "ad_network_name", name="uq_ad_revenue_period_partner"),
        Index("idx_ad_rev_period", "period_key", "territory_code"),
    )

    ad_revenue_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    period_key: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        comment="Accounting period in 'YYYY-MM' format"
    )
    territory_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("territories.country_code"),
        nullable=False
    )
    ad_network_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="DIRECT_DSP",
        comment="Ad demand source (e.g. Google Ad Manager, FreeWheel, SpringServe)"
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD"
    )
    total_impressions_served: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    gross_ad_revenue: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Total programmatic and direct ad billings"
    )
    agency_commissions: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Media agency commission deductions (e.g. 15%)"
    )
    ad_server_tech_fees: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Ad serving and SSAI insertion platform fees"
    )
    net_distributable_ad_pool: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Net ad pool for AVOD revenue-share allocation"
    )
    is_finalized: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # Relationships
    territory: Mapped["Territory"] = relationship("Territory")

    def __repr__(self) -> str:
        return f"<AdvertisementRevenue(period='{self.period_key}', network='{self.ad_network_name}', net={self.net_distributable_ad_pool})>"


class AdImpression(Base, TimestampMixin):
    """
    Table 13: Ad Impressions.
    Detailed ad playback telemetry capturing individual video ad slot impressions during title streams.
    """
    __tablename__ = "ad_impressions"
    __table_args__ = (
        CheckConstraint("effective_cpm >= 0", name="ck_cpm_rate_non_negative"),
        CheckConstraint("gross_value >= 0", name="ck_impression_gross_non_negative"),
        Index("idx_impression_title_time", "title_id", "impression_time_utc"),
    )

    impression_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    view_event_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("view_events.event_id", ondelete="SET NULL"),
        nullable=True,
        comment="Associated playback session if captured during viewer stream"
    )
    title_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("titles.title_id"),
        nullable=False
    )
    territory_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("territories.country_code"),
        nullable=False
    )
    ad_campaign_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )
    placement_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="MIDROLL",
        comment="Ad slot placement: PREROLL, MIDROLL, POSTROLL, OVERLAY"
    )
    impression_time_utc: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False
    )
    effective_cpm: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        comment="Cost Per Mille (CPM) realized for this impression"
    )
    ad_duration_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=15
    )
    was_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether the ad reached quartile 4 (100% completion)"
    )
    gross_value: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        comment="Attributed dollar revenue: CPM / 1000"
    )

    # Relationships
    title: Mapped["Title"] = relationship("Title")
    territory: Mapped["Territory"] = relationship("Territory")

    def __repr__(self) -> str:
        return f"<AdImpression(campaign='{self.ad_campaign_id}', title='{self.title_id}', cpm={self.effective_cpm})>"
