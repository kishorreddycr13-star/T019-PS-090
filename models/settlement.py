"""
Monthly Settlements, Recoupment Records, and Payment Transactions Models.
Covers Tables 15, 18, and 19. Implements historical period lock, MG waterfalls, and remittance tracking.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

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


class MonthlySettlement(Base, TimestampMixin):
    """
    Table 18: Monthly Settlements.
    Maintains historical audited settlement calculations per contract/licensor/period.
    Supports immutable period locking (BR-12).
    """
    __tablename__ = "monthly_settlements"
    __table_args__ = (
        CheckConstraint("gross_royalty_amount >= 0", name="ck_gross_royalty_non_negative"),
        CheckConstraint("mg_recouped_amount >= 0", name="ck_mg_recouped_non_negative"),
        CheckConstraint("net_payable_amount >= 0", name="ck_net_payable_non_negative"),
        CheckConstraint("withholding_tax_amount >= 0", name="ck_wht_amount_non_negative"),
        UniqueConstraint("settlement_run_number", "contract_id", "licensor_id", name="uq_settlement_run_entity"),
        Index("idx_settlement_period_status", "period_key", "status"),
        Index("idx_settlement_contract", "contract_id"),
        Index("idx_settlement_licensor", "licensor_id"),
    )

    settlement_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    settlement_run_number: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Settlement execution batch number (e.g., 'RUN-202610-001')"
    )
    period_key: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        comment="Settlement month in 'YYYY-MM' format"
    )
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("licence_contracts.contract_id"),
        nullable=False
    )
    licensor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("licensors.licensor_id"),
        nullable=False
    )
    title_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("titles.title_id"),
        nullable=True,
        comment="Title ID if title-level statement line item; NULL if contract-level roll-up"
    )
    total_qualified_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Audited qualified viewership seconds for this licensor/title"
    )
    catalog_total_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total platform catalog qualified seconds in same tier/period"
    )
    consumption_share_ratio: Mapped[Decimal] = mapped_column(
        Numeric(12, 8),
        nullable=False,
        default=Decimal("0.00000000"),
        comment="Pro-rata consumption proportion (total_qualified_seconds / catalog_total_seconds)"
    )
    distributable_pool_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Total pool amount allocated from"
    )
    gross_royalty_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Earned royalty prior to deductions and recoupment"
    )
    split_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
        default=Decimal("100.00"),
        comment="Co-licensor split percentage"
    )
    mg_paid: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Minimum Guarantee advance disbursed in current period"
    )
    mg_recouped_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Portion credited toward outstanding Minimum Guarantee advance"
    )
    mg_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Outstanding unrecouped MG advance remaining after current period"
    )
    cap_retained: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Royalty earnings retained exceeding the contractual payment cap"
    )
    payable_before_tds: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Gross royalty payable prior to withholding tax deduction"
    )
    tds_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
        default=Decimal("10.00"),
        comment="Applicable withholding tax percentage (statutory or treaty)"
    )
    withholding_tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Withholding tax deducted at treaty rate"
    )
    net_payable_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Final disbursable balance: gross - mg_recouped - wht"
    )
    settlement_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD"
    )
    fx_rate_applied: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
        default=Decimal("1.000000"),
        comment="Official EOD Forex rate locked at period closing"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DRAFT",
        comment="Lifecycle: DRAFT, APPROVED, LOCKED, DISPUTED"
    )
    locked_at_utc: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        comment="Timestamp when settlement run was cryptographically locked (immutable)"
    )
    cryptographic_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 seal guaranteeing settlement calculation integrity"
    )

    # Convenience Alias Properties
    @property
    def month(self) -> str:
        return self.period_key

    @property
    def licence_id(self) -> str:
        return self.contract_id

    @property
    def gross_share(self) -> Decimal:
        return self.gross_royalty_amount

    @property
    def recouped(self) -> Decimal:
        return self.mg_recouped_amount

    @property
    def tds(self) -> Decimal:
        return self.withholding_tax_amount

    @property
    def net_payable(self) -> Decimal:
        return self.net_payable_amount

    # Relationships
    contract: Mapped["LicenceContract"] = relationship("LicenceContract")
    licensor: Mapped["Licensor"] = relationship("Licensor")
    title: Mapped[Optional["Title"]] = relationship("Title")
    recoupment_records: Mapped[List["RecoupmentRecord"]] = relationship(
        "RecoupmentRecord",
        back_populates="settlement"
    )
    payment_transactions: Mapped[List["PaymentTransaction"]] = relationship(
        "PaymentTransaction",
        back_populates="settlement"
    )

    def __repr__(self) -> str:
        return f"<MonthlySettlement(period='{self.period_key}', licensor='{self.licensor_id}', payable={self.net_payable_amount} {self.settlement_currency}, status='{self.status}')>"


class RecoupmentRecord(Base, TimestampMixin):
    """
    Table 15: Recoupment Records.
    Historical tracking of Minimum Guarantee drawdowns and cumulative balance amortizations.
    """
    __tablename__ = "recoupment_records"
    __table_args__ = (
        CheckConstraint("opening_unrecouped_balance >= 0", name="ck_opening_balance_non_negative"),
        CheckConstraint("amount_recouped >= 0", name="ck_amount_recouped_non_negative"),
        CheckConstraint("closing_unrecouped_balance >= 0", name="ck_closing_balance_non_negative"),
        Index("idx_recoupment_mg_period", "mg_id", "period_key"),
    )

    recoupment_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    mg_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("minimum_guarantees.mg_id"),
        nullable=False
    )
    settlement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("monthly_settlements.settlement_id"),
        nullable=False
    )
    period_key: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        comment="Settlement month in 'YYYY-MM' format"
    )
    opening_unrecouped_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Outstanding MG balance prior to this period's recoupment"
    )
    amount_recouped: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Royalty amount applied to reduce MG in this run"
    )
    closing_unrecouped_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Remaining outstanding MG balance post-settlement"
    )

    # Relationships
    minimum_guarantee: Mapped["MinimumGuarantee"] = relationship("MinimumGuarantee", back_populates="recoupment_records")
    settlement: Mapped["MonthlySettlement"] = relationship("MonthlySettlement", back_populates="recoupment_records")

    def __repr__(self) -> str:
        return f"<RecoupmentRecord(period='{self.period_key}', recouped={self.amount_recouped}, closing={self.closing_unrecouped_balance})>"


class PaymentTransaction(Base, TimestampMixin):
    """
    Table 19: Payment Transactions.
    Maintains financial remittance records, disbursement methods, and banking execution statuses.
    """
    __tablename__ = "payment_transactions"
    __table_args__ = (
        CheckConstraint("disbursed_amount > 0", name="ck_disbursed_positive"),
        Index("idx_payment_ref", "payment_reference"),
        Index("idx_payment_status", "payment_status"),
    )

    transaction_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    settlement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("monthly_settlements.settlement_id"),
        nullable=False
    )
    licensor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("licensors.licensor_id"),
        nullable=False
    )
    payment_reference: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="Unique banking remittance instruction / wire reference (e.g. 'PAY-202611-0042')"
    )
    disbursed_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        comment="Net cash amount disbursed to beneficiary"
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD"
    )
    payment_method: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="WIRE_TRANSFER",
        comment="Disbursement channel: WIRE_TRANSFER, ACH, SWIFT, SEPA"
    )
    payment_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        comment="Status: PENDING, PROCESSING, SETTLED, FAILED, ON_HOLD"
    )
    disbursed_at_utc: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        comment="Confirmation timestamp from corporate treasury / bank"
    )

    # Relationships
    settlement: Mapped["MonthlySettlement"] = relationship("MonthlySettlement", back_populates="payment_transactions")
    licensor: Mapped["Licensor"] = relationship("Licensor")

    def __repr__(self) -> str:
        return f"<PaymentTransaction(ref='{self.payment_reference}', amount={self.disbursed_amount} {self.currency}, status='{self.payment_status}')>"
