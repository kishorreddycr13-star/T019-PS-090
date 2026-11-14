"""
Licensor Split Validator Module.
Enforces that for any title, licensor split percentages sum to exactly 100.00%.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Sequence, Any

from validators.exceptions import SplitValidationError


def validate_title_splits(splits: Sequence[Dict[str, Any]], title_id: str) -> None:
    """
    Validates a set of licensor splits for a title:
    1. At least one split must exist.
    2. No duplicate licensor entries for the same title.
    3. Each split must be strictly between 0.01% and 100.00%.
    4. The total sum of all split percentages must equal exactly 100.00%.
    """
    if not splits:
        raise SplitValidationError(f"Title '{title_id}' must have at least one licensor split defined.")

    seen_licensors = set()
    total_percentage = Decimal("0.00")

    for item in splits:
        licensor_id = item.get("licensor_id", "").strip()
        if not licensor_id:
            raise SplitValidationError("Each split entry must specify a valid 'licensor_id'.")

        if licensor_id in seen_licensors:
            raise SplitValidationError(
                f"Duplicate split entry for licensor '{licensor_id}' on title '{title_id}'."
            )
        seen_licensors.add(licensor_id)

        raw_pct = item.get("split_pct") or item.get("split_percentage")
        if raw_pct is None:
            raise SplitValidationError(f"Missing split percentage for licensor '{licensor_id}'.")

        try:
            pct = Decimal(str(raw_pct))
        except Exception:
            raise SplitValidationError(f"Invalid numeric percentage value '{raw_pct}'.")

        if pct <= Decimal("0.00") or pct > Decimal("100.00"):
            raise SplitValidationError(
                f"Invalid split percentage {pct}% for licensor '{licensor_id}'. "
                f"Must be strictly between 0.01% and 100.00%."
            )

        total_percentage += pct

    if total_percentage != Decimal("100.00"):
        raise SplitValidationError(
            f"Invalid split allocation for title '{title_id}'. "
            f"The sum of all splits is {total_percentage}%, but must equal exactly 100.00%."
        )
