"""
Territory, Timezone, and Withholding Tax Models.
Covers Tables 6 and 17.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    String,
    Numeric,
    Boolean,
    Date,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin


class Territory(Base, TimestampMixin):
    """
    Table 6a: Territory Master Data.
    Stores ISO-3166 territory codes, currency, and default IANA time zones.
    """
    __tablename__ = "territories"

    country_code: Mapped[str] = mapped_column(
        String(3),
        primary_key=True,
        comment="ISO-3166-1 alpha-2 or alpha-3 code (e.g., 'US', 'GB', 'IN', 'DE')"
    )
    country_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Full territorial name"
    )
    default_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
        comment="ISO-4217 Currency Code"
    )
    primary_iana_timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="UTC",
        comment="Default IANA Timezone identifier (e.g., 'America/New_York', 'Asia/Kolkata')"
    )
    is_sanctioned: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Trade compliance / embargo flag"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Relationships
    time_zones: Mapped[List["TerritoryTimeZone"]] = relationship(
        "TerritoryTimeZone",
        back_populates="territory",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Territory(code='{self.country_code}', name='{self.country_name}')>"


class TerritoryTimeZone(Base, TimestampMixin):
    """
    Table 6b: Territory Time Zones (Multi-Zone Countries).
    Supports countries with multiple IANA time zones (e.g., US, Canada, Australia).
    """
    __tablename__ = "territory_time_zones"
    __table_args__ = (
        UniqueConstraint("country_code", "iana_timezone", name="uq_territory_iana_tz"),
    )

    tz_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    country_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("territories.country_code", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    iana_timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Standard IANA Timezone Identifier (e.g., 'America/Los_Angeles')"
    )
    zone_description: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Human readable zone name (e.g., 'Pacific Standard Time')"
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # Relationships
    territory: Mapped["Territory"] = relationship("Territory", back_populates="time_zones")


class WithholdingTaxRate(Base, TimestampMixin):
    """
    Table 17: Withholding Tax Rates and Treaty Rates.
    Stores statutory and Double Taxation Avoidance Agreement (DTAA) treaty rates per country pair.
    """
    __tablename__ = "withholding_tax_rates"
    __table_args__ = (
        CheckConstraint(
            "statutory_wht_rate >= 0 AND statutory_wht_rate <= 100",
            name="ck_statutory_wht_range"
        ),
        CheckConstraint(
            "treaty_wht_rate >= 0 AND treaty_wht_rate <= 100",
            name="ck_treaty_wht_range"
        ),
        CheckConstraint(
            "effective_wht_rate >= 0 AND effective_wht_rate <= 100",
            name="ck_effective_wht_range"
        ),
        UniqueConstraint(
            "source_country_code", "recipient_country_code", "effective_from",
            name="uq_tax_treaty_pair_date"
        ),
        Index("idx_wht_lookup", "source_country_code", "recipient_country_code", "is_active"),
    )

    rate_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    source_country_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("territories.country_code"),
        nullable=False,
        comment="Country where OTT entity is remitting royalties from"
    )
    recipient_country_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("territories.country_code"),
        nullable=False,
        comment="Country of tax residency of Licensor / Studio"
    )
    statutory_wht_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Domestic standard withholding tax percentage (e.g. 30.00)"
    )
    treaty_wht_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="DTAA Treaty concession withholding tax percentage (e.g. 10.00)"
    )
    effective_wht_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Actual applied rate after tax residency certificate (TRC) validation"
    )
    treaty_reference: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
        comment="DTAA treaty treaty article or treaty citation"
    )
    effective_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Effective start date of tax rule"
    )
    effective_to: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Effective end date of tax rule, null if indefinitely active"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
