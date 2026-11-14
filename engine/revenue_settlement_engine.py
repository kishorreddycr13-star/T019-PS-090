"""
Revenue & Settlement Engine Module.
Implements BR-04, BR-05, BR-07, BR-08, BR-09, BR-10, BR-12.
Calculates title_shares.csv and settlements.csv with exact pro-rata pool allocations,
MG recoupment waterfalls, payment cap enforcement, co-licensor split residues, and TDS.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from typing import Dict, List, Optional, Set, Tuple, Any

from services.subscription_calculator import SubscriptionCalculator
from services.advertisement_calculator import AdvertisementCalculator


def round_half_up(val: Decimal | float | int, places: int = 2) -> Decimal:
    """Rounds decimal value using standard HALF_UP rounding."""
    q = Decimal("10") ** -places
    return Decimal(str(val)).quantize(q, rounding=ROUND_HALF_UP)


def floor_paisa(val: Decimal | float | int) -> Decimal:
    """Floors decimal monetary amount to 2 decimal places (paise)."""
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_FLOOR)


class RevenueSettlementEngine:
    """Computes monthly subscriber revenue pools, ad shares, recoupments, and partner settlements."""

    def __init__(
        self,
        territories: Dict[str, Dict[str, Any]],
        licensors: Dict[str, Dict[str, Any]],
        titles: Dict[str, Dict[str, Any]],
        title_splits: Dict[str, List[Dict[str, Any]]],
        licences: Dict[str, Dict[str, Any]],
        windows: Dict[str, List[Dict[str, Any]]],
        subscription_revenue: Dict[Tuple[str, str], Decimal],
        ad_revenue: Dict[Tuple[str, str], Decimal],
    ) -> None:
        self.territories = territories
        self.licensors = licensors
        self.titles = titles
        self.title_splits = title_splits
        self.licences = licences
        self.windows = windows
        self.subscription_revenue = subscription_revenue
        self.ad_revenue = ad_revenue

        # Persistent state across settlement runs
        # licence_id -> outstanding unrecouped MG balance
        self.mg_balances: Dict[str, Decimal] = {}
        # licence_ids that have already had their Month 1 MG advance paid out
        self.mg_paid_licences: Set[str] = set()
        # licence_id -> cumulative paid before TDS towards cap
        self.cumulative_paid_cap: Dict[str, Decimal] = {}
        # licence_id -> whether licence has reached its cap
        self.is_capped: Dict[str, bool] = {}

        # Generated outputs
        self.all_title_shares: List[Dict[str, Any]] = []
        self.all_settlements: List[Dict[str, Any]] = []

    def _get_first_window_month(self, licence_id: str) -> str:
        """Determines the calendar month of the licence's first window start date."""
        lic_windows = self.windows.get(licence_id, [])
        if not lic_windows:
            return ""
        starts = [w["window_start"] for w in lic_windows]
        first_start = min(starts)
        return first_start[:7]  # YYYY-MM

    def settle_month(
        self,
        month: str,
        view_decisions: List[Dict[str, Any]],
        accepted_licences: List[str],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Executes a monthly settlement run for the specified month (e.g. '2026-07').
        Aggregates counted view-hours and impressions, allocates pools, applies MG/Caps/TDS,
        and produces title_shares and settlements records.
        """
        # 1. Filter views that belong to this settlement month and were counted
        eligible_views = [
            vd for vd in view_decisions
            if vd["settlement_month"] == month and vd["counted"] == "true"
        ]

        title_premium_hours: Dict[Tuple[str, str, str], Decimal] = {}
        title_ad_impressions: Dict[Tuple[str, str, str], int] = {}

        for vd in eligible_views:
            t_id = vd["_territory_id"]
            title_id = vd["_title_id"]
            key = (month, t_id, title_id)

            if vd["_tier"] == "PREMIUM":
                # view_hours = watch_seconds / 3600
                vh = Decimal(vd["_watch_seconds"]) / Decimal(3600)
                title_premium_hours[key] = title_premium_hours.get(key, Decimal(0)) + vh
            elif vd["_tier"] == "FREE":
                ad_imp = vd["_ad_impressions"]
                title_ad_impressions[key] = title_ad_impressions.get(key, 0) + ad_imp

        # 2. Compute title_shares.csv for this month
        month_title_shares: List[Dict[str, Any]] = []
        title_share_lookup: Dict[Tuple[str, str, str], Dict[str, Decimal]] = {}

        sorted_territory_ids = sorted(self.territories.keys())
        sorted_title_ids = sorted(self.titles.keys())

        for terr_id in sorted_territory_ids:
            # Subscription pool: 60% of premium revenue
            prem_gross = self.subscription_revenue.get((month, terr_id), Decimal("0.00"))
            prem_pool = prem_gross * Decimal("0.60")

            tot_hours = sum(
                h for (m, t, tid), h in title_premium_hours.items()
                if m == month and t == terr_id
            )

            # Ad pool: 55% of ad revenue
            ad_gross = self.ad_revenue.get((month, terr_id), Decimal("0.00"))
            ad_pool = ad_gross * Decimal("0.55")

            tot_imps = sum(
                i for (m, t, tid), i in title_ad_impressions.items()
                if m == month and t == terr_id
            )

            for title_id in sorted_title_ids:
                key = (month, terr_id, title_id)
                t_hours = title_premium_hours.get(key, Decimal(0))
                t_imps = title_ad_impressions.get(key, 0)

                # Premium pool ratio & share (BR-05)
                pool_ratio = SubscriptionCalculator.calculate_pool_ratio(t_hours, tot_hours)
                pool_share = SubscriptionCalculator.calculate_pool_share(prem_pool, pool_ratio)

                # Ad pool ratio & share (BR-06)
                ad_ratio = AdvertisementCalculator.calculate_ad_ratio(t_imps, tot_imps)
                ad_share = AdvertisementCalculator.calculate_ad_share(ad_pool, ad_ratio)

                title_share_total = pool_share + ad_share

                record = {
                    "month": month,
                    "territory_id": terr_id,
                    "title_id": title_id,
                    "premium_view_hours": f"{round_half_up(t_hours, 4):.4f}",
                    "pool_ratio": f"{pool_ratio:.4f}",
                    "pool_share": f"{pool_share:.2f}",
                    "ad_impressions": str(t_imps),
                    "ad_ratio": f"{ad_ratio:.4f}",
                    "ad_share": f"{ad_share:.2f}",
                    "title_share": f"{title_share_total:.2f}",
                }
                month_title_shares.append(record)
                self.all_title_shares.append(record)

                title_share_lookup[key] = {
                    "pool_share": pool_share,
                    "ad_share": ad_share,
                    "title_share": title_share_total,
                }

        # 3. Compute settlements.csv for this month
        month_settlements: List[Dict[str, Any]] = []

        for licence_id in accepted_licences:
            lic = self.licences[licence_id]
            title_id = lic["title_id"]
            terr_id = lic["territory_id"]
            rev_type = lic["revenue_share_type"]
            contract_mg = Decimal(lic["mg_amount"])
            contract_cap = Decimal(lic["cap_amount"])

            t_shares = title_share_lookup.get(
                (month, terr_id, title_id),
                {"pool_share": Decimal("0.00"), "ad_share": Decimal("0.00")},
            )

            # POOL_ONLY licences get no ad share
            if rev_type == "POOL_ONLY":
                licence_gross = t_shares["pool_share"]
            else:
                licence_gross = t_shares["pool_share"] + t_shares["ad_share"]

            # Check co-licensing splits (EC-07)
            if title_id in self.title_splits:
                splits = self.title_splits[title_id]
            else:
                splits = [{"licensor_id": lic["licensor_id"], "split_pct": "100.00"}]

            # Pre-compute gross share allocation across co-licensors
            # Floored parts to the paisa with residue to largest split
            split_allocations: Dict[str, Decimal] = {}
            if len(splits) == 1:
                split_allocations[splits[0]["licensor_id"]] = licence_gross
            else:
                floored_parts: Dict[str, Decimal] = {}
                for sp in splits:
                    pct = Decimal(sp["split_pct"])
                    val = floor_paisa(licence_gross * pct / Decimal("100"))
                    floored_parts[sp["licensor_id"]] = val

                sum_floored = sum(floored_parts.values())
                residue = licence_gross - sum_floored

                # Find licensor with largest split percentage
                largest_sp = max(splits, key=lambda s: Decimal(s["split_pct"]))
                floored_parts[largest_sp["licensor_id"]] += residue
                split_allocations = floored_parts

            # Check Month 1 MG advance condition (EC-04)
            # MG is paid in month 1 of the first window
            first_month = self._get_first_window_month(licence_id)
            is_month_1 = (month == first_month) and (contract_mg > Decimal(0))
            is_new_mg_payout = is_month_1 and (licence_id not in self.mg_paid_licences)

            # Process settlement for each licensor stakeholder
            for sp in splits:
                licensor_id = sp["licensor_id"]
                split_pct = Decimal(sp["split_pct"])
                gross_share = split_allocations[licensor_id]

                # MG handling
                mg_paid = Decimal("0.00")
                if is_new_mg_payout:
                    # Co-licensors share MG proportionally
                    mg_paid = round_half_up(contract_mg * split_pct / Decimal("100"), 2)
                    self.mg_balances[licence_id] = contract_mg

                current_mg_bal = self.mg_balances.get(licence_id, Decimal("0.00"))
                # Recoupment against unrecouped balance
                recouped = min(gross_share, current_mg_bal)
                new_mg_bal = current_mg_bal - recouped

                # Cap handling (EC-05)
                cap_retained = Decimal("0.00")
                status = "SETTLED"

                if contract_cap > Decimal(0):
                    cum_paid = self.cumulative_paid_cap.get(licence_id, Decimal("0.00"))
                    headroom = max(Decimal("0.00"), contract_cap - cum_paid)

                    if gross_share > headroom:
                        payable_before_tds = headroom
                        cap_retained = gross_share - headroom
                        self.cumulative_paid_cap[licence_id] = contract_cap
                        self.is_capped[licence_id] = True
                        status = "CAPPED"
                    else:
                        payable_before_tds = gross_share
                        self.cumulative_paid_cap[licence_id] = cum_paid + payable_before_tds
                        if self.is_capped.get(licence_id, False) or (cum_paid + payable_before_tds >= contract_cap):
                            status = "CAPPED"
                else:
                    # No Cap
                    if contract_mg > Decimal(0):
                        if is_new_mg_payout:
                            # In Month 1: MG is paid; any excess gross above MG is also paid
                            excess = max(Decimal("0.00"), gross_share - contract_mg)
                            payable_before_tds = mg_paid + excess
                        else:
                            # In subsequent months: only excess above unrecouped balance is paid
                            payable_before_tds = max(Decimal("0.00"), gross_share - current_mg_bal)
                    else:
                        payable_before_tds = gross_share

                # Update state
                self.mg_balances[licence_id] = new_mg_bal
                if is_new_mg_payout:
                    self.mg_paid_licences.add(licence_id)

                # TDS Calculation
                licensor_info = self.licensors[licensor_id]
                is_indian = (licensor_info["is_indian"].lower() == "true")
                treaty_rate_str = licensor_info.get("treaty_tds_pct", "").strip()

                if is_indian:
                    tds_pct = Decimal("10.00")
                else:
                    if treaty_rate_str:
                        tds_pct = Decimal(treaty_rate_str)
                    else:
                        tds_pct = Decimal("20.00")

                tds_amount = round_half_up(
                    payable_before_tds * tds_pct / Decimal("100"), 2
                )
                net_payable = payable_before_tds - tds_amount

                settlement_row = {
                    "month": month,
                    "licence_id": licence_id,
                    "licensor_id": licensor_id,
                    "split_pct": f"{split_pct:.2f}",
                    "gross_share": f"{gross_share:.2f}",
                    "mg_paid": f"{mg_paid:.2f}",
                    "recouped": f"{recouped:.2f}",
                    "mg_balance": f"{new_mg_bal:.2f}",
                    "cap_retained": f"{cap_retained:.2f}",
                    "payable_before_tds": f"{payable_before_tds:.2f}",
                    "tds_pct": f"{tds_pct:.2f}",
                    "tds": f"{tds_amount:.2f}",
                    "net_payable": f"{net_payable:.2f}",
                    "status": status,
                }
                month_settlements.append(settlement_row)
                self.all_settlements.append(settlement_row)

        return month_title_shares, month_settlements
