"""
Minimum Guarantee (MG) Service Module.
Implements BR-07 (Minimum Guarantee Advances and Tracking).

Business Rules:
- A licence with an MG receives the MG advance in month 1 of its first availability window.
- Tracks total MG paid and outstanding MG balance per licence across settlement months.
- Prevents duplicate MG advances.
- Subsequent monthly revenue shares are recouped against the unrecouped balance.
- MG is never clawed back if revenue is insufficient to recoup it.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Set, Union


@dataclass
class MGRecord:
    """Tracks the Minimum Guarantee state for a specific licence contract."""
    licence_id: str
    contract_mg: Decimal
    total_mg_paid: Decimal = Decimal("0.00")
    outstanding_balance: Decimal = Decimal("0.00")
    is_paid_out: bool = False
    first_window_month: str = ""

    def to_dict(self) -> dict:
        return {
            "licence_id": self.licence_id,
            "contract_mg": f"{self.contract_mg:.2f}",
            "total_mg_paid": f"{self.total_mg_paid:.2f}",
            "outstanding_balance": f"{self.outstanding_balance:.2f}",
            "is_paid_out": self.is_paid_out,
            "first_window_month": self.first_window_month,
        }


class MGService:
    """Manages Minimum Guarantee accounting, advance distributions, and cross-month balances."""

    def __init__(self, windows_map: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
        self.windows_map: Dict[str, List[Dict[str, Any]]] = windows_map or {}
        # licence_id -> outstanding unrecouped MG balance
        self.mg_balances: Dict[str, Decimal] = {}
        # licence_ids that have already received their Month 1 MG advance
        self.mg_paid_licences: Set[str] = set()

    def get_first_window_month(self, licence_id: str) -> str:
        """Determines the calendar month ('YYYY-MM') of the licence's earliest window start."""
        lic_windows = self.windows_map.get(licence_id, [])
        if not lic_windows:
            return ""
        starts = [w.get("window_start") or str(w.get("start_date", "")) for w in lic_windows]
        first_start = min(s for s in starts if s)
        return str(first_start)[:7]

    def is_month_one(self, licence_id: str, month: str) -> bool:
        """Checks if the given settlement month corresponds to Month 1 of the licence's first window."""
        first_month = self.get_first_window_month(licence_id)
        return month.strip() == first_month

    def evaluate_mg_payout(
        self,
        licence_id: str,
        month: str,
        contract_mg: Union[Decimal, str],
        split_pct: Union[Decimal, str] = Decimal("100.00"),
    ) -> Tuple[Decimal, bool]:
        """
        Determines if an MG payout is due in the current month for this licence stakeholder.
        Returns: (mg_payout_amount, is_new_mg_payout)
        """
        mg_val = Decimal(str(contract_mg))
        split = Decimal(str(split_pct))

        if mg_val <= Decimal("0.00"):
            return Decimal("0.00"), False

        is_m1 = self.is_month_one(licence_id, month)
        is_new = is_m1 and (licence_id not in self.mg_paid_licences)

        if is_new:
            # Advance paid out pro-rata to co-licensors
            mg_payout = (mg_val * split / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return mg_payout, True

        return Decimal("0.00"), False

    def record_mg_advance_initialized(self, licence_id: str, contract_mg: Decimal) -> None:
        """Initializes the active balance and registers advance payout."""
        self.mg_balances[licence_id] = contract_mg
        self.mg_paid_licences.add(licence_id)

    def get_outstanding_balance(self, licence_id: str) -> Decimal:
        """Returns current unrecouped MG balance for the licence."""
        return self.mg_balances.get(licence_id, Decimal("0.00"))

    def update_balance_after_recoupment(self, licence_id: str, recouped: Decimal) -> Decimal:
        """Deducts recouped amount from outstanding balance and returns new balance."""
        current = self.get_outstanding_balance(licence_id)
        new_bal = max(Decimal("0.00"), current - recouped)
        self.mg_balances[licence_id] = new_bal
        return new_bal

    def reset(self) -> None:
        """Resets all tracking states."""
        self.mg_balances.clear()
        self.mg_paid_licences.clear()
