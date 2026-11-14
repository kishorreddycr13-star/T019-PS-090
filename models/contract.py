"""
Licence Contract, Minimum Guarantee, and Payment Cap Models.
Covers Tables 4, 14, and 16.
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


class LicenceContract(Base, TimestampMixin):
    """
    Table 4: Licence Contracts.
    Master legal agreement governing rights grants, financial rev-share models, and fee structures.
    """
    __tablename__ = "licence_contracts"
    __table_args__ = (
        CheckConstraint(
            "expiration_date >= effective_date",
            name="ck_contract_dates_valid"
        ),
        CheckConstraint(
            "rev_share_percentage >= 0.00 AND rev_share_percentage <= 100.00",
            name="ck_contract_rev_share_range"
        ),
        CheckConstraint(
            "technical_fee_percentage >= 0.00 AND technical_fee_percentage <= 100.00",
            name="ck_contract_tech_fee_range"
        ),
        Index("idx_contract_licensor", "licensor_id"),
        Index("idx_contract_status", "status"),
    )

    contract_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    contract_number: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="Human-readable legal contract identifier (e.g. 'LIC-2026-WB-001')"
    )
    licensor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("licensors.licensor_id"),
        nullable=False,
        comment="Primary lead licensor"
    )
    title_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("titles.title_id"),
        nullable=True,
        comment="Single title ID if title-specific contract; NULL if catalog umbrella contract"
    )
    deal_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="SVOD_PRO_RATA",
        comment="Financial model: SVOD_PRO_RATA, FLAT_FEE, HYBRID_MG, AVOD_REVENUE_SHARE"
    )
    rev_share_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("70.00"),
        comment="Contractual revenue share percentage (e.g., 70.00%)"
    )
    technical_fee_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Platform infrastructure / CDN delivery deduction fee %"
    )
    effective_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )
    expiration_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )
    settlement_frequency: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="MONTHLY",
        comment="Settlement cycle: MONTHLY or QUARTERLY"
    )
    contract_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD"
    )
    territory_id: Mapped[Optional[str]] = mapped_column(
        String(3),
        ForeignKey("territories.country_code"),
        nullable=True,
        comment="Licence territory code (e.g. 'IN', 'US', 'SG', 'AE')"
    )
    exclusivity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="NON_EXCLUSIVE",
        comment="Exclusivity level: EXCLUSIVE, NON_EXCLUSIVE"
    )
    revenue_share_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="POOL_AND_AD",
        comment="Revenue share model: POOL_AND_AD, POOL_ONLY"
    )
    mg_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Minimum guarantee advance amount (0.00 = no MG)"
    )
    cap_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Royalty payout cap amount (0.00 = no cap)"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        comment="Status: DRAFT, ACTIVE, EXPIRED, TERMINATED, REJECTED"
    )

    @property
    def licence_id(self) -> str:
        return self.contract_id

    @licence_id.setter
    def licence_id(self, val: str) -> None:
        self.contract_id = val

    # Relationships
    primary_licensor: Mapped["Licensor"] = relationship("Licensor", back_populates="contracts")
    title: Mapped[Optional["Title"]] = relationship("Title")
    territory: Mapped[Optional["Territory"]] = relationship("Territory")
    windows: Mapped[List["LicenceWindow"]] = relationship(
        "LicenceWindow",
        back_populates="contract",
        cascade="all, delete-orphan"
    )
    splits: Mapped[List["LicensorSplit"]] = relationship(
        "LicensorSplit",
        back_populates="contract",
        cascade="all, delete-orphan"
    )
    minimum_guarantees: Mapped[List["MinimumGuarantee"]] = relationship(
        "MinimumGuarantee",
        back_populates="contract",
        cascade="all, delete-orphan"
    )
    payment_caps: Mapped[List["PaymentCap"]] = relationship(
        "PaymentCap",
        back_populates="contract",
        cascade="all, delete-orphan"
    )
    holdbacks: Mapped[List["Holdback"]] = relationship(
        "Holdback",
        back_populates="contract",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<LicenceContract(number='{self.contract_number}', deal='{self.deal_type}', status='{self.status}')>"


class MinimumGuarantee(Base, TimestampMixin):
    """
    Table 14: Minimum Guarantees (MG).
    Tracks upfront advances paid to licensors that must be recouped from earned royalties.
    """
    __tablename__ = "minimum_guarantees"
    __table_args__ = (
        CheckConstraint("mg_amount > 0", name="ck_mg_amount_positive"),
        CheckConstraint("unrecouped_balance >= 0", name="ck_unrecouped_non_negative"),
        CheckConstraint(
            "unrecouped_balance <= mg_amount",
            name="ck_unrecouped_le_mg_amount"
        ),
        Index("idx_mg_contract", "contract_id"),
        Index("idx_mg_status", "status"),
    )

    mg_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("licence_contracts.contract_id", ondelete="CASCADE"),
        nullable=False
    )
    mg_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Total upfront advance amount paid"
    )
    unrecouped_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Current outstanding balance remaining to be recouped"
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD"
    )
    recoupment_scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="CROSS_COLLATERALIZED",
        comment="CROSS_COLLATERALIZED, TITLE_SPECIFIC, or TERRITORY_SPECIFIC"
    )
    effective_from: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )
    effective_to: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        comment="ACTIVE, FULLY_RECOUPED, FORFEITED, EXPIRED"
    )

    # Relationships
    contract: Mapped["LicenceContract"] = relationship("LicenceContract", back_populates="minimum_guarantees")
    recoupment_records: Mapped[List["RecoupmentRecord"]] = relationship(
        "RecoupmentRecord",
        back_populates="minimum_guarantee"
    )

    def __repr__(self) -> str:
        return f"<MinimumGuarantee(contract='{self.contract_id}', mg={self.mg_amount}, balance={self.unrecouped_balance})>"


class PaymentCap(Base, TimestampMixin):
    """
    Table 16: Payment Caps.
    Restricts maximum royalty liability for a given contract over specified time intervals.
    """
    __tablename__ = "payment_caps"
    __table_args__ = (
        CheckConstraint("cap_amount > 0", name="ck_cap_amount_positive"),
        Index("idx_cap_contract", "contract_id"),
    )

    cap_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("licence_contracts.contract_id", ondelete="CASCADE"),
        nullable=False
    )
    cap_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Maximum allowable disbursement limit"
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD"
    )
    cap_period: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MONTHLY",
        comment="Period limit applies to: MONTHLY, ANNUAL, or LIFETIME"
    )
    is_hard_cap: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="If True, excess royalty is permanently forfeit; if False, deferred to next period"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Relationships
    contract: Mapped["LicenceContract"] = relationship("LicenceContract", back_populates="payment_caps")

    def __repr__(self) -> str:
        return f"<PaymentCap(contract='{self.contract_id}', cap={self.cap_amount} {self.currency}, period='{self.cap_period}')>"
