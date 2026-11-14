"""
Comprehensive Unit Test Suite for Playback Eligibility Engine (Phase 5).
Strictly covers all 14 required business rules and edge cases:
1. Valid active licence (ALLOWED).
2. Missing licence (DENIED).
3. Rejected licence (DENIED - rejected licences never authorize playback).
4. Wrong territory (DENIED - title licensed in one territory requested in another).
5. Playback before window start (DENIED - local time < window_start 00:00:00).
6. Playback after window end (DENIED - local time > window_end 23:59:59).
7. Multiple licence windows (ALLOWED in both Window 1 and Window 2).
8. Playback during a window gap (DENIED - between Window 1 and Window 2).
9. Playback at 23:59:59 on the final day (ALLOWED - EC-01 / VW-001417).
10. Two territories with different local times crossing UTC midnight (EC-06: IN DENIED, US ALLOWED).
11. Existing stream completing within 4 hours (ALLOWED to complete in full).
12. Existing stream exceeding 4 hours (effective watch duration capped at 4 hours).
13. New playback after window expiry (DENIED - title removed from catalogue).
14. Multiple NON_EXCLUSIVE licences (assigned to first-created licence).
15. Official sample dataset integration and evaluation output conformity.
16. Database telemetry persistence and playback decision history retrieval.
"""
from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_db_session, init_database, engine
from engine.playback_eligibility_engine import (
    PlaybackEligibilityEngine,
    PlaybackRequest,
    PlaybackDecision,
    MAX_IN_PROGRESS_STREAM_SECONDS,
)
from services.playback_service import PlaybackService
from services.title_service import TitleService
from services.licensor_service import LicensorService
from services.licence_service import LicenceService
from models.viewership import ViewEvent


class TestPlaybackEligibilityEngine(unittest.TestCase):
    """Test suite for BR-04, BR-05, and BR-06 Playback Eligibility."""

    @classmethod
    def setUpClass(cls) -> None:
        init_database(engine)
        cls.title_service = TitleService()
        cls.licensor_service = LicensorService()
        cls.licence_service = LicenceService()
        cls.playback_service = PlaybackService()

    def setUp(self) -> None:
        self.suffix = uuid.uuid4().hex[:6].upper()
        # Clean isolated engine instance
        self.territories = {
            "IN": {"territory_id": "IN", "utc_offset_minutes": 330},
            "AE": {"territory_id": "AE", "utc_offset_minutes": 240},
            "SG": {"territory_id": "SG", "utc_offset_minutes": 480},
            "US": {"territory_id": "US", "utc_offset_minutes": -240},
        }
        self.engine = PlaybackEligibilityEngine(
            territories=self.territories,
            licences={},
            windows={},
            titles={},
        )

    # -------------------------------------------------------------------------
    # Scenario 1: Valid active licence
    # -------------------------------------------------------------------------
    def test_01_valid_active_licence(self) -> None:
        """Scenario 1: Playback during an active licence window is ALLOWED and assigned to licence."""
        t_id = f"TTL-VAL-{self.suffix}"
        l_id = f"LCN-VAL-{self.suffix}"
        self.engine.licences[l_id] = {
            "licence_id": l_id,
            "title_id": t_id,
            "territory_id": "IN",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows[l_id] = [
            {"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-08-31"}
        ]

        # Request on 2026-07-15 12:00:00 UTC (17:30:00 IST) -> Within window
        req = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-001",
            tier="PREMIUM",
            territory_id="IN",
            playback_timestamp_utc="2026-07-15 12:00:00",
            watch_seconds=3600,
        )
        dec = self.engine.evaluate_playback(req, accepted_licences=[l_id])
        self.assertTrue(dec.is_allowed)
        self.assertEqual(dec.decision, "ALLOWED")
        self.assertEqual(dec.licence_id, l_id)
        self.assertEqual(dec.reason, "")
        self.assertEqual(dec.local_start_str, "2026-07-15 17:30:00")
        self.assertEqual(dec.effective_watch_seconds, 3600)

    # -------------------------------------------------------------------------
    # Scenario 2: Missing licence
    # -------------------------------------------------------------------------
    def test_02_missing_licence(self) -> None:
        """Scenario 2: Playback for an unlicensed title is DENIED with reason OUTSIDE_WINDOW."""
        req = PlaybackRequest(
            title_id=f"TTL-UNLICENSED-{self.suffix}",
            subscriber_id="SUB-002",
            tier="PREMIUM",
            territory_id="IN",
            playback_timestamp_utc="2026-07-15 12:00:00",
            watch_seconds=1800,
        )
        dec = self.engine.evaluate_playback(req, accepted_licences=[])
        self.assertFalse(dec.is_allowed)
        self.assertEqual(dec.decision, "DENIED")
        self.assertEqual(dec.reason, "OUTSIDE_WINDOW")
        self.assertEqual(dec.licence_id, "")

    # -------------------------------------------------------------------------
    # Scenario 3: Rejected licence
    # -------------------------------------------------------------------------
    def test_03_rejected_licence_never_authorizes_playback(self) -> None:
        """Scenario 3: A licence rejected during Phase 4 validation cannot authorize playback."""
        t_id = f"TTL-REJ-{self.suffix}"
        l_id_rej = f"LCN-REJECTED-{self.suffix}"

        # Licence exists in catalogue but was REJECTED during validation (omitted from accepted_licences)
        self.engine.licences[l_id_rej] = {
            "licence_id": l_id_rej,
            "title_id": t_id,
            "territory_id": "US",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows[l_id_rej] = [
            {"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-08-31"}
        ]

        req = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-003",
            tier="PREMIUM",
            territory_id="US",
            playback_timestamp_utc="2026-07-01 15:00:00",
            watch_seconds=2400,
        )
        # Accepted licences list does NOT contain l_id_rej because it was rejected
        dec = self.engine.evaluate_playback(req, accepted_licences=["OTHER-ACCEPTED-LCN"])
        self.assertFalse(dec.is_allowed)
        self.assertEqual(dec.decision, "DENIED")
        self.assertEqual(dec.licence_id, "")
        self.assertEqual(dec.reason, "OUTSIDE_WINDOW")

    # -------------------------------------------------------------------------
    # Scenario 4: Wrong territory
    # -------------------------------------------------------------------------
    def test_04_wrong_territory(self) -> None:
        """Scenario 4: Title licensed in IN requested in US is DENIED (geo-entitlement enforcement)."""
        t_id = f"TTL-GEO-{self.suffix}"
        l_id = f"LCN-IN-ONLY-{self.suffix}"
        self.engine.licences[l_id] = {
            "licence_id": l_id,
            "title_id": t_id,
            "territory_id": "IN",
            "exclusivity": "EXCLUSIVE",
        }
        self.engine.windows[l_id] = [
            {"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-12-31"}
        ]

        # Request from US for IN-only title
        req = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-US-001",
            tier="PREMIUM",
            territory_id="US",
            playback_timestamp_utc="2026-07-15 12:00:00",
            watch_seconds=1200,
        )
        dec = self.engine.evaluate_playback(req, accepted_licences=[l_id])
        self.assertFalse(dec.is_allowed)
        self.assertEqual(dec.decision, "DENIED")
        self.assertEqual(dec.reason, "OUTSIDE_WINDOW")

    # -------------------------------------------------------------------------
    # Scenario 5: Playback before window start
    # -------------------------------------------------------------------------
    def test_05_playback_before_window_start(self) -> None:
        """Scenario 5: Playback before window start date (e.g. 23:59:59 on the preceding day) is DENIED."""
        t_id = f"TTL-PRE-{self.suffix}"
        l_id = f"LCN-PRE-{self.suffix}"
        # Window starts 2026-07-01 00:00:00 local time
        self.engine.licences[l_id] = {
            "licence_id": l_id,
            "title_id": t_id,
            "territory_id": "IN",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows[l_id] = [
            {"window_no": 1, "window_start": "2026-07-01", "window_end": "2026-09-30"}
        ]

        # Local time: 2026-06-30 23:59:59 IST (1 second before window starts)
        # UTC: 2026-06-30 18:29:59 UTC
        req = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-005",
            tier="PREMIUM",
            territory_id="IN",
            playback_timestamp_utc="2026-06-30 18:29:59",
            watch_seconds=3600,
        )
        dec = self.engine.evaluate_playback(req, accepted_licences=[l_id])
        self.assertFalse(dec.is_allowed)
        self.assertEqual(dec.decision, "DENIED")
        self.assertEqual(dec.local_start_str, "2026-06-30 23:59:59")
        self.assertEqual(dec.reason, "OUTSIDE_WINDOW")

    # -------------------------------------------------------------------------
    # Scenario 6: Playback after window end
    # -------------------------------------------------------------------------
    def test_06_playback_after_window_end(self) -> None:
        """Scenario 6: New playback after window end date (e.g. 00:00:00 on the following day) is DENIED."""
        t_id = f"TTL-POST-{self.suffix}"
        l_id = f"LCN-POST-{self.suffix}"
        # Window ends 2026-08-31 23:59:59 local time
        self.engine.licences[l_id] = {
            "licence_id": l_id,
            "title_id": t_id,
            "territory_id": "IN",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows[l_id] = [
            {"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-08-31"}
        ]

        # Local time: 2026-09-01 00:00:00 IST (1 second after window expires)
        # UTC: 2026-08-31 18:30:00 UTC
        req = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-006",
            tier="PREMIUM",
            territory_id="IN",
            playback_timestamp_utc="2026-08-31 18:30:00",
            watch_seconds=1200,
        )
        dec = self.engine.evaluate_playback(req, accepted_licences=[l_id])
        self.assertFalse(dec.is_allowed)
        self.assertEqual(dec.decision, "DENIED")
        self.assertEqual(dec.local_start_str, "2026-09-01 00:00:00")
        self.assertEqual(dec.reason, "OUTSIDE_WINDOW")

    # -------------------------------------------------------------------------
    # Scenario 7: Multiple licence windows
    # -------------------------------------------------------------------------
    def test_07_multiple_licence_windows_allowed_in_both(self) -> None:
        """Scenario 7: Playback is ALLOWED in both Window 1 and Window 2 under the same licence."""
        t_id = f"TTL-MWIN-{self.suffix}"
        l_id = f"LCN-MWIN-{self.suffix}"
        self.engine.licences[l_id] = {
            "licence_id": l_id,
            "title_id": t_id,
            "territory_id": "AE",
            "exclusivity": "EXCLUSIVE",
        }
        self.engine.windows[l_id] = [
            {"window_no": 1, "window_start": "2026-05-01", "window_end": "2026-07-20"},
            {"window_no": 2, "window_start": "2026-08-20", "window_end": "2026-12-31"},
        ]

        # 1. Playback inside Window 1 (June 10 local)
        req_w1 = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-007",
            tier="PREMIUM",
            territory_id="AE",
            playback_timestamp_utc="2026-06-10 10:00:00",
            watch_seconds=3600,
        )
        dec1 = self.engine.evaluate_playback(req_w1, accepted_licences=[l_id])
        self.assertTrue(dec1.is_allowed)
        self.assertEqual(dec1.licence_id, l_id)

        # 2. Playback inside Window 2 (September 15 local)
        req_w2 = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-007",
            tier="PREMIUM",
            territory_id="AE",
            playback_timestamp_utc="2026-09-15 10:00:00",
            watch_seconds=3600,
        )
        dec2 = self.engine.evaluate_playback(req_w2, accepted_licences=[l_id])
        self.assertTrue(dec2.is_allowed)
        self.assertEqual(dec2.licence_id, l_id)

    # -------------------------------------------------------------------------
    # Scenario 8: Playback during a window gap
    # -------------------------------------------------------------------------
    def test_08_playback_during_window_gap_denied(self) -> None:
        """Scenario 8 & Trap 2: Playback during the blackout gap between Window 1 and Window 2 is DENIED."""
        t_id = f"TTL-GAP-{self.suffix}"
        l_id = f"LCN-GAP-{self.suffix}"
        # Gap is from 2026-07-21 to 2026-08-19
        self.engine.licences[l_id] = {
            "licence_id": l_id,
            "title_id": t_id,
            "territory_id": "AE",
            "exclusivity": "EXCLUSIVE",
        }
        self.engine.windows[l_id] = [
            {"window_no": 1, "window_start": "2026-05-01", "window_end": "2026-07-20"},
            {"window_no": 2, "window_start": "2026-08-20", "window_end": "2026-12-31"},
        ]

        # Playback on 2026-08-01 (Inside the gap) -> DENIED
        req_gap = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-008",
            tier="PREMIUM",
            territory_id="AE",
            playback_timestamp_utc="2026-08-01 12:00:00",
            watch_seconds=1800,
        )
        dec_gap = self.engine.evaluate_playback(req_gap, accepted_licences=[l_id])
        self.assertFalse(dec_gap.is_allowed)
        self.assertEqual(dec_gap.decision, "DENIED")
        self.assertEqual(dec_gap.reason, "OUTSIDE_WINDOW")

    # -------------------------------------------------------------------------
    # Scenario 9: Playback at 23:59:59 on the final day
    # -------------------------------------------------------------------------
    def test_09_playback_at_235959_on_final_day_allowed(self) -> None:
        """Scenario 9 & EC-01: Playback starting at 23:59:59 local time on window end day is ALLOWED."""
        t_id = f"TTL-FINAL-{self.suffix}"
        l_id = f"LCN-FINAL-{self.suffix}"
        self.engine.licences[l_id] = {
            "licence_id": l_id,
            "title_id": t_id,
            "territory_id": "IN",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows[l_id] = [
            {"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-08-31"}
        ]

        # 2026-08-31 18:29:59 UTC + 330 min = 2026-08-31 23:59:59 IST (Exact final second)
        req = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-009",
            tier="PREMIUM",
            territory_id="IN",
            playback_timestamp_utc="2026-08-31 18:29:59",
            watch_seconds=5400,  # 90 minutes
            view_id="VW-TEST-EC01",
        )
        dec = self.engine.evaluate_playback(req, accepted_licences=[l_id])
        self.assertTrue(dec.is_allowed)
        self.assertEqual(dec.decision, "ALLOWED")
        self.assertEqual(dec.local_start_str, "2026-08-31 23:59:59")
        self.assertEqual(dec.licence_id, l_id)

    # -------------------------------------------------------------------------
    # Scenario 10: Two territories crossing UTC midnight (EC-06)
    # -------------------------------------------------------------------------
    def test_10_two_territories_crossing_utc_midnight(self) -> None:
        """
        Scenario 10 & EC-06: Two territories ending on 2026-08-31 tested at the same instant (22:30:00 UTC).
        - IN (UTC+05:30) is 2026-09-01 04:00:00 IST -> DENIED (past Aug 31).
        - US (UTC-04:00) is 2026-08-31 18:30:00 EDT -> ALLOWED (inside Aug 31).
        """
        t_id = f"TTL-MIDNIGHT-{self.suffix}"
        l_in = f"LCN-IN-{self.suffix}"
        l_us = f"LCN-US-{self.suffix}"

        self.engine.licences[l_in] = {"licence_id": l_in, "title_id": t_id, "territory_id": "IN"}
        self.engine.windows[l_in] = [{"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-08-31"}]

        self.engine.licences[l_us] = {"licence_id": l_us, "title_id": t_id, "territory_id": "US"}
        self.engine.windows[l_us] = [{"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-08-31"}]

        same_instant_utc = "2026-08-31 22:30:00"

        # India: DENIED
        req_in = PlaybackRequest(
            title_id=t_id, subscriber_id="SUB-IN", tier="PREMIUM", territory_id="IN",
            playback_timestamp_utc=same_instant_utc, watch_seconds=1800,
        )
        dec_in = self.engine.evaluate_playback(req_in, accepted_licences=[l_in, l_us])
        self.assertFalse(dec_in.is_allowed)
        self.assertEqual(dec_in.decision, "DENIED")
        self.assertEqual(dec_in.local_start_str, "2026-09-01 04:00:00")

        # US: ALLOWED
        req_us = PlaybackRequest(
            title_id=t_id, subscriber_id="SUB-US", tier="PREMIUM", territory_id="US",
            playback_timestamp_utc=same_instant_utc, watch_seconds=1800,
        )
        dec_us = self.engine.evaluate_playback(req_us, accepted_licences=[l_in, l_us])
        self.assertTrue(dec_us.is_allowed)
        self.assertEqual(dec_us.decision, "ALLOWED")
        self.assertEqual(dec_us.local_start_str, "2026-08-31 18:30:00")
        self.assertEqual(dec_us.licence_id, l_us)

    # -------------------------------------------------------------------------
    # Scenario 11: Existing stream completing within 4 hours (BR-06)
    # -------------------------------------------------------------------------
    def test_11_existing_stream_completing_within_4_hours(self) -> None:
        """Scenario 11: A stream starting right before window expiry is allowed to complete up to 4 hours."""
        t_id = f"TTL-COMP4H-{self.suffix}"
        l_id = f"LCN-COMP4H-{self.suffix}"
        self.engine.licences[l_id] = {"licence_id": l_id, "title_id": t_id, "territory_id": "IN"}
        self.engine.windows[l_id] = [{"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-08-31"}]

        # Starts at 23:50:00 on window end day (10 min before window end)
        # Watches for 3 hours (10,800 seconds). Runs 2h 50m past midnight (< 4 hours)
        local_dt_start = datetime(2026, 8, 31, 23, 50, 0)
        # In UTC: 23:50 - 5h30m = 18:20:00
        req = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-011",
            tier="PREMIUM",
            territory_id="IN",
            playback_timestamp_utc="2026-08-31 18:20:00",
            watch_seconds=10800,
        )
        dec = self.engine.evaluate_playback(req, accepted_licences=[l_id])
        self.assertTrue(dec.is_allowed)
        self.assertTrue(dec.stream_completed_within_4h)
        self.assertFalse(dec.exceeded_4h_limit)
        self.assertEqual(dec.effective_watch_seconds, 10800)

    # -------------------------------------------------------------------------
    # Scenario 12: Existing stream exceeding 4 hours (BR-06)
    # -------------------------------------------------------------------------
    def test_12_existing_stream_exceeding_4_hours_capped(self) -> None:
        """Scenario 12: Stream attempting to run >4 hours past window expiry is capped at 4 hours allowance."""
        t_id = f"TTL-EXC4H-{self.suffix}"
        l_id = f"LCN-EXC4H-{self.suffix}"
        self.engine.licences[l_id] = {"licence_id": l_id, "title_id": t_id, "territory_id": "IN"}
        self.engine.windows[l_id] = [{"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-08-31"}]

        # Starts at 23:59:59 on window end day
        # Watches for 6 hours = 21,600 seconds
        req = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-012",
            tier="PREMIUM",
            territory_id="IN",
            playback_timestamp_utc="2026-08-31 18:29:59",
            watch_seconds=21600,
        )
        dec = self.engine.evaluate_playback(req, accepted_licences=[l_id])
        self.assertTrue(dec.is_allowed)
        self.assertTrue(dec.exceeded_4h_limit)
        # Should be capped at 1 second before midnight + 14400s = 14400s (or 14401s total)
        self.assertLessEqual(dec.effective_watch_seconds, 14401)
        self.assertGreaterEqual(dec.effective_watch_seconds, 14400)

    # -------------------------------------------------------------------------
    # Scenario 13: New playback after window expiry (BR-06 Catalogue Removal)
    # -------------------------------------------------------------------------
    def test_13_new_playback_after_window_expiry_forbidden(self) -> None:
        """Scenario 13: Once window expires, title is removed from catalogue; new playback is forbidden."""
        t_id = f"TTL-EXPIRED-{self.suffix}"
        l_id = f"LCN-EXPIRED-{self.suffix}"
        self.engine.licences[l_id] = {"licence_id": l_id, "title_id": t_id, "territory_id": "IN"}
        self.engine.windows[l_id] = [{"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-08-31"}]

        # Starts at 2026-09-01 00:00:01 local (1 second after midnight)
        req = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-013",
            tier="PREMIUM",
            territory_id="IN",
            playback_timestamp_utc="2026-08-31 18:30:01",
            watch_seconds=600,
        )
        dec = self.engine.evaluate_playback(req, accepted_licences=[l_id])
        self.assertFalse(dec.is_allowed)
        self.assertEqual(dec.decision, "DENIED")
        self.assertEqual(dec.reason, "OUTSIDE_WINDOW")

    # -------------------------------------------------------------------------
    # Scenario 14: Multiple NON_EXCLUSIVE licences (First created wins)
    # -------------------------------------------------------------------------
    def test_14_multiple_non_exclusive_licences_arbitration(self) -> None:
        """Scenario 14: When multiple NON_EXCLUSIVE licences overlap, playback is assigned to the first created."""
        t_id = f"TTL-MULTI-NONEX-{self.suffix}"
        l1 = f"LCN-01-FIRST-{self.suffix}"
        l2 = f"LCN-02-SECOND-{self.suffix}"

        self.engine.licences[l1] = {"licence_id": l1, "title_id": t_id, "territory_id": "SG", "exclusivity": "NON_EXCLUSIVE"}
        self.engine.windows[l1] = [{"window_no": 1, "window_start": "2026-06-15", "window_end": "2026-12-31"}]

        self.engine.licences[l2] = {"licence_id": l2, "title_id": t_id, "territory_id": "SG", "exclusivity": "NON_EXCLUSIVE"}
        self.engine.windows[l2] = [{"window_no": 1, "window_start": "2026-06-15", "window_end": "2026-12-31"}]

        req = PlaybackRequest(
            title_id=t_id,
            subscriber_id="SUB-014",
            tier="PREMIUM",
            territory_id="SG",
            playback_timestamp_utc="2026-07-01 10:00:00",
            watch_seconds=2000,
        )
        # In stream order: [l1, l2] -> l1 was created first
        dec = self.engine.evaluate_playback(req, accepted_licences=[l1, l2])
        self.assertTrue(dec.is_allowed)
        self.assertEqual(dec.licence_id, l1)

    # -------------------------------------------------------------------------
    # Scenario 15: Official Dataset View Events Batch Processing
    # -------------------------------------------------------------------------
    def test_15_official_sample_dataset_view_events_processing(self) -> None:
        """Scenario 15: Ingest real sample view_events.csv and check consistency with evaluations."""
        sample_views_path = PROJECT_ROOT / "sample_data" / "view_events.csv"
        if not sample_views_path.exists():
            self.skipTest("Sample data view_events.csv not found")

        decisions = self.playback_service.ingest_view_events_from_csv(
            csv_path=sample_views_path,
            cutoff_utc="2026-07-02 00:00:00",  # First day of views
        )
        self.assertGreater(len(decisions), 10)
        # Check first record VW-000001 (TTL-030 in IN on 2026-07-01 local start 07:01:29) -> DENIED OUTSIDE_WINDOW
        d1 = decisions[0]
        self.assertEqual(d1.view_id, "VW-000001")
        self.assertEqual(d1.decision, "DENIED")
        self.assertEqual(d1.reason, "OUTSIDE_WINDOW")

        # Check second record VW-000002 -> ALLOWED under LCN-024
        d2 = decisions[1]
        self.assertEqual(d2.view_id, "VW-000002")
        self.assertEqual(d2.decision, "ALLOWED")
        self.assertEqual(d2.licence_id, "LCN-024")

    # -------------------------------------------------------------------------
    # Scenario 16: Database Telemetry Persistence and Decision History
    # -------------------------------------------------------------------------
    def test_16_database_persistence_and_decision_history(self) -> None:
        """Scenario 16: Record playback request with DB persistence and query history."""
        t_id = f"T-DB-PB-{self.suffix}"
        self.title_service.register_title(title_id=t_id, title_name="DB Playback Title", runtime_seconds=5400)
        lic = self.licensor_service.register_licensor(licensor_id=f"L-DB-PB-{self.suffix}", licensor_name="DB Studio", country="India")

        lic_id = f"LIC-DB-PB-{self.suffix}"
        self.licence_service.create_licence(
            licence_id=lic_id,
            title_id=t_id,
            licensor_id=lic.licensor_id,
            territory_id="IN",
            exclusivity="NON_EXCLUSIVE",
            revenue_share_type="POOL_AND_AD",
            windows=[{"window_start": "2026-06-01", "window_end": "2026-10-31"}],
        )

        req = PlaybackRequest(
            title_id=t_id,
            subscriber_id=f"SUB-HIST-{self.suffix}",
            tier="PREMIUM",
            territory_id="IN",
            playback_timestamp_utc="2026-07-15 14:00:00",
            watch_seconds=3600,
            view_id=f"VW-HIST-{self.suffix}",
        )
        dec = self.playback_service.record_playback(req, persist_to_db=True, accepted_licences=[lic_id])
        self.assertTrue(dec.is_allowed)

        # Retrieve history
        history = self.playback_service.get_playback_history(subscriber_id=f"SUB-HIST-{self.suffix}")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].view_id, f"VW-HIST-{self.suffix}")
        self.assertEqual(history[0].decision, "ALLOWED")

        # Verify record in DB view_events table
        with get_db_session() as session:
            v_record = session.get(ViewEvent, f"VW-HIST-{self.suffix}")
            self.assertIsNotNone(v_record)
            self.assertEqual(v_record.title_id, t_id)
            self.assertEqual(v_record.territory_code, "IN")


if __name__ == "__main__":
    unittest.main()
