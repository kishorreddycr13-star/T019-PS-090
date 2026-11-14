"""
Licensor Validator Module.
Validates corporate name, country residency, and tax treaty parameters.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from validators.exceptions import ValidationError


def validate_licensor_input(
    licensor_id: str,
    licensor_name: str,
    country: str,
    is_indian: bool,
    treaty_tds_pct: Optional[Decimal] = None,
) -> None:
    """Validates licensor entity registration attributes."""
    if not licensor_id or not licensor_id.strip():
        raise ValidationError("Licensor ID cannot be blank.", field="licensor_id")

    if not licensor_name or not licensor_name.strip():
        raise ValidationError("Licensor legal name cannot be blank.", field="licensor_name")

    if not country or not country.strip():
        raise ValidationError("Country information cannot be blank.", field="country")

    if treaty_tds_pct is not None:
        dec_val = Decimal(str(treaty_tds_pct))
        if dec_val < Decimal("0.00") or dec_val > Decimal("100.00"):
            raise ValidationError(
                f"Treaty TDS percentage must be between 0.00% and 100.00% (received: {dec_val}%).",
                field="treaty_tds_pct"
            )
