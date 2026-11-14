"""
Comprehensive Unit Test Suite for Licence Validation Engine.
Strictly tests BR-01, BR-02, BR-03, and all conflict edge cases:
- BR-01: Playback window validity, multiple windows, invalid dates, internal overlaps, and adjacent windows.
- BR-02: Exclusivity conflicts (EXCLUSIVE blocks others, NON_EXCLUSIVE coexists, conflicting licence ID reporting).
- BR-03: Theatrical (45-day) and TV (7-day) holdbacks with exact boundary validation (Day 44 rejected, Day 45 accepted; Day 6 rejected, Day 7 accepted).
- Multi-territory independence (territory-local dates, no conflict across territories).
- Audit trail logging in database and CSV generation.
"""
from __future__ import annotations

import unittest
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.licence_validation_engine import (
    LicenceValidationEngine,
    ValidationDecision,
    WindowRange,
)
from database.connection import get_db_session, init_database, engine
from models.audit import AuditLog
from services.licence_service import LicenceService
from services.title_service import TitleService
from services.licensor_service import LicensorService
from validators.exceptions import (
    ValidationError,
    HoldbackViolationError,
    ExclusivityConflictError,
)


class TestLicenceValidationEngine(unittest.TestCase):
    """Unit tests for the Licence Validation Engine."""

    @classmethod
    def setUpClass(cls) -> None:
        init_database(engine)
        cls.licence_service = LicenceService()
        cls.title_service = TitleService()
        cls.licensor_service = LicensorService()

    def setUp(self) -> None:
        self.suffix = uuid.uuid4().hex[:6].upper()
        # Initialize an isolated engine instance for each test
        self.engine = LicenceValidationEngine(
            titles={},
            licences={},
            windows={},
            enable_db_audit=True,
        )

    # =========================================================================
    # BR-01: Window Validation Tests
    # =========================================================================

    def test_br01_valid_single_and_multiple_windows(self) -> None:
        """BR-01: Valid single and multiple playback windows are correctly parsed."""
        raw_windows = [
            {"window_no": 1, "window_start": "2026-05-01", "window_end": "2026-07-20"},
            {"window_no": 2, "window_start": "2026-08-20", "window_end": "2026-12-31"},
        ]
        valid, reason, parsed = self.engine.validate_and_parse_windows(raw_windows)
        self.assertTrue(valid)
        self.assertEqual(reason, "")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].window_no, 1)
        self.assertEqual(parsed[0].start_date, date(2026, 5, 1))
        self.assertEqual(parsed[0].end_date, date(2026, 7, 20))
        self.assertEqual(parsed[1].window_no, 2)
        self.assertEqual(parsed[1].start_date, date(2026, 8, 20))
        self.assertEqual(parsed[1].end_date, date(2026, 12, 31))

    def test_br01_reject_start_date_after_end_date(self) -> None:
        """BR-01: Detect and reject invalid date ranges where start_date > end_date."""
        raw_windows = [
            {"window_no": 1, "window_start": "2026-09-01", "window_end": "2026-08-01"}
        ]
        valid, reason, parsed = self.engine.validate_and_parse_windows(raw_windows)
        self.assertFalse(valid)
        self.assertEqual(reason, "INVALID_WINDOW_DATES")
        self.assertEqual(len(parsed), 0)

    def test_br01_reject_missing_dates(self) -> None:
        """BR-01: Detect and reject windows with missing start or end dates."""
        raw_windows = [{"window_no": 1, "window_start": "2026-09-01", "window_end": ""}]
        valid, reason, parsed = self.engine.validate_and_parse_windows(raw_windows)
        self.assertFalse(valid)
        self.assertEqual(reason, "INVALID_WINDOW_DATES")

        valid2, reason2, _ = self.engine.validate_and_parse_windows([])
        self.assertFalse(valid2)
        self.assertEqual(reason2, "NO_WINDOWS_DEFINED")

    def test_br01_reject_internal_overlapping_windows(self) -> None:
        """BR-01: Detect and reject overlapping date ranges within the same candidate licence."""
        # Windows overlap from 2026-07-01 to 2026-07-20
        raw_windows = [
            {"window_no": 1, "window_start": "2026-05-01", "window_end": "2026-07-20"},
            {"window_no": 2, "window_start": "2026-07-01", "window_end": "2026-09-30"},
        ]
        valid, reason, parsed = self.engine.validate_and_parse_windows(raw_windows)
        self.assertFalse(valid)
        self.assertEqual(reason, "OVERLAPPING_INTERNAL_WINDOWS")

    def test_br01_allow_adjacent_windows(self) -> None:
        """BR-01: Adjacent contiguous windows (e.g. May 1 - July 20 and July 21 - Dec 31) are valid."""
        raw_windows = [
            {"window_no": 1, "window_start": "2026-05-01", "window_end": "2026-07-20"},
            {"window_no": 2, "window_start": "2026-07-21", "window_end": "2026-12-31"},
        ]
        valid, reason, parsed = self.engine.validate_and_parse_windows(raw_windows)
        self.assertTrue(valid)
        self.assertEqual(reason, "")
        self.assertEqual(len(parsed), 2)
        self.assertTrue(parsed[0].is_adjacent_to(parsed[1]))
        self.assertFalse(parsed[0].overlaps(parsed[1]))

    # =========================================================================
    # BR-02: Exclusivity Validation Tests
    # =========================================================================

    def test_br02_exclusive_blocks_exclusive_overlap(self) -> None:
        """BR-02: EXCLUSIVE licence blocks another EXCLUSIVE licence for same title and territory."""
        title_id = f"TTL-EX1-{self.suffix}"
        self.engine.titles[title_id] = {"title_id": title_id}

        # 1. Accept first EXCLUSIVE licence (IN, 2026-06-01 to 2026-08-31)
        self.engine.licences["LCN-001"] = {
            "licence_id": "LCN-001",
            "title_id": title_id,
            "territory_id": "IN",
            "exclusivity": "EXCLUSIVE",
        }
        self.engine.windows["LCN-001"] = [
            {"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-08-31"}
        ]
        dec1 = self.engine.validate_licence("LCN-001")
        self.assertTrue(dec1.is_accepted)
        self.assertEqual(dec1.result, "ACCEPTED")

        # 2. Candidate EXCLUSIVE licence overlapping (IN, 2026-08-01 to 2026-10-31)
        self.engine.licences["LCN-002"] = {
            "licence_id": "LCN-002",
            "title_id": title_id,
            "territory_id": "IN",
            "exclusivity": "EXCLUSIVE",
        }
        self.engine.windows["LCN-002"] = [
            {"window_no": 1, "window_start": "2026-08-01", "window_end": "2026-10-31"}
        ]
        dec2 = self.engine.validate_licence("LCN-002")
        self.assertFalse(dec2.is_accepted)
        self.assertEqual(dec2.result, "REJECTED")
        self.assertEqual(dec2.reason, "EXCLUSIVITY")
        self.assertEqual(dec2.conflicting_licence_id, "LCN-001")

    def test_br02_exclusive_blocks_non_exclusive_overlap(self) -> None:
        """BR-02: Existing EXCLUSIVE licence blocks incoming NON_EXCLUSIVE licence during overlapping window."""
        title_id = f"TTL-EX2-{self.suffix}"
        self.engine.titles[title_id] = {"title_id": title_id}

        # Accept EXCLUSIVE
        self.engine.licences["LCN-EX"] = {
            "licence_id": "LCN-EX",
            "title_id": title_id,
            "territory_id": "US",
            "exclusivity": "EXCLUSIVE",
        }
        self.engine.windows["LCN-EX"] = [
            {"window_no": 1, "window_start": "2026-07-01", "window_end": "2026-09-30"}
        ]
        self.engine.validate_licence("LCN-EX")

        # Candidate NON_EXCLUSIVE overlapping
        self.engine.licences["LCN-NONEX"] = {
            "licence_id": "LCN-NONEX",
            "title_id": title_id,
            "territory_id": "US",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows["LCN-NONEX"] = [
            {"window_no": 1, "window_start": "2026-08-15", "window_end": "2026-11-30"}
        ]
        dec = self.engine.validate_licence("LCN-NONEX")
        self.assertEqual(dec.result, "REJECTED")
        self.assertEqual(dec.reason, "EXCLUSIVITY")
        self.assertEqual(dec.conflicting_licence_id, "LCN-EX")

    def test_br02_non_exclusive_blocks_exclusive_overlap(self) -> None:
        """BR-02: Existing NON_EXCLUSIVE licence blocks incoming EXCLUSIVE licence during overlapping window."""
        title_id = f"TTL-EX3-{self.suffix}"
        self.engine.titles[title_id] = {"title_id": title_id}

        # Accept NON_EXCLUSIVE first
        self.engine.licences["LCN-N1"] = {
            "licence_id": "LCN-N1",
            "title_id": title_id,
            "territory_id": "SG",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows["LCN-N1"] = [
            {"window_no": 1, "window_start": "2026-06-15", "window_end": "2026-12-31"}
        ]
        self.engine.validate_licence("LCN-N1")

        # Incoming EXCLUSIVE cannot displace existing NON_EXCLUSIVE rights
        self.engine.licences["LCN-E2"] = {
            "licence_id": "LCN-E2",
            "title_id": title_id,
            "territory_id": "SG",
            "exclusivity": "EXCLUSIVE",
        }
        self.engine.windows["LCN-E2"] = [
            {"window_no": 1, "window_start": "2026-07-01", "window_end": "2026-08-31"}
        ]
        dec = self.engine.validate_licence("LCN-E2")
        self.assertEqual(dec.result, "REJECTED")
        self.assertEqual(dec.reason, "EXCLUSIVITY")
        self.assertEqual(dec.conflicting_licence_id, "LCN-N1")

    def test_br02_non_exclusive_licences_can_coexist(self) -> None:
        """BR-02: Multiple NON_EXCLUSIVE licences for the same title and territory can coexist."""
        title_id = f"TTL-COEXIST-{self.suffix}"
        self.engine.titles[title_id] = {"title_id": title_id}

        self.engine.licences["LCN-CO1"] = {
            "licence_id": "LCN-CO1",
            "title_id": title_id,
            "territory_id": "IN",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows["LCN-CO1"] = [
            {"window_no": 1, "window_start": "2026-06-15", "window_end": "2026-12-31"}
        ]
        dec1 = self.engine.validate_licence("LCN-CO1")
        self.assertTrue(dec1.is_accepted)

        self.engine.licences["LCN-CO2"] = {
            "licence_id": "LCN-CO2",
            "title_id": title_id,
            "territory_id": "IN",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows["LCN-CO2"] = [
            {"window_no": 1, "window_start": "2026-07-01", "window_end": "2026-10-31"}
        ]
        dec2 = self.engine.validate_licence("LCN-CO2")
        self.assertTrue(dec2.is_accepted)
        self.assertEqual(dec2.result, "ACCEPTED")
        self.assertEqual(dec2.reason, "")

    def test_br02_adjacent_windows_do_not_conflict_with_exclusive(self) -> None:
        """BR-02: An EXCLUSIVE licence does NOT conflict with adjacent windows (day after end date)."""
        title_id = f"TTL-ADJ-{self.suffix}"
        self.engine.titles[title_id] = {"title_id": title_id}

        # LCN-A ends on 2026-07-20 (EXCLUSIVE)
        self.engine.licences["LCN-A"] = {
            "licence_id": "LCN-A",
            "title_id": title_id,
            "territory_id": "AE",
            "exclusivity": "EXCLUSIVE",
        }
        self.engine.windows["LCN-A"] = [
            {"window_no": 1, "window_start": "2026-05-01", "window_end": "2026-07-20"}
        ]
        self.engine.validate_licence("LCN-A")

        # LCN-B starts on 2026-07-21 (Day after LCN-A ends) -> Must be ACCEPTED!
        self.engine.licences["LCN-B"] = {
            "licence_id": "LCN-B",
            "title_id": title_id,
            "territory_id": "AE",
            "exclusivity": "EXCLUSIVE",
        }
        self.engine.windows["LCN-B"] = [
            {"window_no": 1, "window_start": "2026-07-21", "window_end": "2026-09-30"}
        ]
        dec_b = self.engine.validate_licence("LCN-B")
        self.assertTrue(dec_b.is_accepted)
        self.assertEqual(dec_b.result, "ACCEPTED")

    def test_br02_different_territories_never_conflict(self) -> None:
        """BR-02: EXCLUSIVE licences in different territories do not conflict with each other."""
        title_id = f"TTL-TERR-{self.suffix}"
        self.engine.titles[title_id] = {"title_id": title_id}

        # EXCLUSIVE in IN
        self.engine.licences["LCN-IN"] = {
            "licence_id": "LCN-IN",
            "title_id": title_id,
            "territory_id": "IN",
            "exclusivity": "EXCLUSIVE",
        }
        self.engine.windows["LCN-IN"] = [
            {"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-12-31"}
        ]
        self.engine.validate_licence("LCN-IN")

        # EXCLUSIVE in US with identical dates
        self.engine.licences["LCN-US"] = {
            "licence_id": "LCN-US",
            "title_id": title_id,
            "territory_id": "US",
            "exclusivity": "EXCLUSIVE",
        }
        self.engine.windows["LCN-US"] = [
            {"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-12-31"}
        ]
        dec_us = self.engine.validate_licence("LCN-US")
        self.assertTrue(dec_us.is_accepted)
        self.assertEqual(dec_us.result, "ACCEPTED")

    # =========================================================================
    # BR-03: Holdback Validation Tests (Exact Boundary Precision)
    # =========================================================================

    def test_br03_theatrical_holdback_exact_boundary_day_44_vs_45(self) -> None:
        """
        BR-03 & EC-08: Validate exact 45th-day theatrical premiere holdback boundary.
        Theatrical premiere: 2026-05-22.
        - Day 44 (2026-07-05): REJECTED (reason: HOLDBACK).
        - Day 45 (2026-07-06): ACCEPTED.
        """
        premiere = date(2026, 5, 22)
        day_44 = premiere + timedelta(days=44)  # 2026-07-05
        day_45 = premiere + timedelta(days=45)  # 2026-07-06

        title_id = f"TTL-TH-{self.suffix}"
        self.engine.titles[title_id] = {
            "title_id": title_id,
            "theatrical_premiere": str(premiere),
        }

        # Attempt Day 44: Must be REJECTED with reason 'HOLDBACK'
        self.engine.licences["LCN-D44"] = {
            "licence_id": "LCN-D44",
            "title_id": title_id,
            "territory_id": "IN",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows["LCN-D44"] = [
            {"window_no": 1, "window_start": str(day_44), "window_end": "2026-12-31"}
        ]
        dec_44 = self.engine.validate_licence("LCN-D44")
        self.assertFalse(dec_44.is_accepted)
        self.assertEqual(dec_44.result, "REJECTED")
        self.assertEqual(dec_44.reason, "HOLDBACK")
        self.assertIn("45-day theatrical holdback", dec_44.message)

        # Attempt Day 45: Must be ACCEPTED
        self.engine.licences["LCN-D45"] = {
            "licence_id": "LCN-D45",
            "title_id": title_id,
            "territory_id": "IN",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows["LCN-D45"] = [
            {"window_no": 1, "window_start": str(day_45), "window_end": "2026-12-31"}
        ]
        dec_45 = self.engine.validate_licence("LCN-D45")
        self.assertTrue(dec_45.is_accepted)
        self.assertEqual(dec_45.result, "ACCEPTED")
        self.assertEqual(dec_45.reason, "")

    def test_br03_tv_holdback_exact_boundary_day_6_vs_7(self) -> None:
        """
        BR-03 & EC-08: Validate exact 7th-day TV premiere holdback boundary.
        TV premiere: 2026-06-26.
        - Day 6 (2026-07-02): REJECTED (reason: HOLDBACK).
        - Day 7 (2026-07-03): ACCEPTED.
        """
        tv_prem = date(2026, 6, 26)
        day_6 = tv_prem + timedelta(days=6)  # 2026-07-02
        day_7 = tv_prem + timedelta(days=7)  # 2026-07-03

        title_id = f"TTL-TV-{self.suffix}"
        self.engine.titles[title_id] = {
            "title_id": title_id,
            "tv_premiere": str(tv_prem),
        }

        # Attempt Day 6: Must be REJECTED with reason 'HOLDBACK'
        self.engine.licences["LCN-TV6"] = {
            "licence_id": "LCN-TV6",
            "title_id": title_id,
            "territory_id": "SG",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows["LCN-TV6"] = [
            {"window_no": 1, "window_start": str(day_6), "window_end": "2026-12-31"}
        ]
        dec_6 = self.engine.validate_licence("LCN-TV6")
        self.assertFalse(dec_6.is_accepted)
        self.assertEqual(dec_6.result, "REJECTED")
        self.assertEqual(dec_6.reason, "HOLDBACK")
        self.assertIn("7-day TV holdback", dec_6.message)

        # Attempt Day 7: Must be ACCEPTED
        self.engine.licences["LCN-TV7"] = {
            "licence_id": "LCN-TV7",
            "title_id": title_id,
            "territory_id": "SG",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows["LCN-TV7"] = [
            {"window_no": 1, "window_start": str(day_7), "window_end": "2026-12-31"}
        ]
        dec_7 = self.engine.validate_licence("LCN-TV7")
        self.assertTrue(dec_7.is_accepted)
        self.assertEqual(dec_7.result, "ACCEPTED")
        self.assertEqual(dec_7.reason, "")

    def test_br03_multiple_windows_holdback_compliance(self) -> None:
        """BR-03: Under multiple windows, if any window violates holdback, contract is rejected."""
        premiere = date(2026, 4, 1)  # 45 days is 2026-05-16
        title_id = f"TTL-MW-HOLD-{self.suffix}"
        self.engine.titles[title_id] = {
            "title_id": title_id,
            "theatrical_premiere": str(premiere),
        }

        # Window 1 violates (starts 2026-05-01 < 2026-05-16), Window 2 compliant (starts 2026-08-01)
        self.engine.licences["LCN-MW-FAIL"] = {
            "licence_id": "LCN-MW-FAIL",
            "title_id": title_id,
            "territory_id": "IN",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows["LCN-MW-FAIL"] = [
            {"window_no": 1, "window_start": "2026-05-01", "window_end": "2026-06-30"},
            {"window_no": 2, "window_start": "2026-08-01", "window_end": "2026-10-31"},
        ]
        dec_fail = self.engine.validate_licence("LCN-MW-FAIL")
        self.assertEqual(dec_fail.result, "REJECTED")
        self.assertEqual(dec_fail.reason, "HOLDBACK")

    # =========================================================================
    # Additional Requirements: Audit Logging & Database Integration Tests
    # =========================================================================

    def test_audit_logging_to_database(self) -> None:
        """Verify that every validation acceptance and rejection writes an audit log in DB."""
        title_id = f"TTL-AUDIT-{self.suffix}"
        self.engine.titles[title_id] = {"title_id": title_id}

        test_lic_id = f"LCN-AUDIT-{self.suffix}"
        self.engine.licences[test_lic_id] = {
            "licence_id": test_lic_id,
            "title_id": title_id,
            "territory_id": "US",
            "exclusivity": "NON_EXCLUSIVE",
        }
        self.engine.windows[test_lic_id] = [
            {"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-09-30"}
        ]

        dec = self.engine.validate_licence(test_lic_id)
        self.assertTrue(dec.is_accepted)
        self.assertIsNotNone(dec.audit_id)

        # Query database AuditLog table
        with get_db_session() as session:
            log_entry = session.get(AuditLog, dec.audit_id)
            self.assertIsNotNone(log_entry)
            self.assertEqual(log_entry.table_name, "licence_contracts")
            self.assertEqual(log_entry.record_id, test_lic_id)
            self.assertEqual(log_entry.action, "VALIDATION_ACCEPTED")
            self.assertIn("ACCEPTED", log_entry.new_values_json)

    def test_service_level_audit_and_exceptions(self) -> None:
        """Verify LicenceService records audit logs on contract creation and raises domain exceptions."""
        t_id = f"T-SRV-{self.suffix}"
        self.title_service.register_title(title_id=t_id, title_name="Service Audit Film", runtime_seconds=6000)
        lic = self.licensor_service.register_licensor(licensor_id=f"L-SRV-{self.suffix}", licensor_name="Srv Studio", country="India")

        lic_id = f"LIC-SRV-{self.suffix}"
        contract = self.licence_service.create_licence(
            licence_id=lic_id,
            title_id=t_id,
            licensor_id=lic.licensor_id,
            territory_id="IN",
            exclusivity="EXCLUSIVE",
            revenue_share_type="POOL_AND_AD",
            windows=[{"window_start": "2026-06-01", "window_end": "2026-08-31"}],
        )
        self.assertEqual(contract.contract_id, lic_id)

        # Retrieve audit logs for this contract
        audit_logs = self.licence_service.get_audit_logs(licence_id=lic_id)
        self.assertTrue(len(audit_logs) >= 1)
        self.assertEqual(audit_logs[0].action, "CONTRACT_CREATED")

        # Conflict attempt on same title/territory
        with self.assertRaises(ExclusivityConflictError) as ctx_err:
            self.licence_service.create_licence(
                licence_id=f"LIC-SRV-2-{self.suffix}",
                title_id=t_id,
                licensor_id=lic.licensor_id,
                territory_id="IN",
                exclusivity="NON_EXCLUSIVE",
                revenue_share_type="POOL_ONLY",
                windows=[{"window_start": "2026-07-01", "window_end": "2026-09-30"}],
            )
        self.assertEqual(ctx_err.exception.conflicting_licence_id, lic_id)


if __name__ == "__main__":
    unittest.main()
