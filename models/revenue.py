"""
Title Share and Revenue Calculation Models.
Implements persistence for title_shares calculations (BR-05, BR-06).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Numeric,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin


class TitleShareRecord(Base, TimestampMixin):
    """
    Title Share Record entity.
    Maintains monthly territory-wise title revenue share allocations.
    Corresponds directly to title_shares.csv evaluation outputs.
    """
    __tablename__ = "title_shares"
    __table_args__ = (
        CheckConstraint("premium_view_hours >= 0", name="ck_title_view_hours_non_negative"),
        CheckConstraint("pool_share >= 0", name="ck_title_pool_share_non_negative"),
        CheckConstraint("ad_impressions >= 0", name="ck_title_ad_impressions_non_negative"),
        CheckConstraint("ad_share >= 0", name="ck_title_ad_share_non_negative"),
        CheckConstraint("title_share >= 0", name="ck_title_total_share_non_negative"),
        UniqueConstraint("period_key", "territory_code", "title_id", name="uq_title_share_period_terr_title"),
        Index("idx_title_share_lookup", "period_key", "territory_code"),
    )

    share_id: Mapped[str] = mapped_column(
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
    title_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("titles.title_id"),
        nullable=False
    )
    premium_view_hours: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Qualified and counted PREMIUM consumption in view-hours"
    )
    pool_ratio: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Proportion of territory subscription pool rounded half-up to 4 decimals"
    )
    pool_share: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Attributed subscription revenue share in paise"
    )
    ad_impressions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Qualified and counted FREE ad impressions served"
    )
    ad_ratio: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Proportion of territory ad pool rounded half-up to 4 decimals"
    )
    ad_share: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Attributed advertisement revenue share in paise"
    )
    title_share: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Total title revenue share (pool_share + ad_share) in paise"
    )

    # Relationships
    territory: Mapped["Territory"] = relationship("Territory")
    title: Mapped["Title"] = relationship("Title")

    def __repr__(self) -> str:
        return (
            f"<TitleShareRecord(month='{self.period_key}', terr='{self.territory_code}', "
            f"title='{self.title_id}', total={self.title_share})>"
        )
