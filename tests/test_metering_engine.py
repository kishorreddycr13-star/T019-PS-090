"""
Unit Tests for Phase 6: View Tracking & Metering Engine.
Covers BR-07 (Qualifying Views), BR-08 (Duplicate View Prevention),
BR-09 (Subscriber Tier Classification), and BR-10 (Monthly/Territory Metering).

Verifies all 17 explicit test scenarios:
 1. Watch duration below the qualifying threshold.
 2. Watch duration exactly equal to the threshold.
 3. Watch duration above the threshold.
 4. Runtime of 180 seconds with a 90-second threshold (EC-02).
 5. Runtime of 300 seconds with a 120-second threshold.
 6. Duplicate view within 24 hours (< 86,400s) (EC-03).
 7. Duplicate view exactly at the 24-hour boundary (= 86,400s).
 8. Same subscriber watching different titles.
 9. Different subscribers watching the same title.
10. FREE-tier qualifying views.
11. PREMIUM-tier qualifying views.
12. Denied playback events.
13. Different territories and time zone offsets.
14. UTC midnight crossing (EC-06).
15. Late-ingested events (Trap 3 / VW-001661).
16. Multiple views in the same month aggregation.
17. Views spanning different months (July, August, September).
"""
from __future__ import annotations

import csv
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.qualification_service import QualificationService
from services.duplicate_detection import DuplicateDetector
from services.metering_service import MeteringService
from repositories.metering_repository import MeteringRepository
from engine.playback_eligibility_engine import PlaybackRequest, PlaybackDecision


class TestMeteringEngine(unittest.TestCase):
    """Test suite verifying BR-07, BR-08, BR-09, and BR-10 across all 17 required scenarios."""

    def setUp(self) -> None:
        self.qual_svc = QualificationService()
        self.dup_detector = DuplicateDetector()
        self.metering_svc = MeteringService()
        self.sample_dir = PROJECT_ROOT / "sample_data"

    # -------------------------------------------------------------------------
    # Scenario 1: Watch duration below the qualifying threshold
    # -------------------------------------------------------------------------
    def test_01_watch_duration_below_threshold(self) -> None:
        # Runtime 7200s -> threshold is min(120, 3600) = 120s
        runtime = 7200
        watch_seconds = 119
        result = self.qual_svc.evaluate_qualification(watch_seconds, runtime)
        self.assertFalse(result.is_qualifying)
        self.assertEqual(result.threshold_seconds, 120)
        self.assertEqual(result.qualification_status, "UNDER_THRESHOLD")

    # -------------------------------------------------------------------------
    # Scenario 2: Watch duration exactly equal to the threshold
    # -------------------------------------------------------------------------
    def test_02_watch_duration_exactly_equal_threshold(self) -> None:
        runtime = 7200
        watch_seconds = 120
        result = self.qual_svc.evaluate_qualification(watch_seconds, runtime)
        self.assertTrue(result.is_qualifying)
        self.assertEqual(result.threshold_seconds, 120)
        self.assertEqual(result.qualification_status, "QUALIFIED")

    # -------------------------------------------------------------------------
    # Scenario 3: Watch duration above the threshold
    # -------------------------------------------------------------------------
    def test_03_watch_duration_above_threshold(self) -> None:
        runtime = 7200
        watch_seconds = 3600
        result = self.qual_svc.evaluate_qualification(watch_seconds, runtime)
        self.assertTrue(result.is_qualifying)
        self.assertEqual(result.threshold_seconds, 120)
        self.assertEqual(result.qualification_status, "QUALIFIED")

    # -------------------------------------------------------------------------
    # Scenario 4: Runtime of 180 seconds with a 90-second threshold (EC-02)
    # -------------------------------------------------------------------------
    def test_04_runtime_180s_threshold_90s(self) -> None:
        # Formula: min(120, 180 * 0.50) = 90 seconds
        runtime = 180
        threshold = self.qual_svc.compute_qualifying_threshold(runtime)
        self.assertEqual(threshold, 90)

        # 95s qualifies (EC-02 / VW-000997)
        res_qual = self.qual_svc.evaluate_qualification(watch_seconds=95, runtime_seconds=180)
        self.assertTrue(res_qual.is_qualifying)

        # 85s fails (EC-02 / VW-000999)
        res_fail = self.qual_svc.evaluate_qualification(watch_seconds=85, runtime_seconds=180)
        self.assertFalse(res_fail.is_qualifying)

    # -------------------------------------------------------------------------
    # Scenario 5: Runtime of 300 seconds with a 120-second threshold
    # -------------------------------------------------------------------------
    def test_05_runtime_300s_threshold_120s(self) -> None:
        # Formula: min(120, 300 * 0.50) = min(120, 150) = 120 seconds
        runtime = 300
        threshold = self.qual_svc.compute_qualifying_threshold(runtime)
        self.assertEqual(threshold, 120)

        # 119s fails, 120s qualifies, 121s qualifies
        self.assertFalse(self.qual_svc.evaluate_qualification(119, runtime).is_qualifying)
        self.assertTrue(self.qual_svc.evaluate_qualification(120, runtime).is_qualifying)
        self.assertTrue(self.qual_svc.evaluate_qualification(121, runtime).is_qualifying)

    # -------------------------------------------------------------------------
    # Scenario 6: Duplicate view within 24 hours (< 86,400s) (EC-03)
    # -------------------------------------------------------------------------
    def test_06_duplicate_view_within_24_hours(self) -> None:
        sub = "SUB-TEST-001"
        title = "TTL-TEST-001"
        t0 = datetime(2026, 7, 21, 10, 0, 0)
        t1 = datetime(2026, 7, 22, 9, 59, 0)  # 23h 59m apart (86,340s)

        # First view is counted
        res1 = self.dup_detector.is_duplicate(sub, title, t0)
        self.assertFalse(res1.is_duplicate)
        self.dup_detector.record_counted_view(sub, title, t0)

        # Second view within 24h is rejected as duplicate
        res2 = self.dup_detector.is_duplicate(sub, title, t1)
        self.assertTrue(res2.is_duplicate)
        self.assertEqual(res2.delta_seconds, 86340.0)

    # -------------------------------------------------------------------------
    # Scenario 7: Duplicate view exactly at the 24-hour boundary (= 86,400s)
    # -------------------------------------------------------------------------
    def test_07_duplicate_boundary_at_exact_24_hours(self) -> None:
        sub = "SUB-TEST-002"
        title = "TTL-TEST-002"
        t0 = datetime(2026, 7, 21, 10, 0, 0)
        t_exact_24h = t0 + timedelta(seconds=86400)  # Exactly 2026-07-22 10:00:00

        self.dup_detector.record_counted_view(sub, title, t0)

        # "no counted view started less than 24 h earlier": exactly 24h is NOT duplicate
        res = self.dup_detector.is_duplicate(sub, title, t_exact_24h)
        self.assertFalse(res.is_duplicate)
        self.assertEqual(res.delta_seconds, 86400.0)

    # -------------------------------------------------------------------------
    # Scenario 8: Same subscriber watching different titles
    # -------------------------------------------------------------------------
    def test_08_same_subscriber_different_titles(self) -> None:
        sub = "SUB-TEST-003"
        t0 = datetime(2026, 7, 21, 10, 0, 0)
        t_short = t0 + timedelta(minutes=30)

        # Watch Title A
        self.dup_detector.record_counted_view(sub, "TTL-A", t0)

        # Watch Title B 30 minutes later: must NOT be duplicate
        res_b = self.dup_detector.is_duplicate(sub, "TTL-B", t_short)
        self.assertFalse(res_b.is_duplicate)

    # -------------------------------------------------------------------------
    # Scenario 9: Different subscribers watching the same title
    # -------------------------------------------------------------------------
    def test_09_different_subscribers_same_title(self) -> None:
        title = "TTL-SHARED-001"
        t0 = datetime(2026, 7, 21, 10, 0, 0)
        t_same_time = t0 + timedelta(seconds=10)

        # Subscriber 1 watches
        self.dup_detector.record_counted_view("SUB-01", title, t0)

        # Subscriber 2 watches 10 seconds later: must NOT be duplicate
        res_sub2 = self.dup_detector.is_duplicate("SUB-02", title, t_same_time)
        self.assertFalse(res_sub2.is_duplicate)

    # -------------------------------------------------------------------------
    # Scenario 10: FREE-tier qualifying views
    # -------------------------------------------------------------------------
    def test_10_free_tier_qualifying_views(self) -> None:
        contrib = self.qual_svc.classify_tier_contribution(
            tier="FREE",
            watch_seconds=3600,
            ad_impressions=12,
            is_qualifying=True,
            is_counted=True,
        )
        self.assertEqual(contrib.tier, "FREE")
        self.assertEqual(contrib.view_hours, Decimal("0.0000"))  # Excluded from sub pool
        self.assertEqual(contrib.ad_impressions, 12)             # Contributes to ad pool
        self.assertFalse(contrib.pool_eligible)
        self.assertTrue(contrib.ad_eligible)

    # -------------------------------------------------------------------------
    # Scenario 11: PREMIUM-tier qualifying views
    # -------------------------------------------------------------------------
    def test_11_premium_tier_qualifying_views(self) -> None:
        contrib = self.qual_svc.classify_tier_contribution(
            tier="PREMIUM",
            watch_seconds=4000,
            ad_impressions=5,  # Raw player telemetry might report ad slots; must be 0 for PREMIUM
            is_qualifying=True,
            is_counted=True,
        )
        self.assertEqual(contrib.tier, "PREMIUM")
        # 4000 / 3600 = 1.111111... -> 1.1111
        self.assertEqual(contrib.view_hours, Decimal("1.1111"))
        self.assertEqual(contrib.ad_impressions, 0)             # Excluded from ad pool
        self.assertTrue(contrib.pool_eligible)
        self.assertFalse(contrib.ad_eligible)

    # -------------------------------------------------------------------------
    # Scenario 12: Denied playback events
    # -------------------------------------------------------------------------
    def test_12_denied_playback_events_uncounted(self) -> None:
        # Event in window gap (Trap 2 / VW-001046)
        event = {
            "view_id": "VW-001046",
            "subscriber_id": "SUB-IN-0010",
            "tier": "PREMIUM",
            "territory_id": "IN",
            "title_id": "TTL-001",
            "start_utc": "2026-07-25 10:00:00",
            "watch_seconds": 3600,
            "ad_impressions": 0,
            "ingested_utc": "2026-07-25 11:00:00",
        }
        res = self.metering_svc.process_view_event(event)
        self.assertEqual(res["decision"], "DENIED")
        self.assertEqual(res["reason"], "OUTSIDE_WINDOW")
        self.assertEqual(res["counted"], "false")
        self.assertEqual(res["view_hours"], "0.0000")

    # -------------------------------------------------------------------------
    # Scenario 13: Different territories and time zone offsets
    # -------------------------------------------------------------------------
    def test_13_different_territories_timezones(self) -> None:
        utc_str = "2026-07-15 12:00:00"

        # India (UTC+05:30) -> 17:30:00
        ev_in = {
            "view_id": "VW-TZ-IN",
            "subscriber_id": "SUB-IN-01",
            "tier": "PREMIUM",
            "territory_id": "IN",
            "title_id": "TTL-011",
            "start_utc": utc_str,
            "watch_seconds": 3600,
        }
        res_in = self.metering_svc.process_view_event(ev_in)
        self.assertEqual(res_in["local_start"], "2026-07-15 17:30:00")

        # US (America/New_York UTC-04:00) -> 08:00:00
        ev_us = {
            "view_id": "VW-TZ-US",
            "subscriber_id": "SUB-US-01",
            "tier": "PREMIUM",
            "territory_id": "US",
            "title_id": "TTL-010",
            "start_utc": utc_str,
            "watch_seconds": 3600,
        }
        res_us = self.metering_svc.process_view_event(ev_us)
        self.assertEqual(res_us["local_start"], "2026-07-15 08:00:00")

        # Singapore (UTC+08:00) -> 20:00:00
        ev_sg = {
            "view_id": "VW-TZ-SG",
            "subscriber_id": "SUB-SG-01",
            "tier": "PREMIUM",
            "territory_id": "SG",
            "title_id": "TTL-003",
            "start_utc": utc_str,
            "watch_seconds": 3600,
        }
        res_sg = self.metering_svc.process_view_event(ev_sg)
        self.assertEqual(res_sg["local_start"], "2026-07-15 20:00:00")

    # -------------------------------------------------------------------------
    # Scenario 14: UTC midnight crossing (EC-06)
    # -------------------------------------------------------------------------
    def test_14_utc_midnight_crossing(self) -> None:
        # At 2026-07-20 20:30:00 UTC:
        # IN (+05:30) is 2026-07-21 02:00:00 (July 21st, after window expiry July 20th -> DENIED)
        # US (-04:00) is 2026-07-20 16:30:00 (July 20th, inside window -> ALLOWED)
        ev_in = {
            "view_id": "VW-001418",
            "subscriber_id": "SUB-IN-0010",
            "tier": "PREMIUM",
            "territory_id": "IN",
            "title_id": "TTL-007",
            "start_utc": "2026-07-20 20:30:00",
            "watch_seconds": 3600,
        }
        ev_us = {
            "view_id": "VW-001419",
            "subscriber_id": "SUB-US-0010",
            "tier": "PREMIUM",
            "territory_id": "US",
            "title_id": "TTL-010",
            "start_utc": "2026-07-20 20:30:00",
            "watch_seconds": 3600,
        }
        res_in = self.metering_svc.process_view_event(ev_in)
        res_us = self.metering_svc.process_view_event(ev_us)

        self.assertEqual(res_in["local_start"], "2026-07-21 02:00:00")
        self.assertEqual(res_in["decision"], "DENIED")

        self.assertEqual(res_us["local_start"], "2026-07-20 16:30:00")
        self.assertEqual(res_us["decision"], "ALLOWED")

    # -------------------------------------------------------------------------
    # Scenario 15: Late-ingested events (Trap 3 / VW-001661)
    # -------------------------------------------------------------------------
    def test_15_late_ingested_events_tagged_and_shifted(self) -> None:
        self.metering_svc.reset_state()
        # Mark 2026-07 as settled, advancing active settlement to 2026-09
        self.metering_svc.mark_month_settled("2026-07", "2026-09")

        # VW-001661: Playback started in July local (2026-07-25), but ingested late
        event = {
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
        res = self.metering_svc.process_view_event(event)

        self.assertEqual(res["decision"], "ALLOWED")
        self.assertEqual(res["tag"], "LATE_VIEW")
        self.assertEqual(res["settlement_month"], "2026-09")
        self.assertTrue(res["local_start"].startswith("2026-07-25"))

    # -------------------------------------------------------------------------
    # Scenario 16: Multiple views in the same month aggregation
    # -------------------------------------------------------------------------
    def test_16_multiple_views_same_month_aggregation(self) -> None:
        self.metering_svc.reset_state()
        # Create 3 views for TTL-011 in IN for 2026-07
        events = [
            {
                "view_id": "VW-AGG-1",
                "subscriber_id": "SUB-A",
                "tier": "PREMIUM",
                "territory_id": "IN",
                "title_id": "TTL-011",
                "start_utc": "2026-07-10 10:00:00",
                "watch_seconds": 3600,  # 1.0000 vh
            },
            {
                "view_id": "VW-AGG-2",
                "subscriber_id": "SUB-B",
                "tier": "PREMIUM",
                "territory_id": "IN",
                "title_id": "TTL-011",
                "start_utc": "2026-07-11 12:00:00",
                "watch_seconds": 1800,  # 0.5000 vh
            },
            {
                "view_id": "VW-AGG-3",
                "subscriber_id": "SUB-C",
                "tier": "FREE",
                "territory_id": "IN",
                "title_id": "TTL-011",
                "start_utc": "2026-07-12 14:00:00",
                "watch_seconds": 1800,
                "ad_impressions": 5,
            },
        ]
        self.metering_svc.process_views_batch(events)
        aggs = self.metering_svc.get_metering_aggregations(month="2026-07", territory_id="IN", title_id="TTL-011")

        self.assertEqual(len(aggs), 1)
        m = aggs[0]
        self.assertEqual(m["total_views"], 3)
        self.assertEqual(m["qualifying_views"], 3)
        self.assertEqual(m["qualifying_premium_views"], 2)
        self.assertEqual(m["qualifying_free_views"], 1)
        self.assertEqual(m["premium_view_hours"], Decimal("1.5000"))
        self.assertEqual(m["free_ad_impressions"], 5)

    # -------------------------------------------------------------------------
    # Scenario 17: Views spanning different months
    # -------------------------------------------------------------------------
    def test_17_views_spanning_different_months(self) -> None:
        self.metering_svc.reset_state()
        events = [
            {
                "view_id": "VW-M-JUL",
                "subscriber_id": "SUB-1",
                "tier": "PREMIUM",
                "territory_id": "IN",
                "title_id": "TTL-011",
                "start_utc": "2026-07-15 10:00:00",
                "watch_seconds": 3600,
            },
            {
                "view_id": "VW-M-AUG",
                "subscriber_id": "SUB-2",
                "tier": "PREMIUM",
                "territory_id": "IN",
                "title_id": "TTL-011",
                "start_utc": "2026-08-15 10:00:00",
                "watch_seconds": 7200,
            },
            {
                "view_id": "VW-M-SEP",
                "subscriber_id": "SUB-3",
                "tier": "PREMIUM",
                "territory_id": "IN",
                "title_id": "TTL-011",
                "start_utc": "2026-09-15 10:00:00",
                "watch_seconds": 1800,
            },
        ]
        self.metering_svc.process_views_batch(events)
        aggs = self.metering_svc.get_metering_aggregations(territory_id="IN", title_id="TTL-011")

        self.assertEqual(len(aggs), 3)
        months = {a["month"]: a["premium_view_hours"] for a in aggs}
        self.assertEqual(months["2026-07"], Decimal("1.0000"))
        self.assertEqual(months["2026-08"], Decimal("2.0000"))
        self.assertEqual(months["2026-09"], Decimal("0.5000"))


if __name__ == "__main__":
    unittest.main()
