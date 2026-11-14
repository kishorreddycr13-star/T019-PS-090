"""
Revenue Validation Module.
Enforces business invariants, monetary non-negativity, revenue-share model checks,
and ratio ceiling validation for financial calculations.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Dict, List, Optional, Set, Union

from validators.exceptions import ValidationError

PERIOD_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
VALID_REV_SHARE_TYPES: Set[str] = {"POOL_AND_AD", "POOL_ONLY"}


class RevenueValidationError(ValidationError):
    """Raised when financial inputs or allocation calculations violate business rules."""
    def __init__(self, message: str, field: str = "revenue", code: str = "ERR_REVENUE_VALIDATION") -> None:
        super().__init__(field=field, message=message, code=code)


def validate_period_format(period_key: str) -> None:
    """Validates accounting period format (YYYY-MM)."""
    if not period_key or not PERIOD_REGEX.match(period_key.strip()):
        raise RevenueValidationError(
            f"Invalid accounting period format '{period_key}'. Expected 'YYYY-MM'.",
            field="period_key",
            code="ERR_INVALID_PERIOD_FORMAT"
        )


def validate_revenue_amount(amount: Union[Decimal, float, int, str], field_name: str = "revenue") -> Decimal:
    """Validates that a monetary input is non-negative and convertible to Decimal."""
    try:
        val = Decimal(str(amount))
    except Exception as e:
        raise RevenueValidationError(
            f"Invalid monetary value for {field_name}: '{amount}'. Must be a valid numeric amount.",
            field=field_name,
            code="ERR_INVALID_MONETARY_VALUE"
        ) from e

    if val < Decimal("0.00"):
        raise RevenueValidationError(
            f"{field_name.replace('_', ' ').title()} cannot be negative: {val}",
            field=field_name,
            code="ERR_NEGATIVE_REVENUE"
        )
    return val


def validate_revenue_share_type(rev_type: str) -> str:
    """Ensures revenue share type is supported."""
    clean = rev_type.strip().upper()
    if clean not in VALID_REV_SHARE_TYPES:
        raise RevenueValidationError(
            f"Unsupported revenue-share type '{rev_type}'. Allowed options: {sorted(VALID_REV_SHARE_TYPES)}",
            field="revenue_share_type",
            code="ERR_INVALID_REV_SHARE_TYPE"
        )
    return clean


def validate_ratio_bounds(ratio: Decimal, name: str = "ratio") -> None:
    """Ensures a ratio is between 0.0000 and 1.0000 (allowing 0.0001 for half-up rounding edge)."""
    if ratio < Decimal("0.0000") or ratio > Decimal("1.0005"):
        raise RevenueValidationError(
            f"Calculated {name} {ratio} exceeds valid proportion bounds [0.0000, 1.0000].",
            field=name,
            code="ERR_RATIO_OUT_OF_BOUNDS"
        )


def validate_title_share_totals(
    pool_share: Decimal,
    ad_share: Decimal,
    total_share: Decimal,
    title_id: str,
) -> None:
    """Validates that title_share matches the sum of pool_share and ad_share exactly."""
    expected = pool_share + ad_share
    if total_share != expected:
        raise RevenueValidationError(
            f"Title share mismatch for {title_id}: total ({total_share}) != pool ({pool_share}) + ad ({ad_share})",
            field="title_share",
            code="ERR_TITLE_SHARE_SUM_MISMATCH"
        )
