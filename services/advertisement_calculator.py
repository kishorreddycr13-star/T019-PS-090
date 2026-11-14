"""
Advertisement Revenue Share Calculator Module.
Implements BR-06 (Advertisement Revenue Share Allocation).

Business Rules:
- 55% of advertisement revenue is distributed across qualifying FREE-tier views.
- Ad Pool = Gross Advertisement Revenue in Territory * 55%
- Title Ad Ratio = Title FREE Ad Impressions / Total FREE Ad Impressions in Territory
- Title Ad Share = Ad Pool * Title Ad Ratio
- Ad ratio rounded to 4 decimal places using ROUND_HALF_UP.
- Ad share rounded to 2 decimal places (paise) using ROUND_HALF_UP.
- Only qualifying and counted FREE-tier views contribute; PREMIUM views are excluded.
- Zero total impressions handled safely without division by zero.
- For POOL_ONLY licences, advertisement share allocation is strictly 0.00.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Union

AD_POOL_RATE: Decimal = Decimal("0.55")
RATIO_QUANTUM: Decimal = Decimal("0.0001")
CURRENCY_QUANTUM: Decimal = Decimal("0.01")


@dataclass(frozen=True)
class AdShareResult:
    """Holds the advertisement revenue allocation result for a single title."""
    title_id: str
    ad_impressions: int
    total_territory_impressions: int
    ad_pool: Decimal
    ad_ratio: Decimal
    ad_share: Decimal

    def to_dict(self) -> dict:
        return {
            "title_id": self.title_id,
            "ad_impressions": self.ad_impressions,
            "total_territory_impressions": self.total_territory_impressions,
            "ad_pool": f"{self.ad_pool:.2f}",
            "ad_ratio": f"{self.ad_ratio:.4f}",
            "ad_share": f"{self.ad_share:.2f}",
        }


class AdvertisementCalculator:
    """Encapsulates mathematical operations for the 55% AVOD advertisement pool."""

    @staticmethod
    def calculate_ad_pool(gross_revenue: Union[Decimal, float, str]) -> Decimal:
        """
        Calculates the 55% distributable advertisement revenue pool.
        Ad Pool = Gross Advertisement Revenue * 0.55
        """
        gross = Decimal(str(gross_revenue))
        if gross < Decimal("0.00"):
            raise ValueError(f"Advertisement gross revenue cannot be negative: {gross}")
        return gross * AD_POOL_RATE

    @staticmethod
    def calculate_ad_ratio(
        title_impressions: int,
        total_territory_impressions: int,
    ) -> Decimal:
        """
        Calculates title's ad-impression proportion in territory, rounded half-up to 4 decimals.
        Title Ad Ratio = Title FREE Ad Impressions / Total Territory FREE Ad Impressions
        """
        if title_impressions < 0:
            raise ValueError(f"Title ad impressions cannot be negative: {title_impressions}")
        if total_territory_impressions < 0:
            raise ValueError(f"Total territory impressions cannot be negative: {total_territory_impressions}")

        if total_territory_impressions == 0 or title_impressions == 0:
            return Decimal("0.0000")

        ratio = Decimal(title_impressions) / Decimal(total_territory_impressions)
        return ratio.quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP)

    @staticmethod
    def calculate_ad_share(
        ad_pool: Union[Decimal, float, str],
        ad_ratio: Union[Decimal, float, str],
        is_pool_only: bool = False,
    ) -> Decimal:
        """
        Calculates the pro-rata monetary ad share in paise (2 decimal places).
        Title Ad Share = Ad Pool * Ad Ratio (or 0.00 if licence is POOL_ONLY)
        """
        if is_pool_only:
            return Decimal("0.00")

        pool = Decimal(str(ad_pool))
        ratio = Decimal(str(ad_ratio))

        if pool < Decimal("0.00"):
            raise ValueError(f"Ad pool cannot be negative: {pool}")
        if ratio < Decimal("0.0000"):
            raise ValueError(f"Ad ratio cannot be negative: {ratio}")

        return (pool * ratio).quantize(CURRENCY_QUANTUM, rounding=ROUND_HALF_UP)

    @classmethod
    def allocate_territory_ad_pool(
        cls,
        gross_ad_revenue: Union[Decimal, float, str],
        title_impressions_map: Dict[str, int],
    ) -> Dict[str, AdShareResult]:
        """
        Allocates the monthly advertisement pool among all titles in a territory.
        """
        pool = cls.calculate_ad_pool(gross_ad_revenue)
        tot_imps = sum(title_impressions_map.values())

        results: Dict[str, AdShareResult] = {}
        for title_id, imps in title_impressions_map.items():
            ratio = cls.calculate_ad_ratio(imps, tot_imps)
            share = cls.calculate_ad_share(pool, ratio)

            results[title_id] = AdShareResult(
                title_id=title_id,
                ad_impressions=imps,
                total_territory_impressions=tot_imps,
                ad_pool=pool.quantize(CURRENCY_QUANTUM, rounding=ROUND_HALF_UP),
                ad_ratio=ratio,
                ad_share=share,
            )

        return results
