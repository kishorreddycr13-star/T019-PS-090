"""
Unit Tests for Phase 7: Revenue Calculation Engine.
Covers BR-05 (Subscription Revenue Pool Allocation) and BR-06 (Advertisement Revenue Share).

Verifies all 17 required scenarios:
 1. Correct 60% subscription pool.
 2. Correct title-wise PREMIUM view ratio.
 3. Correct subscription share.
 4. Correct 55% advertisement share.
 5. Correct ad-impression allocation.
 6. POOL_ONLY licence entitlement (ad share is 0.00).
 7. POOL_AND_AD licence entitlement (pool share + ad share).
 8. Zero PREMIUM view-hours handling without division errors.
 9. Zero FREE ad impressions handling without division errors.
10. Multiple titles in one territory.
11. Multiple territories isolation.
12. Multiple settlement months isolation.
13. FREE-tier exclusion from subscription calculations.
14. PREMIUM-tier exclusion from advertisement calculations.
15. Ratio rounding to 4 decimal places with ROUND_HALF_UP.
16. Monetary rounding to paise (2 decimal places) with ROUND_HALF_UP.
17. Late-view revenue month assignment (Trap 3 / VW-001661).
"""
from __future__ import annotations

import csv
import sys
import unittest
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.subscription_calculator import SubscriptionCalculator
from services.advertisement_calculator import AdvertisementCalculator
from services.revenue_service import RevenueService
from services.metering_service import MeteringService
from services.revenue_validation import RevenueValidationError


class TestRevenueEngine(unittest.TestCase):
    """Test suite verifying BR-05 and BR-06 across all 17 required scenarios."""

    def setUp(self) -> None:
        self.sub_calc = SubscriptionCalculator()
        self.ad_calc = AdvertisementCalculator()
        self.rev_service = RevenueService()
        self.met_service = MeteringService()
        self.sample_dir = PROJECT_ROOT / "sample_data"

    # -------------------------------------------------------------------------
    # Scenario 1: Correct 60% subscription pool
    # -------------------------------------------------------------------------
    def test_01_correct_60_percent_subscription_pool(self) -> None:
        gross = Decimal("2801540.00")
        pool = self.sub_calc.calculate_subscription_pool(gross)
        # 2,801,540.00 * 0.60 = 1,680,924.00
        self.assertEqual(pool, Decimal("1680924.00"))

        # Rejects negative revenue
        with self.assertRaises(ValueError):
            self.sub_calc.calculate_subscription_pool(Decimal("-100.00"))

    # -------------------------------------------------------------------------
    # Scenario 2: Correct title-wise PREMIUM view ratio
    # -------------------------------------------------------------------------
    def test_02_correct_title_wise_premium_view_ratio(self) -> None:
        # Title hours: 10.1808 hrs, total territory hours: 43.7695 hrs
        t_hours = Decimal("10.1808")
        tot_hours = Decimal("43.7695")
        ratio = self.sub_calc.calculate_pool_ratio(t_hours, tot_hours)
        # 10.1808 / 43.7695 = 0.232600326... -> 0.2326
        self.assertEqual(ratio, Decimal("0.2326"))

    # -------------------------------------------------------------------------
    # Scenario 3: Correct subscription share
    # -------------------------------------------------------------------------
    def test_03_correct_subscription_share(self) -> None:
        pool = Decimal("1199553.60")
        ratio = Decimal("0.2326")
        share = self.sub_calc.calculate_pool_share(pool, ratio)
        # 1,199,553.60 * 0.2326 = 279,016.16736 -> 279,016.17
        self.assertEqual(share, Decimal("279016.17"))

    # -------------------------------------------------------------------------
    # Scenario 4: Correct 55% advertisement share
    # -------------------------------------------------------------------------
    def test_04_correct_55_percent_advertisement_share(self) -> None:
        gross_ad = Decimal("928757.00")
        ad_pool = self.ad_calc.calculate_ad_pool(gross_ad)
        # 928,757.00 * 0.55 = 510,816.35
        self.assertEqual(ad_pool, Decimal("510816.35"))

        with self.assertRaises(ValueError):
            self.ad_calc.calculate_ad_pool(Decimal("-50.00"))

    # -------------------------------------------------------------------------
    # Scenario 5: Correct ad-impression allocation
    # -------------------------------------------------------------------------
    def test_05_correct_ad_impression_allocation(self) -> None:
        # 19 impressions out of 308 total territory impressions
        ratio = self.ad_calc.calculate_ad_ratio(title_impressions=19, total_territory_impressions=308)
        # 19 / 308 = 0.0616883... -> 0.0617
        self.assertEqual(ratio, Decimal("0.0617"))

        ad_pool = Decimal("510816.35")
        ad_share = self.ad_calc.calculate_ad_share(ad_pool, ratio)
        # 510,816.35 * 0.0617 = 31,517.368795 -> 31,517.37
        self.assertEqual(ad_share, Decimal("31517.37"))

    # -------------------------------------------------------------------------
    # Scenario 6: POOL_ONLY licence entitlement
    # -------------------------------------------------------------------------
    def test_06_pool_only_licence_entitlement(self) -> None:
        pool_share = Decimal("279016.17")
        ad_share = Decimal("31517.37")

        # Mock licence with POOL_ONLY
        self.rev_service.licences["LCN-POOL-ONLY"] = {
            "licence_id": "LCN-POOL-ONLY",
            "revenue_share_type": "POOL_ONLY",
        }
        entitlement = self.rev_service.calculate_licence_revenue_entitlement(
            "LCN-POOL-ONLY", pool_share, ad_share
        )
        # POOL_ONLY receives only subscription pool share; ad_share is 0.00
        self.assertEqual(entitlement, pool_share)

    # -------------------------------------------------------------------------
    # Scenario 7: POOL_AND_AD licence entitlement
    # -------------------------------------------------------------------------
    def test_07_pool_and_ad_licence_entitlement(self) -> None:
        pool_share = Decimal("279016.17")
        ad_share = Decimal("31517.37")

        self.rev_service.licences["LCN-POOL-AD"] = {
            "licence_id": "LCN-POOL-AD",
            "revenue_share_type": "POOL_AND_AD",
        }
        entitlement = self.rev_service.calculate_licence_revenue_entitlement(
            "LCN-POOL-AD", pool_share, ad_share
        )
        # POOL_AND_AD receives pool_share + ad_share
        self.assertEqual(entitlement, pool_share + ad_share)
        self.assertEqual(entitlement, Decimal("310533.54"))

    # -------------------------------------------------------------------------
    # Scenario 8: Zero PREMIUM view-hours handling
    # -------------------------------------------------------------------------
    def test_08_zero_premium_view_hours(self) -> None:
        # Title has 0 view hours in non-empty territory
        ratio = self.sub_calc.calculate_pool_ratio(Decimal("0.0000"), Decimal("100.0000"))
        share = self.sub_calc.calculate_pool_share(Decimal("10000.00"), ratio)
        self.assertEqual(ratio, Decimal("0.0000"))
        self.assertEqual(share, Decimal("0.00"))

        # Entire territory has 0 view hours (handles division by zero)
        ratio_zero_tot = self.sub_calc.calculate_pool_ratio(Decimal("0.0000"), Decimal("0.0000"))
        share_zero_tot = self.sub_calc.calculate_pool_share(Decimal("10000.00"), ratio_zero_tot)
        self.assertEqual(ratio_zero_tot, Decimal("0.0000"))
        self.assertEqual(share_zero_tot, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # Scenario 9: Zero FREE ad impressions handling
    # -------------------------------------------------------------------------
    def test_09_zero_free_ad_impressions(self) -> None:
        ratio = self.ad_calc.calculate_ad_ratio(0, 500)
        share = self.ad_calc.calculate_ad_share(Decimal("5000.00"), ratio)
        self.assertEqual(ratio, Decimal("0.0000"))
        self.assertEqual(share, Decimal("0.00"))

        # Territory has 0 impressions
        ratio_zero_tot = self.ad_calc.calculate_ad_ratio(0, 0)
        share_zero_tot = self.ad_calc.calculate_ad_share(Decimal("5000.00"), ratio_zero_tot)
        self.assertEqual(ratio_zero_tot, Decimal("0.0000"))
        self.assertEqual(share_zero_tot, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # Scenario 10: Multiple titles in one territory
    # -------------------------------------------------------------------------
    def test_10_multiple_titles_in_one_territory(self) -> None:
        title_hours = {
            "TTL-A": Decimal("50.0000"),
            "TTL-B": Decimal("30.0000"),
            "TTL-C": Decimal("20.0000"),
        }
        res = self.sub_calc.allocate_territory_subscription_pool(
            gross_premium_revenue=Decimal("100000.00"),  # Pool = 60,000.00
            title_hours_map=title_hours,
        )
        self.assertEqual(res["TTL-A"].pool_ratio, Decimal("0.5000"))
        self.assertEqual(res["TTL-A"].pool_share, Decimal("30000.00"))

        self.assertEqual(res["TTL-B"].pool_ratio, Decimal("0.3000"))
        self.assertEqual(res["TTL-B"].pool_share, Decimal("18000.00"))

        self.assertEqual(res["TTL-C"].pool_ratio, Decimal("0.2000"))
        self.assertEqual(res["TTL-C"].pool_share, Decimal("12000.00"))

        # Sum of shares equals exactly the pool amount
        sum_shares = sum(r.pool_share for r in res.values())
        self.assertEqual(sum_shares, Decimal("60000.00"))

    # -------------------------------------------------------------------------
    # Scenario 11: Multiple territories isolation
    # -------------------------------------------------------------------------
    def test_11_multiple_territories_isolation(self) -> None:
        # Load July title shares
        sample_file = self.sample_dir / "view_events.csv"
        with open(sample_file, "r", encoding="utf-8") as f:
            events = list(csv.DictReader(f))

        decisions = self.met_service.process_views_batch(events)
        shares_jul = self.rev_service.calculate_monthly_title_shares("2026-07", decisions)

        # Check TTL-004 in AE vs IN
        share_ae = next((s for s in shares_jul if s["territory_id"] == "AE" and s["title_id"] == "TTL-004"), None)
        share_in = next((s for s in shares_jul if s["territory_id"] == "IN" and s["title_id"] == "TTL-004"), None)

        self.assertIsNotNone(share_ae)
        self.assertIsNotNone(share_in)
        self.assertEqual(share_ae["pool_share"], "279016.17")
        # In IN, TTL-004 had 0 view hours -> pool share 0.00
        self.assertEqual(share_in["pool_share"], "0.00")

    # -------------------------------------------------------------------------
    # Scenario 12: Multiple settlement months isolation
    # -------------------------------------------------------------------------
    def test_12_multiple_settlement_months_isolation(self) -> None:
        sample_file = self.sample_dir / "view_events.csv"
        with open(sample_file, "r", encoding="utf-8") as f:
            events = list(csv.DictReader(f))

        decisions = self.met_service.process_views_batch(events)
        shares_jul = self.rev_service.calculate_monthly_title_shares("2026-07", decisions)
        shares_aug = self.rev_service.calculate_monthly_title_shares("2026-08", decisions)

        # Check TTL-015 in SG (active in Aug)
        share_jul = next((s for s in shares_jul if s["territory_id"] == "SG" and s["title_id"] == "TTL-015"), None)
        share_aug = next((s for s in shares_aug if s["territory_id"] == "SG" and s["title_id"] == "TTL-015"), None)

        self.assertIsNotNone(share_jul)
        self.assertIsNotNone(share_aug)
        self.assertNotEqual(share_jul["pool_share"], share_aug["pool_share"])

    # -------------------------------------------------------------------------
    # Scenario 13: FREE-tier exclusion from subscription calculations
    # -------------------------------------------------------------------------
    def test_13_free_tier_exclusion_from_subscription_calculations(self) -> None:
        # Construct views: 1 PREMIUM (1 hr), 1 FREE (10 hrs)
        views = [
            {
                "view_id": "VW-P1",
                "counted": "true",
                "settlement_month": "2026-07",
                "_territory_id": "IN",
                "_title_id": "TTL-001",
                "_tier": "PREMIUM",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            },
            {
                "view_id": "VW-F1",
                "counted": "true",
                "settlement_month": "2026-07",
                "_territory_id": "IN",
                "_title_id": "TTL-002",
                "_tier": "FREE",
                "_watch_seconds": 36000,  # 10 hrs FREE
                "_ad_impressions": 100,
            },
        ]
        shares = self.rev_service.calculate_monthly_title_shares("2026-07", views)
        s_ttl2 = next(s for s in shares if s["territory_id"] == "IN" and s["title_id"] == "TTL-002")

        # TTL-002 has 0 premium view-hours despite 10 hours of FREE watching
        self.assertEqual(s_ttl2["premium_view_hours"], "0.0000")
        self.assertEqual(s_ttl2["pool_ratio"], "0.0000")
        self.assertEqual(s_ttl2["pool_share"], "0.00")

    # -------------------------------------------------------------------------
    # Scenario 14: PREMIUM-tier exclusion from advertisement calculations
    # -------------------------------------------------------------------------
    def test_14_premium_tier_exclusion_from_advertisement_calculations(self) -> None:
        views = [
            {
                "view_id": "VW-P2",
                "counted": "true",
                "settlement_month": "2026-07",
                "_territory_id": "IN",
                "_title_id": "TTL-001",
                "_tier": "PREMIUM",
                "_watch_seconds": 3600,
                "_ad_impressions": 50,  # Telemetry artifact must be excluded for PREMIUM
            },
            {
                "view_id": "VW-F2",
                "counted": "true",
                "settlement_month": "2026-07",
                "_territory_id": "IN",
                "_title_id": "TTL-002",
                "_tier": "FREE",
                "_watch_seconds": 1800,
                "_ad_impressions": 20,
            },
        ]
        shares = self.rev_service.calculate_monthly_title_shares("2026-07", views)
        s_ttl1 = next(s for s in shares if s["territory_id"] == "IN" and s["title_id"] == "TTL-001")

        # TTL-001 has 0 ad impressions in revenue allocation
        self.assertEqual(s_ttl1["ad_impressions"], "0")
        self.assertEqual(s_ttl1["ad_ratio"], "0.0000")
        self.assertEqual(s_ttl1["ad_share"], "0.00")

    # -------------------------------------------------------------------------
    # Scenario 15: Ratio rounding to 4 decimal places with ROUND_HALF_UP
    # -------------------------------------------------------------------------
    def test_15_ratio_rounding_to_four_decimal_places(self) -> None:
        # Exactly 0.12344 -> 0.1234
        r_down = self.sub_calc.calculate_pool_ratio(Decimal("12344"), Decimal("100000"))
        self.assertEqual(r_down, Decimal("0.1234"))

        # Exactly 0.12345 -> 0.1235 (ROUND_HALF_UP)
        r_up = self.sub_calc.calculate_pool_ratio(Decimal("12345"), Decimal("100000"))
        self.assertEqual(r_up, Decimal("0.1235"))

    # -------------------------------------------------------------------------
    # Scenario 16: Monetary rounding to paise with ROUND_HALF_UP
    # -------------------------------------------------------------------------
    def test_16_monetary_rounding_to_paise(self) -> None:
        pool = Decimal("100.00")
        # 100 * 0.00044 = 0.044 -> 0.04
        share_down = self.sub_calc.calculate_pool_share(pool, Decimal("0.00044"))
        self.assertEqual(share_down, Decimal("0.04"))

        # 100 * 0.00045 = 0.045 -> 0.05
        share_up = self.sub_calc.calculate_pool_share(pool, Decimal("0.00045"))
        self.assertEqual(share_up, Decimal("0.05"))

    # -------------------------------------------------------------------------
    # Scenario 17: Late-view revenue month assignment (Trap 3 / VW-001661)
    # -------------------------------------------------------------------------
    def test_17_late_view_revenue_month_assignment(self) -> None:
        self.met_service.reset_state()
        self.met_service.mark_month_settled("2026-07", "2026-09")

        # VW-001661 started in July local time but arrived late (tagged LATE_VIEW)
        late_event = {
            "view_id": "VW-001661",
            "subscriber_id": "SUB-IN-0050",
            "tier": "PREMIUM",
            "territory_id": "IN",
            "title_id": "TTL-027",
            "start_utc": "2026-07-25 15:00:00",
            "watch_seconds": 3600,
            "ad_impressions": 0,
            "ingested_utc": "2026-09-02 08:00:00",
        }
        dec = self.met_service.process_view_event(late_event)
        self.assertEqual(dec["settlement_month"], "2026-09")
        self.assertEqual(dec["tag"], "LATE_VIEW")

        # Verify that when July title shares are computed, this late view is NOT included
        shares_jul = self.rev_service.calculate_monthly_title_shares("2026-07", [dec])
        s_jul = next(s for s in shares_jul if s["territory_id"] == "IN" and s["title_id"] == "TTL-027")
        self.assertEqual(s_jul["premium_view_hours"], "0.0000")

        # Verify that it IS included when September title shares are computed
        shares_sep = self.rev_service.calculate_monthly_title_shares("2026-09", [dec])
        s_sep = next(s for s in shares_sep if s["territory_id"] == "IN" and s["title_id"] == "TTL-027")
        self.assertEqual(s_sep["premium_view_hours"], "1.0000")


if __name__ == "__main__":
    unittest.main()
