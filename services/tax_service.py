"""
Tax Service Module.
Implements BR-09 (Withholding Tax / TDS and International Treaty Rates).

Business Rules:
- Indian resident licensors: 10.00% standard domestic TDS.
- Foreign resident licensors: 20.00% statutory foreign withholding tax.
- If a Double Tax Avoidance Agreement (DTAA) treaty rate is registered for the foreign licensor,
  the concessional treaty rate overrides the 20.00% statutory rate.
- Withholding tax is applied to the net payable amount after MG recoupment and cap retention.
- TDS amount is rounded to paise using ROUND_HALF_UP.
- Net Payable = Payable Before TDS - TDS Amount.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Union

STANDARD_INDIAN_TDS_RATE: Decimal = Decimal("10.00")
STANDARD_FOREIGN_TDS_RATE: Decimal = Decimal("20.00")
CURRENCY_QUANTUM: Decimal = Decimal("0.01")


@dataclass(frozen=True)
class TaxCalculationResult:
    """Encapsulates the withholding tax assessment result for a licensor settlement."""
    licensor_id: str
    payable_before_tds: Decimal
    is_indian: bool
    treaty_rate_applied: bool
    tds_pct: Decimal
    tds_amount: Decimal
    net_payable: Decimal

    def to_dict(self) -> dict:
        return {
            "licensor_id": self.licensor_id,
            "payable_before_tds": f"{self.payable_before_tds:.2f}",
            "is_indian": self.is_indian,
            "treaty_rate_applied": self.treaty_rate_applied,
            "tds_pct": f"{self.tds_pct:.2f}",
            "tds_amount": f"{self.tds_amount:.2f}",
            "net_payable": f"{self.net_payable:.2f}",
        }


class TaxService:
    """Computes statutory and treaty-based withholding tax deductions."""

    @staticmethod
    def determine_tds_rate(
        is_indian: bool,
        treaty_tds_pct: Optional[Union[Decimal, str]] = None,
    ) -> Decimal:
        """
        Determines the applicable withholding tax rate:
        - Domestic (Indian): 10.00%
        - Foreign with DTAA treaty: Concession treaty rate (e.g. 15.00%)
        - Foreign without treaty: 20.00%
        """
        if is_indian:
            return STANDARD_INDIAN_TDS_RATE

        if treaty_tds_pct is not None and str(treaty_tds_pct).strip():
            rate = Decimal(str(treaty_tds_pct).strip())
            if rate < Decimal("0.00") or rate > Decimal("100.00"):
                raise ValueError(f"Treaty TDS rate out of bounds [0, 100]: {rate}")
            return rate

        return STANDARD_FOREIGN_TDS_RATE

    @classmethod
    def calculate_tax(
        cls,
        licensor_id: str,
        payable_before_tds: Union[Decimal, str],
        is_indian: bool,
        treaty_tds_pct: Optional[Union[Decimal, str]] = None,
    ) -> TaxCalculationResult:
        """
        Calculates withholding tax amount and net payable for a given gross entitlement.
        """
        amount = Decimal(str(payable_before_tds))
        if amount < Decimal("0.00"):
            raise ValueError(f"Payable amount cannot be negative: {amount}")

        tds_pct = cls.determine_tds_rate(is_indian, treaty_tds_pct)
        treaty_applied = (not is_indian) and (treaty_tds_pct is not None and bool(str(treaty_tds_pct).strip()))

        if amount == Decimal("0.00"):
            tds_amount = Decimal("0.00")
            net_payable = Decimal("0.00")
        else:
            tds_amount = (amount * tds_pct / Decimal("100")).quantize(CURRENCY_QUANTUM, rounding=ROUND_HALF_UP)
            net_payable = amount - tds_amount

        return TaxCalculationResult(
            licensor_id=licensor_id,
            payable_before_tds=amount,
            is_indian=is_indian,
            treaty_rate_applied=treaty_applied,
            tds_pct=tds_pct,
            tds_amount=tds_amount,
            net_payable=net_payable,
        )
