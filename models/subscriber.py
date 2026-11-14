"""
Subscriber Tier and Monthly Subscription Revenue Models.
Covers Tables 8 and 11. Implements gross-to-net deduction cascade for SVOD pools.
"""
from __future__ import annotations

import uuid
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

from database.base import Base, TimestampMixin


class SubscriberTier(Base, TimestampMixin):
    """
    Table 8: Subscriber Tiers.
    Defines subscription packages (Mobile, Standard HD, Premium 4K) preventing cross-subsidization.
    """
    __tablename__ = "subscriber_tiers"
    __table_args__ = (
        CheckConstraint("monthly_price >= 0", name="ck_tier_price_non_negative"),
        CheckConstraint("max_concurrent_streams > 0", name="ck_tier_streams_positive"),
        Index("idx_tier_code", "tier_code"),
    )

    tier_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    tier_code: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        comment="System tier code (e.g., 'MOBILE', 'STANDARD_HD', 'PREMIUM_4K')"
    )
    tier_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name (e.g., 'Premium 4K Family Plan')"
    )
    monthly_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Base catalog retail monthly subscription price"
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD"
    )
    max_concurrent_streams: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2
    )
    max_resolution: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="HD",
        comment="Resolution limit: SD, HD, 4K_UHD"
    )
    is_ad_supported: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<SubscriberTier(code='{self.tier_code}', price={self.monthly_price} {self.currency})>"


class MonthlySubscriptionRevenue(Base, TimestampMixin):
    """
    Table 11: Monthly Subscription Revenue.
    Maintains audited gross billings and ordered gross-to-net deductions per (period, tier, territory).
    """
    __tablename__ = "monthly_subscription_revenues"
    __table_args__ = (
        CheckConstraint("gross_billing_amount >= 0", name="ck_gross_billing_non_negative"),
        CheckConstraint("net_distributable_pool >= 0", name="ck_net_pool_non_negative"),
        UniqueConstraint("period_key", "tier_id", "territory_code", name="uq_period_tier_territory"),
        Index("idx_rev_period_lookup", "period_key", "territory_code"),
    )

    revenue_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    period_key: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        comment="Accounting settlement month in 'YYYY-MM' format (e.g., '2026-10')"
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
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD"
    )
    subscriber_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Active paying subscriber headcount in period"
    )
    gross_billing_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Gross cash collected from subscription billings"
    )
    refunds_chargebacks: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Deduction 1: Customer refunds and credit card chargebacks"
    )
    statutory_taxes: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Deduction 2: Remitted indirect taxes, sales tax, VAT, GST"
    )
    app_store_commissions: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Deduction 3: Apple IAP (15-30%), Google Play, Roku store commission"
    )
    payment_processing_fees: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Deduction 4: Payment gateway merchant interchange (e.g. Stripe, Adyen 2-3%)"
    )
    platform_tech_fee: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Deduction 5: Contractual platform delivery & CDN infrastructure fee"
    )
    net_distributable_pool: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Net pool balance eligible for pro-rata royalty attribution"
    )
    is_finalized: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Flag indicating accounting period closure"
    )

    # Relationships
    tier: Mapped["SubscriberTier"] = relationship("SubscriberTier")
    territory: Mapped["Territory"] = relationship("Territory")

    def __repr__(self) -> str:
        return f"<MonthlySubscriptionRevenue(period='{self.period_key}', gross={self.gross_billing_amount}, net={self.net_distributable_pool})>"
