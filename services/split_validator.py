"""
Licensor Split Validation Service.
Enforces business rules ensuring that for any contract, stakeholder royalty splits sum to exactly 100.00%
and exactly one primary payee is designated.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Sequence
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from models.licensor import LicensorSplit


class SplitValidationError(ValueError):
    """Raised when licensor splits violate contractual split business rules."""
    pass


def validate_contract_splits(splits: Sequence[LicensorSplit], contract_id: str) -> None:
    """
    Validates a set of licensor splits for a contract:
    1. At least one split must exist.
    2. Sum of split percentages must equal exactly 100.00%.
    3. Exactly one primary payee must be designated.
    4. Each individual split must be strictly between 0.01% and 100.00%.
    """
    if not splits:
        raise SplitValidationError(f"Contract '{contract_id}' has no licensor splits defined.")

    total_percentage = Decimal("0.00")
    primary_payee_count = 0

    for split in splits:
        pct = Decimal(str(split.split_percentage))
        if pct <= Decimal("0.00") or pct > Decimal("100.00"):
            raise SplitValidationError(
                f"Split ID '{split.split_id}' for contract '{contract_id}' has invalid percentage {pct}%. "
                f"Must be between 0.01% and 100.00%."
            )
        total_percentage += pct
        if split.is_primary_payee:
            primary_payee_count += 1

    if total_percentage != Decimal("100.00"):
        raise SplitValidationError(
            f"Invalid split allocation for contract '{contract_id}'. "
            f"Total split sum is {total_percentage}%, but must equal exactly 100.00%."
        )

    if primary_payee_count != 1:
        raise SplitValidationError(
            f"Contract '{contract_id}' has {primary_payee_count} primary payees designated. "
            f"Exactly 1 primary payee must be flagged."
        )


def validate_contract_splits_in_db(session: Session, contract_id: str) -> None:
    """Queries the database and validates all existing splits for a contract."""
    stmt = select(LicensorSplit).where(LicensorSplit.contract_id == contract_id)
    splits = session.scalars(stmt).all()
    validate_contract_splits(splits, contract_id)
