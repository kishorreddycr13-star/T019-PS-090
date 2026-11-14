"""
Subscription Revenue Pool Calculator Module.
Implements BR-05 (Subscription Revenue Pool Allocation).

Business Rules:
- Subscription Pool = Gross PREMIUM Subscription Revenue * 60%
- Title Ratio = Title PREMIUM View-Hours / Total PREMIUM View-Hours in Territory
- Title Pool Share = Subscription Pool * Title Ratio
- Pool ratio rounded to 4 decimal places using ROUND_HALF_UP.
- Title pool share rounded to 2 decimal places (paise) using ROUND_HALF_UP.
- Only qualifying and counted PREMIUM views contribute; FREE views are excluded.
- Zero total view-hours handled safely without division by zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Union

SUBSCRIPTION_POOL_RATE: Decimal = Decimal("0.60")
RATIO_QUANTUM: Decimal = Decimal("0.0001")
CURRENCY_QUANTUM: Decimal = Decimal("0.01")


@dataclass(frozen=True)
class SubscriptionShareResult:
    """Holds the subscription revenue allocation result for a single title."""
    title_id: str
    premium_view_hours: Decimal
    total_territory_view_hours: Decimal
    subscription_pool: Decimal
    pool_ratio: Decimal
    pool_share: Decimal

    def to_dict(self) -> dict:
        return {
            "title_id": self.title_id,
            "premium_view_hours": f"{self.premium_view_hours:.4f}",
            "total_territory_view_hours": f"{self.total_territory_view_hours:.4f}",
            "subscription_pool": f"{self.subscription_pool:.2f}",
            "pool_ratio": f"{self.pool_ratio:.4f}",
            "pool_share": f"{self.pool_share:.2f}",
        }


class SubscriptionCalculator:
    """Encapsulates mathematical operations for the 60% SVOD subscription pool."""

    @staticmethod
    def calculate_subscription_pool(gross_revenue: Union[Decimal, float, str]) -> Decimal:
        """
        Calculates the 60% distributable subscription pool.
        Subscription Pool = Gross PREMIUM Subscription Revenue * 0.60
        """
        gross = Decimal(str(gross_revenue))
        if gross < Decimal("0.00"):
            raise ValueError(f"Subscription gross revenue cannot be negative: {gross}")
        return gross * SUBSCRIPTION_POOL_RATE

    @staticmethod
    def calculate_pool_ratio(
        title_view_hours: Union[Decimal, float, str],
        total_territory_view_hours: Union[Decimal, float, str],
    ) -> Decimal:
        """
        Calculates title's view-hour proportion in territory, rounded half-up to 4 decimals.
        Title Ratio = Title PREMIUM View-Hours / Total Territory View-Hours
        """
        t_hours = Decimal(str(title_view_hours))
        tot_hours = Decimal(str(total_territory_view_hours))

        if t_hours < Decimal("0.0000"):
            raise ValueError(f"Title view hours cannot be negative: {t_hours}")
        if tot_hours < Decimal("0.0000"):
            raise ValueError(f"Total territory view hours cannot be negative: {tot_hours}")

        if tot_hours == Decimal("0.0000") or t_hours == Decimal("0.0000"):
            return Decimal("0.0000")

        return (t_hours / tot_hours).quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP)

    @staticmethod
    def calculate_pool_share(
        subscription_pool: Union[Decimal, float, str],
        pool_ratio: Union[Decimal, float, str],
    ) -> Decimal:
        """
        Calculates the pro-rata monetary share in paise (2 decimal places).
        Title Pool Share = Subscription Pool * Pool Ratio
        """
        pool = Decimal(str(subscription_pool))
        ratio = Decimal(str(pool_ratio))

        if pool < Decimal("0.00"):
            raise ValueError(f"Subscription pool cannot be negative: {pool}")
        if ratio < Decimal("0.0000"):
            raise ValueError(f"Pool ratio cannot be negative: {ratio}")

        return (pool * ratio).quantize(CURRENCY_QUANTUM, rounding=ROUND_HALF_UP)

    @classmethod
    def allocate_territory_subscription_pool(
        cls,
        gross_premium_revenue: Union[Decimal, float, str],
        title_hours_map: Dict[str, Decimal],
    ) -> Dict[str, SubscriptionShareResult]:
        """
        Allocates the monthly subscription pool among all titles in a territory.
        """
        pool = cls.calculate_subscription_pool(gross_premium_revenue)
        tot_hours = sum(title_hours_map.values(), Decimal("0.0000"))

        results: Dict[str, SubscriptionShareResult] = {}
        for title_id, hours in title_hours_map.items():
            ratio = cls.calculate_pool_ratio(hours, tot_hours)
            share = cls.calculate_pool_share(pool, ratio)

            results[title_id] = SubscriptionShareResult(
                title_id=title_id,
                premium_view_hours=hours.quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP),
                total_territory_view_hours=tot_hours.quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP),
                subscription_pool=pool.quantize(CURRENCY_QUANTUM, rounding=ROUND_HALF_UP),
                pool_ratio=ratio,
                pool_share=share,
            )

        return results
