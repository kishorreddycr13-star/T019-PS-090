"""
Licensor and Licensor Split Models.
Covers Tables 2 and 3. Supports Indian and Foreign licensors, country info, and tax treaties.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    String,
    Numeric,
    Boolean,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from database.base import Base, TimestampMixin


class Licensor(Base, TimestampMixin):
    """
    Table 2: Licensors (Studios, Production Houses, Distributors).
    Stores corporate legal entities, country of residency, and DTAA treaty TDS rates.
    """
    __tablename__ = "licensors"
    __table_args__ = (
        Index("idx_licensor_country", "country_code"),
    )

    licensor_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: f"LIC-{str(uuid.uuid4())[:6].upper()}"
    )
    legal_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Registered corporate legal name"
    )
    trade_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Doing Business As (DBA) / Brand name"
    )
    country: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="India",
        comment="Country of tax residency (e.g. 'India', 'United States', 'United Kingdom')"
    )
    country_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("territories.country_code"),
        nullable=False,
        default="IN",
        comment="ISO country code"
    )
    is_indian: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Indian domestic resident flag (TDS 10% if true, 20% if false unless treaty rate)"
    )
    treaty_tds_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="DTAA treaty concession withholding tax percentage (e.g. 10.00)"
    )
    tax_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Tax Identification Number (EIN, PAN, GSTIN)"
    )
    settlement_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        comment="ISO-4217 Currency requested for contract payouts"
    )
    iban_swift: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Bank account IBAN or SWIFT routing identifier"
    )
    contact_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Royalty statement notification recipient"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Hybrid alias
    @property
    def licensor_name(self) -> str:
        return self.legal_name

    @licensor_name.setter
    def licensor_name(self, val: str) -> None:
        self.legal_name = val

    # Relationships
    splits: Mapped[List["LicensorSplit"]] = relationship(
        "LicensorSplit",
        back_populates="licensor"
    )
    contracts: Mapped[List["LicenceContract"]] = relationship(
        "LicenceContract",
        back_populates="primary_licensor"
    )

    def __repr__(self) -> str:
        return f"<Licensor(id='{self.licensor_id}', name='{self.legal_name}', country='{self.country}')>"


class LicensorSplit(Base, TimestampMixin):
    """
    Table 3: Licensor Splits (Contract-Level).
    Allocates gross title royalties among multiple co-producers and talent residuals.
    """
    __tablename__ = "licensor_splits"
    __table_args__ = (
        CheckConstraint(
            "split_percentage > 0 AND split_percentage <= 100.00",
            name="ck_split_percentage_range"
        ),
        UniqueConstraint(
            "contract_id", "licensor_id", "stakeholder_role",
            name="uq_contract_licensor_role"
        ),
        Index("idx_split_contract", "contract_id"),
    )

    split_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("licence_contracts.contract_id", ondelete="CASCADE"),
        nullable=False
    )
    licensor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("licensors.licensor_id"),
        nullable=False
    )
    stakeholder_role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="STUDIO",
        comment="Role: STUDIO, PRODUCER, TALENT_RESIDUAL, SALES_AGENT, FINANCIER"
    )
    split_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Stakeholder royalty allocation percentage"
    )
    is_primary_payee: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # Relationships
    contract: Mapped["LicenceContract"] = relationship("LicenceContract", back_populates="splits")
    licensor: Mapped["Licensor"] = relationship("Licensor", back_populates="splits")

    @validates("split_percentage")
    def validate_split_percentage(self, key: str, value: Decimal | float | int) -> Decimal:
        dec_val = Decimal(str(value))
        if dec_val <= Decimal("0.00") or dec_val > Decimal("100.00"):
            raise ValueError(f"Invalid split_percentage {dec_val}%. Must be strictly between 0.01% and 100.00%.")
        return dec_val

    def __repr__(self) -> str:
        return f"<LicensorSplit(contract='{self.contract_id}', role='{self.stakeholder_role}', pct={self.split_percentage}%)>"
