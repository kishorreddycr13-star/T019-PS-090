"""
Payment Cap Service Module.
Implements BR-08 (Contractual Payment Cap Enforcement).

Business Rules:
- A licence contract may specify a maximum cumulative payment cap.
- A cap of 0.00 signifies an unlimited licence (no cap).
- Cumulative payments under the licence are tracked across settlement months.
- Headroom = max(0.00, Contract Cap - Cumulative Paid).
- When payable amount exceeds headroom:
  * Payable Before TDS is reduced to the remaining headroom.
  * Excess is retained by the platform (cap_retained = Amount - Headroom).
  * Licence status transitions to 'CAPPED'.
  * Subsequent months generate zero additional payable amounts (payable = 0.00, cap_retained = gross).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional, Union


@dataclass(frozen=True)
class CapEvaluationResult:
    """Encapsulates the calculation output of payment cap enforcement."""
    licence_id: str
    payable_before_cap: Decimal
    headroom_before: Decimal
    payable_after_cap: Decimal
    cap_retained: Decimal
    cumulative_paid_after: Decimal
    is_capped: bool
    status: str  # "SETTLED" or "CAPPED"

    def to_dict(self) -> dict:
        return {
            "licence_id": self.licence_id,
            "payable_before_cap": f"{self.payable_before_cap:.2f}",
            "headroom_before": f"{self.headroom_before:.2f}",
            "payable_after_cap": f"{self.payable_after_cap:.2f}",
            "cap_retained": f"{self.cap_retained:.2f}",
            "cumulative_paid_after": f"{self.cumulative_paid_after:.2f}",
            "is_capped": self.is_capped,
            "status": self.status,
        }


class CapService:
    """Manages cumulative payment ceiling tracking and cap retention enforcement."""

    def __init__(self) -> None:
        # licence_id -> cumulative paid before TDS
        self.cumulative_paid_cap: Dict[str, Decimal] = {}
        # licence_id -> whether cap has been fully reached
        self.is_capped_map: Dict[str, bool] = {}

    def get_cumulative_paid(self, licence_id: str) -> Decimal:
        """Returns the cumulative payments made to date under this licence."""
        return self.cumulative_paid_cap.get(licence_id, Decimal("0.00"))

    def get_remaining_headroom(self, licence_id: str, contract_cap: Union[Decimal, str]) -> Optional[Decimal]:
        """Returns the remaining headroom under the cap, or None if unlimited (cap <= 0)."""
        cap = Decimal(str(contract_cap))
        if cap <= Decimal("0.00"):
            return None
        cum = self.get_cumulative_paid(licence_id)
        return max(Decimal("0.00"), cap - cum)

    def is_licence_capped(self, licence_id: str) -> bool:
        """Returns whether the licence has reached its cap limit."""
        return self.is_capped_map.get(licence_id, False)

    def apply_payment_cap(
        self,
        licence_id: str,
        payable_amount: Union[Decimal, str],
        contract_cap: Union[Decimal, str],
    ) -> CapEvaluationResult:
        """
        Applies contractual payment cap to the candidate payable amount:
        - If cap == 0: unlimited payment allowed.
        - If payable > headroom: pays remaining headroom; retains the excess; marks CAPPED.
        - If payable <= headroom: pays full amount; updates cumulative paid.
        """
        amount = Decimal(str(payable_amount))
        cap = Decimal(str(contract_cap))

        if amount < Decimal("0.00"):
            raise ValueError(f"Payable amount cannot be negative: {amount}")

        # Case 1: Unlimited Cap
        if cap <= Decimal("0.00"):
            cum = self.get_cumulative_paid(licence_id)
            new_cum = cum + amount
            self.cumulative_paid_cap[licence_id] = new_cum
            return CapEvaluationResult(
                licence_id=licence_id,
                payable_before_cap=amount,
                headroom_before=Decimal("999999999.99"),
                payable_after_cap=amount,
                cap_retained=Decimal("0.00"),
                cumulative_paid_after=new_cum,
                is_capped=False,
                status="SETTLED",
            )

        # Case 2: Capped Contract
        cum = self.get_cumulative_paid(licence_id)
        headroom = max(Decimal("0.00"), cap - cum)

        if amount > headroom:
            payable = headroom
            cap_retained = amount - headroom
            new_cum = cap
            self.cumulative_paid_cap[licence_id] = cap
            self.is_capped_map[licence_id] = True
            status = "CAPPED"
            is_capped = True
        else:
            payable = amount
            cap_retained = Decimal("0.00")
            new_cum = cum + payable
            self.cumulative_paid_cap[licence_id] = new_cum
            is_capped = self.is_capped_map.get(licence_id, False) or (new_cum >= cap)
            self.is_capped_map[licence_id] = is_capped
            status = "CAPPED" if is_capped else "SETTLED"

        return CapEvaluationResult(
            licence_id=licence_id,
            payable_before_cap=amount,
            headroom_before=headroom,
            payable_after_cap=payable,
            cap_retained=cap_retained,
            cumulative_paid_after=new_cum,
            is_capped=is_capped,
            status=status,
        )

    def reset(self) -> None:
        """Clears all cap tracking states."""
        self.cumulative_paid_cap.clear()
        self.is_capped_map.clear()
