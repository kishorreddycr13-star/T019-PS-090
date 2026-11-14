"""
Licensor Split Service Module.
Implements BR-10 (Co-Licensor Allocation and Rounding Residue Attribution).

Business Rules:
- Title revenue is partitioned among co-licensors according to registered split percentages.
- Split percentages for a title must sum to exactly 100.00%.
- Individual licensor allocations are floored to the paisa (2 decimal places).
- Any fractional rounding residue (e.g. 1 paisa) is attributed to the co-licensor with the largest registered share.
- In case of a tie for largest share, the first declared licensor deterministically receives the residue.
- Zero financial leakage: Sum of allocated parts == Original total amount down to the exact paisa.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from typing import Any, Dict, List, Sequence, Union

from validators.exceptions import SplitValidationError


def floor_paisa(val: Union[Decimal, float, int, str]) -> Decimal:
    """Floors decimal monetary amount to 2 decimal places (paise)."""
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_FLOOR)


class LicensorSplitService:
    """Allocates title gross revenue shares among co-licensors with zero rounding discrepancy."""

    @staticmethod
    def validate_splits_total(splits: Sequence[Dict[str, Any]], title_id: str = "TITLE") -> None:
        """Ensures co-licensor split percentages sum to exactly 100.00%."""
        if not splits:
            raise SplitValidationError(
                title_id=title_id,
                total_pct=Decimal("0.00"),
                message=f"No licensor splits registered for title '{title_id}'."
            )
        total_pct = sum(Decimal(str(s["split_pct"])) for s in splits)
        if total_pct != Decimal("100.00"):
            raise SplitValidationError(
                title_id=title_id,
                total_pct=total_pct,
                message=f"Co-licensor splits for title '{title_id}' sum to {total_pct:.2f}%, but must equal exactly 100.00%."
            )

    @classmethod
    def allocate_splits(
        cls,
        total_amount: Union[Decimal, str],
        splits: Sequence[Dict[str, Any]],
        title_id: str = "TITLE",
    ) -> Dict[str, Decimal]:
        """
        Distributes total_amount among co-licensors:
        - Floors each allocation to the paisa.
        - Adds remaining fractional residue to the licensor with the largest split percentage.
        """
        amount = Decimal(str(total_amount))
        if amount < Decimal("0.00"):
            raise ValueError(f"Total allocation amount cannot be negative: {amount}")

        if not splits:
            raise ValueError(f"Cannot allocate revenue: no splits provided for title '{title_id}'.")

        # Single licensor optimization
        if len(splits) == 1:
            return {splits[0]["licensor_id"]: amount}

        cls.validate_splits_total(splits, title_id=title_id)

        # Floor each licensor's share to paisa
        floored_parts: Dict[str, Decimal] = {}
        for sp in splits:
            pct = Decimal(str(sp["split_pct"]))
            val = floor_paisa(amount * pct / Decimal("100"))
            floored_parts[sp["licensor_id"]] = val

        # Calculate rounding residue
        sum_floored = sum(floored_parts.values())
        residue = amount - sum_floored

        # Find licensor with largest split percentage (deterministic in case of tie)
        largest_sp = max(splits, key=lambda s: Decimal(str(s["split_pct"])))
        floored_parts[largest_sp["licensor_id"]] += residue

        return floored_parts
