"""
Revenue Service Module.
Coordinates BR-05 (Subscription Revenue Pool) and BR-06 (Advertisement Revenue Share)
to compute title-level and licence-level revenue shares per month and territory.
"""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from services.subscription_calculator import SubscriptionCalculator
from services.advertisement_calculator import AdvertisementCalculator
from services.revenue_validation import (
    validate_period_format,
    validate_revenue_amount,
    validate_revenue_share_type,
    validate_ratio_bounds,
    validate_title_share_totals,
)
from repositories.revenue_repository import RevenueRepository
from models.revenue import TitleShareRecord


class RevenueService:
    """Central orchestration service for title and licence revenue share calculations."""

    def __init__(
        self,
        titles: Optional[Dict[str, Dict[str, Any]]] = None,
        territories: Optional[Dict[str, Dict[str, Any]]] = None,
        licences: Optional[Dict[str, Dict[str, Any]]] = None,
        subscription_revenues: Optional[Dict[Tuple[str, str], Decimal]] = None,
        ad_revenues: Optional[Dict[Tuple[str, str], Decimal]] = None,
        data_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "sample_data"
        self.sub_calc = SubscriptionCalculator()
        self.ad_calc = AdvertisementCalculator()
        self.repo = RevenueRepository(data_dir=self.data_dir)

        self.titles = titles or self._load_titles()
        self.territories = territories or self._load_territories()
        self.licences = licences or self._load_licences()
        self.subscription_revenues = subscription_revenues or self.repo.get_subscription_revenues()
        self.ad_revenues = ad_revenues or self.repo.get_ad_revenues()

    def _load_titles(self) -> Dict[str, Dict[str, Any]]:
        csv_file = self.data_dir / "titles.csv"
        if csv_file.exists():
            with open(csv_file, "r", encoding="utf-8") as f:
                return {r["title_id"]: r for r in csv.DictReader(f)}
        return {}

    def _load_territories(self) -> Dict[str, Dict[str, Any]]:
        csv_file = self.data_dir / "territories.csv"
        if csv_file.exists():
            with open(csv_file, "r", encoding="utf-8") as f:
                return {r["territory_id"]: r for r in csv.DictReader(f)}
        return {}

    def _load_licences(self) -> Dict[str, Dict[str, Any]]:
        csv_file = self.data_dir / "licences.csv"
        if csv_file.exists():
            with open(csv_file, "r", encoding="utf-8") as f:
                return {r["licence_id"]: r for r in csv.DictReader(f)}
        return {}

    def calculate_monthly_title_shares(
        self,
        month: str,
        view_decisions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Calculates title_shares for a given month across all territories and titles.
        Uses qualifying and counted view decisions from Phase 6.
        """
        validate_period_format(month)

        # 1. Filter views belonging to this settlement month and marked as counted
        eligible_views = [
            vd for vd in view_decisions
            if vd.get("settlement_month") == month and vd.get("counted") == "true"
        ]

        title_premium_hours: Dict[Tuple[str, str, str], Decimal] = {}
        title_ad_impressions: Dict[Tuple[str, str, str], int] = {}

        for vd in eligible_views:
            t_id = vd.get("_territory_id") or vd.get("territory_id") or ""
            title_id = vd.get("_title_id") or vd.get("title_id") or ""
            key = (month, t_id, title_id)
            tier = (vd.get("_tier") or vd.get("tier") or "PREMIUM").upper()

            if "PREM" in tier:
                watch_secs = int(vd.get("_watch_seconds") or vd.get("watch_seconds") or 0)
                vh = Decimal(watch_secs) / Decimal(3600)
                title_premium_hours[key] = title_premium_hours.get(key, Decimal(0)) + vh
            elif "FREE" in tier or "AD" in tier:
                ad_imp = int(vd.get("_ad_impressions") or vd.get("ad_impressions") or 0)
                title_ad_impressions[key] = title_ad_impressions.get(key, 0) + ad_imp

        # 2. Iterate over sorted territories and sorted titles
        month_records: List[Dict[str, Any]] = []
        sorted_territory_ids = sorted(self.territories.keys())
        sorted_title_ids = sorted(self.titles.keys())

        for terr_id in sorted_territory_ids:
            # Subscription Pool (60%)
            prem_gross = self.subscription_revenues.get((month, terr_id), Decimal("0.00"))
            prem_gross = validate_revenue_amount(prem_gross, f"subscription_revenue_{terr_id}_{month}")
            sub_pool = self.sub_calc.calculate_subscription_pool(prem_gross)

            tot_hours = sum(
                h for (m, t, tid), h in title_premium_hours.items()
                if m == month and t == terr_id
            )

            # Ad Pool (55%)
            ad_gross = self.ad_revenues.get((month, terr_id), Decimal("0.00"))
            ad_gross = validate_revenue_amount(ad_gross, f"ad_revenue_{terr_id}_{month}")
            ad_pool = self.ad_calc.calculate_ad_pool(ad_gross)

            tot_imps = sum(
                i for (m, t, tid), i in title_ad_impressions.items()
                if m == month and t == terr_id
            )

            for title_id in sorted_title_ids:
                key = (month, terr_id, title_id)
                t_hours = title_premium_hours.get(key, Decimal(0))
                t_imps = title_ad_impressions.get(key, 0)

                # Subscription ratio and share
                pool_ratio = self.sub_calc.calculate_pool_ratio(t_hours, tot_hours)
                validate_ratio_bounds(pool_ratio, "pool_ratio")
                pool_share = self.sub_calc.calculate_pool_share(sub_pool, pool_ratio)

                # Advertisement ratio and share
                ad_ratio = self.ad_calc.calculate_ad_ratio(t_imps, tot_imps)
                validate_ratio_bounds(ad_ratio, "ad_ratio")
                ad_share = self.ad_calc.calculate_ad_share(ad_pool, ad_ratio)

                # Total Title Share
                title_share_total = pool_share + ad_share
                validate_title_share_totals(pool_share, ad_share, title_share_total, title_id)

                # Format in exact evaluation string representation
                record = {
                    "month": month,
                    "territory_id": terr_id,
                    "title_id": title_id,
                    "premium_view_hours": f"{t_hours.quantize(Decimal('0.0001'), rounding=Decimal('0.0001')) if False else (Decimal(str(t_hours)).quantize(Decimal('0.0001'), rounding='ROUND_HALF_UP')):.4f}",
                    "pool_ratio": f"{pool_ratio:.4f}",
                    "pool_share": f"{pool_share:.2f}",
                    "ad_impressions": str(t_imps),
                    "ad_ratio": f"{ad_ratio:.4f}",
                    "ad_share": f"{ad_share:.2f}",
                    "title_share": f"{title_share_total:.2f}",
                    # Numeric values for programmatic access
                    "_pool_share_num": pool_share,
                    "_ad_share_num": ad_share,
                    "_title_share_num": title_share_total,
                }
                month_records.append(record)

        return month_records

    def calculate_licence_revenue_entitlement(
        self,
        licence_id: str,
        pool_share: Union[Decimal, str],
        ad_share: Union[Decimal, str],
    ) -> Decimal:
        """
        Determines licence gross entitlement taking into account the revenue-share type.
        - POOL_ONLY: entitled to subscription pool share only (ad_share is excluded).
        - POOL_AND_AD: entitled to subscription pool share + advertisement share.
        """
        lic = self.licences.get(licence_id)
        if not lic:
            raise ValueError(f"Licence '{licence_id}' not found in registered licences.")

        rev_type = validate_revenue_share_type(lic.get("revenue_share_type", "POOL_AND_AD"))
        p_share = Decimal(str(pool_share))
        a_share = Decimal(str(ad_share))

        if rev_type == "POOL_ONLY":
            return p_share
        return p_share + a_share

    def persist_title_shares(self, title_share_records: List[Dict[str, Any]]) -> None:
        """Converts dict results to TitleShareRecord entities and saves them to DB."""
        db_entities = [
            TitleShareRecord(
                period_key=r["month"],
                territory_code=r["territory_id"],
                title_id=r["title_id"],
                premium_view_hours=Decimal(r["premium_view_hours"]),
                pool_ratio=Decimal(r["pool_ratio"]),
                pool_share=Decimal(r["pool_share"]),
                ad_impressions=int(r["ad_impressions"]),
                ad_ratio=Decimal(r["ad_ratio"]),
                ad_share=Decimal(r["ad_share"]),
                title_share=Decimal(r["title_share"]),
            )
            for r in title_share_records
        ]
        self.repo.save_title_shares(db_entities)

    @staticmethod
    def export_title_shares_csv(
        records: List[Dict[str, Any]],
        output_path: Union[str, Path],
    ) -> None:
        """
        Exports title shares to CSV in the required evaluation schema:
        month,territory_id,title_id,premium_view_hours,pool_ratio,pool_share,ad_impressions,ad_ratio,ad_share,title_share
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "month",
            "territory_id",
            "title_id",
            "premium_view_hours",
            "pool_ratio",
            "pool_share",
            "ad_impressions",
            "ad_ratio",
            "ad_share",
            "title_share",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in records:
                writer.writerow({fn: r.get(fn, "") for fn in fieldnames})
