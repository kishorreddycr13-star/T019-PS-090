"""
Recoupment Service Module.
Implements BR-07 (Recoupment Waterfall against Minimum Guarantees).

Business Rules:
- Revenue share is applied first to recoup unrecouped Minimum Guarantee advances.
- Recouped Amount = min(Gross Share, Outstanding MG Balance)
- Remaining MG Balance = Outstanding MG Balance - Recouped Amount
- Only excess revenue share exceeding the unrecouped MG balance is additionally payable.
- Zero recoupment when outstanding MG balance is zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Union


@dataclass(frozen=True)
class RecoupmentResult:
    """Encapsulates the calculation output of an MG recoupment step."""
    gross_share: Decimal
    outstanding_mg_before: Decimal
    recouped_amount: Decimal
    outstanding_mg_after: Decimal
    excess_payable: Decimal

    def to_dict(self) -> dict:
        return {
            "gross_share": f"{self.gross_share:.2f}",
            "outstanding_mg_before": f"{self.outstanding_mg_before:.2f}",
            "recouped_amount": f"{self.recouped_amount:.2f}",
            "outstanding_mg_after": f"{self.outstanding_mg_after:.2f}",
            "excess_payable": f"{self.excess_payable:.2f}",
        }


class RecoupmentService:
    """Applies gross royalty revenue against outstanding Minimum Guarantee advances."""

    @staticmethod
    def calculate_recoupment(
        gross_share: Union[Decimal, str],
        outstanding_mg: Union[Decimal, str],
    ) -> RecoupmentResult:
        """
        Executes recoupment waterfall:
        - Recouped = min(Gross, Outstanding MG)
        - Excess = max(0, Gross - Outstanding MG)
        """
        gross = Decimal(str(gross_share))
        mg_bal = Decimal(str(outstanding_mg))

        if gross < Decimal("0.00"):
            raise ValueError(f"Gross share cannot be negative: {gross}")
        if mg_bal < Decimal("0.00"):
            raise ValueError(f"Outstanding MG balance cannot be negative: {mg_bal}")

        recouped = min(gross, mg_bal)
        mg_after = mg_bal - recouped
        excess = max(Decimal("0.00"), gross - mg_bal)

        return RecoupmentResult(
            gross_share=gross,
            outstanding_mg_before=mg_bal,
            recouped_amount=recouped,
            outstanding_mg_after=mg_after,
            excess_payable=excess,
        )

    @classmethod
    def calculate_payable_after_mg(
        cls,
        gross_share: Union[Decimal, str],
        outstanding_mg_before: Union[Decimal, str],
        is_new_mg_payout: bool = False,
        mg_advance_paid: Union[Decimal, str] = Decimal("0.00"),
    ) -> Decimal:
        """
        Calculates payable before TDS under the MG waterfall:
        - In Month 1 with new advance: payable = mg_advance_paid + max(0, gross - total_mg)
        - In subsequent months: payable = max(0, gross - outstanding_mg_before)
        """
        gross = Decimal(str(gross_share))
        mg_bal = Decimal(str(outstanding_mg_before))
        mg_adv = Decimal(str(mg_advance_paid))

        if is_new_mg_payout:
            excess = max(Decimal("0.00"), gross - mg_bal)
            return mg_adv + excess
        else:
            return max(Decimal("0.00"), gross - mg_bal)
