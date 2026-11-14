"""
Unit and Integration Test Suite for Title, Licensor, and Licence Management Module.
Rigorously tests all 12 Functional Requirements:
1. Register a new title.
2. Store title ID, title name, runtime, release date and content category.
3. Register licensors and their country information.
4. Support multiple licensors for a single title.
5. Register licensor split percentages.
6. Ensure all licensor splits total exactly 100% (reject != 100.00%).
7. Create licence contracts.
8. Store territory, exclusivity, revenue-share type, MG and cap.
9. Support multiple windows under one licence.
10. Store window start and end dates.
11. Support theatrical and TV premiere information (45-day and 7-day holdback rules).
12. Allow licence information to be viewed, updated, and searched (including exclusivity collisions).
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

from database.connection import get_db_session, init_database, engine
from services.title_service import TitleService
from services.licensor_service import LicensorService
from services.licence_service import LicenceService
from validators.exceptions import (
    ValidationError,
    SplitValidationError,
    HoldbackViolationError,
    ExclusivityConflictError,
    EntityNotFoundError,
)
from cli.management_cli import main as cli_main


class TestTitleLicensorLicenceManagement(unittest.TestCase):
    """Test suite covering the 12 functional requirements of PS-090 Management Module."""

    @classmethod
    def setUpClass(cls) -> None:
        init_database(engine)
        cls.title_service = TitleService()
        cls.licensor_service = LicensorService()
        cls.licence_service = LicenceService()

    def setUp(self) -> None:
        self.suffix = uuid.uuid4().hex[:6].upper()

    # -------------------------------------------------------------------------
    # Req 1 & 2: Title Registration and Metadata Storage
    # -------------------------------------------------------------------------
    def test_01_register_title_with_complete_metadata(self) -> None:
        """Req 1 & 2: Register a title and store ID, name, runtime, release date, and content category."""
        t_id = f"T-TEST-{self.suffix}"
        t_name = f"Inception Test {self.suffix}"
        t_runtime = 8880  # 148 min
        t_release = date(2026, 1, 15)
        t_theatrical = date(2026, 1, 1)
        t_tv = date(2026, 3, 1)

        title = self.title_service.register_title(
            title_id=t_id,
            title_name=t_name,
            runtime_seconds=t_runtime,
            content_type="FILM",
            release_date=t_release,
            theatrical_premiere=t_theatrical,
            tv_premiere=t_tv,
        )

        self.assertEqual(title.title_id, t_id)
        self.assertEqual(title.title_name, t_name)
        self.assertEqual(title.duration_seconds, t_runtime)
        self.assertEqual(title.content_type, "FILM")
        self.assertEqual(title.release_date, t_release)
        self.assertEqual(title.theatrical_premiere, t_theatrical)
        self.assertEqual(title.tv_premiere, t_tv)

        # Retrieve and verify persistence
        fetched = self.title_service.get_title(t_id)
        self.assertEqual(fetched.title_name, t_name)
        self.assertEqual(fetched.duration_seconds, t_runtime)

    def test_02_register_title_validation_failures(self) -> None:
        """Req 2: Reject invalid runtime, blank title name, and unsupported categories."""
        # Non-positive runtime
        with self.assertRaises(ValidationError):
            self.title_service.register_title(
                title_id=f"T-INV-{self.suffix}",
                title_name="Invalid Runtime Title",
                runtime_seconds=0,
            )

        # Blank title name
        with self.assertRaises(ValidationError):
            self.title_service.register_title(
                title_id=f"T-INV2-{self.suffix}",
                title_name="   ",
                runtime_seconds=3600,
            )

        # Unsupported content category
        with self.assertRaises(ValidationError):
            self.title_service.register_title(
                title_id=f"T-INV3-{self.suffix}",
                title_name="Invalid Cat Title",
                runtime_seconds=3600,
                content_type="INVALID_CATEGORY",
            )

    # -------------------------------------------------------------------------
    # Req 3: Licensor Registration and Country Information
    # -------------------------------------------------------------------------
    def test_03_register_domestic_and_foreign_licensors(self) -> None:
        """Req 3: Register licensors, domicile country, residency, and tax treaty parameters."""
        # Domestic Indian licensor
        lic_in_id = f"LIC-IN-{self.suffix}"
        lic_in = self.licensor_service.register_licensor(
            licensor_id=lic_in_id,
            licensor_name=f"Bollywood Studio {self.suffix}",
            country="India",
            country_code="IN",
            is_indian=True,
        )
        self.assertEqual(lic_in.licensor_id, lic_in_id)
        self.assertEqual(lic_in.country, "India")
        self.assertEqual(lic_in.country_code, "IN")
        self.assertTrue(lic_in.is_indian)

        # Foreign US licensor with DTAA treaty TDS rate of 10.00%
        lic_us_id = f"LIC-US-{self.suffix}"
        lic_us = self.licensor_service.register_licensor(
            licensor_id=lic_us_id,
            licensor_name=f"Hollywood Pictures {self.suffix}",
            country="United States",
            country_code="US",
            is_indian=False,
            treaty_tds_pct=Decimal("10.00"),
        )
        self.assertEqual(lic_us.licensor_id, lic_us_id)
        self.assertFalse(lic_us.is_indian)
        self.assertEqual(lic_us.treaty_tds_pct, Decimal("10.00"))

        # Verify get and search
        fetched = self.licensor_service.get_licensor(lic_us_id)
        self.assertEqual(fetched.legal_name, f"Hollywood Pictures {self.suffix}")

        search_res = self.licensor_service.search_licensors(query=self.suffix)
        self.assertEqual(len(search_res), 2)

    # -------------------------------------------------------------------------
    # Req 4, 5, 6: Multiple Licensors and Exact 100% Split Rule
    # -------------------------------------------------------------------------
    def test_04_multiple_licensors_split_exact_100_percent(self) -> None:
        """Req 4, 5, 6: Multiple licensors for a single title with splits totaling exactly 100.00%."""
        # 1. Register title
        t_id = f"T-SPLIT-{self.suffix}"
        self.title_service.register_title(
            title_id=t_id,
            title_name="Co-Produced Blockbuster",
            runtime_seconds=7200,
        )

        # 2. Register 3 licensors
        lic1 = self.licensor_service.register_licensor(licensor_id=f"L1-{self.suffix}", licensor_name="Studio A", country="India")
        lic2 = self.licensor_service.register_licensor(licensor_id=f"L2-{self.suffix}", licensor_name="Studio B", country="United States")
        lic3 = self.licensor_service.register_licensor(licensor_id=f"L3-{self.suffix}", licensor_name="Studio C", country="United Kingdom")

        # 3. Set valid splits: 50.00% + 30.00% + 20.00% = 100.00%
        splits_payload = [
            {"licensor_id": lic1.licensor_id, "split_percentage": Decimal("50.00")},
            {"licensor_id": lic2.licensor_id, "split_percentage": Decimal("30.00")},
            {"licensor_id": lic3.licensor_id, "split_percentage": Decimal("20.00")},
        ]
        saved_splits = self.title_service.register_title_splits(t_id, splits_payload)
        self.assertEqual(len(saved_splits), 3)

        # Verify through query
        splits_fetched = self.title_service.get_title_splits(t_id)
        total_pct = sum(s.split_percentage for s in splits_fetched)
        self.assertEqual(total_pct, Decimal("100.00"))

    def test_05_reject_splits_not_summing_to_100_percent(self) -> None:
        """Req 6: Ensure all licensor splits total exactly 100%; reject 90.00% and 110.00%."""
        t_id = f"T-BAD-SPLIT-{self.suffix}"
        self.title_service.register_title(
            title_id=t_id,
            title_name="Split Validation Failure Test",
            runtime_seconds=5400,
        )
        lic1 = self.licensor_service.register_licensor(licensor_id=f"LB1-{self.suffix}", licensor_name="Studio Alpha", country="India")
        lic2 = self.licensor_service.register_licensor(licensor_id=f"LB2-{self.suffix}", licensor_name="Studio Beta", country="India")

        # Under 100% (60.00 + 30.00 = 90.00)
        with self.assertRaises(SplitValidationError) as ctx_under:
            self.title_service.register_title_splits(
                t_id,
                [
                    {"licensor_id": lic1.licensor_id, "split_percentage": Decimal("60.00")},
                    {"licensor_id": lic2.licensor_id, "split_percentage": Decimal("30.00")},
                ],
            )
        self.assertIn("100.00%", str(ctx_under.exception))
        self.assertIn("90.00", str(ctx_under.exception))

        # Over 100% (70.00 + 40.00 = 110.00)
        with self.assertRaises(SplitValidationError) as ctx_over:
            self.title_service.register_title_splits(
                t_id,
                [
                    {"licensor_id": lic1.licensor_id, "split_percentage": Decimal("70.00")},
                    {"licensor_id": lic2.licensor_id, "split_percentage": Decimal("40.00")},
                ],
            )
        self.assertIn("100.00%", str(ctx_over.exception))
        self.assertIn("110.00", str(ctx_over.exception))

    # -------------------------------------------------------------------------
    # Req 7 & 8: Licence Contracts with Commercial Terms (Territory, Exclusivity, Rev-Share, MG, Cap)
    # -------------------------------------------------------------------------
    def test_06_create_licence_contract_with_full_terms(self) -> None:
        """Req 7 & 8: Create licence storing territory, exclusivity, revenue-share type, MG, and cap."""
        t_id = f"T-LIC-{self.suffix}"
        self.title_service.register_title(title_id=t_id, title_name="Licensed Movie", runtime_seconds=6000)
        lic = self.licensor_service.register_licensor(licensor_id=f"L-LIC-{self.suffix}", licensor_name="Warner Dist", country="United States", country_code="US")

        lic_id = f"LIC-TEST-{self.suffix}"
        contract = self.licence_service.create_licence(
            licence_id=lic_id,
            title_id=t_id,
            licensor_id=lic.licensor_id,
            territory_id="IN",
            exclusivity="NON_EXCLUSIVE",
            revenue_share_type="POOL_AND_AD",
            mg_amount=Decimal("50000.00"),
            cap_amount=Decimal("200000.00"),
            windows=[
                {"window_no": 1, "window_start": "2026-06-01", "window_end": "2026-09-30"}
            ],
        )

        self.assertEqual(contract.contract_id, lic_id)
        self.assertEqual(contract.title_id, t_id)
        self.assertEqual(contract.territory_id, "IN")
        self.assertEqual(contract.exclusivity, "NON_EXCLUSIVE")
        self.assertEqual(contract.revenue_share_type, "POOL_AND_AD")
        self.assertEqual(contract.mg_amount, Decimal("50000.00"))
        self.assertEqual(contract.cap_amount, Decimal("200000.00"))
        self.assertEqual(len(contract.windows), 1)

    # -------------------------------------------------------------------------
    # Req 9 & 10: Multiple Windows and Start/End Dates
    # -------------------------------------------------------------------------
    def test_07_support_multiple_windows_under_one_licence(self) -> None:
        """Req 9 & 10: Support multiple availability windows and their start/end dates under one contract."""
        t_id = f"T-WIN-{self.suffix}"
        self.title_service.register_title(title_id=t_id, title_name="Multi-Window Epic", runtime_seconds=7500)
        lic = self.licensor_service.register_licensor(licensor_id=f"L-WIN-{self.suffix}", licensor_name="Universal", country="United States", country_code="US")

        lic_id = f"LIC-MWIN-{self.suffix}"
        # Contract created with initial window 1
        contract = self.licence_service.create_licence(
            licence_id=lic_id,
            title_id=t_id,
            licensor_id=lic.licensor_id,
            territory_id="US",
            exclusivity="NON_EXCLUSIVE",
            revenue_share_type="POOL_ONLY",
            windows=[
                {"window_no": 1, "window_start": "2026-05-01", "window_end": "2026-07-31"}
            ],
        )
        self.assertEqual(len(contract.windows), 1)

        # Add window 2 later
        win2 = self.licence_service.add_window(
            licence_id=lic_id,
            window_start="2026-10-01",
            window_end="2026-12-31",
            window_no=2,
            window_type="SVOD",
        )
        self.assertEqual(win2.window_no, 2)
        self.assertEqual(win2.window_start, date(2026, 10, 1))
        self.assertEqual(win2.window_end, date(2026, 12, 31))

        # Re-fetch and verify multiple windows
        refreshed = self.licence_service.get_licence(lic_id)
        self.assertEqual(len(refreshed.windows), 2)
        self.assertEqual(refreshed.expiration_date, date(2026, 12, 31))

    # -------------------------------------------------------------------------
    # Req 11: Theatrical and TV Premiere Holdback Rules (BR-02)
    # -------------------------------------------------------------------------
    def test_08_theatrical_and_tv_holdback_enforcement(self) -> None:
        """Req 11: Validate 45-day theatrical and 7-day TV premiere holdbacks."""
        # Title with Theatrical Premiere on 2026-04-01 -> Earliest allowed window: 2026-05-16 (+45 days)
        t_id = f"T-HOLD-{self.suffix}"
        self.title_service.register_title(
            title_id=t_id,
            title_name="Summer Tentpole",
            runtime_seconds=7000,
            theatrical_premiere=date(2026, 4, 1),
        )
        lic = self.licensor_service.register_licensor(licensor_id=f"L-HOLD-{self.suffix}", licensor_name="Sony Pictures", country="United States", country_code="US")

        # Attempt to create window starting on 2026-05-01 (only 30 days after theatrical premiere)
        with self.assertRaises(HoldbackViolationError) as ctx_theat:
            self.licence_service.create_licence(
                licence_id=f"LIC-FAIL1-{self.suffix}",
                title_id=t_id,
                licensor_id=lic.licensor_id,
                territory_id="IN",
                exclusivity="NON_EXCLUSIVE",
                revenue_share_type="POOL_AND_AD",
                windows=[{"window_start": "2026-05-01", "window_end": "2026-08-31"}],
            )
        self.assertEqual(ctx_theat.exception.premiere_type, "THEATRICAL")
        self.assertIn("violates the 45-day theatrical holdback", str(ctx_theat.exception))

        # Now create with compliant window starting on 2026-05-16 (+45 days) -> Must succeed
        compliant = self.licence_service.create_licence(
            licence_id=f"LIC-PASS1-{self.suffix}",
            title_id=t_id,
            licensor_id=lic.licensor_id,
            territory_id="IN",
            exclusivity="NON_EXCLUSIVE",
            revenue_share_type="POOL_AND_AD",
            windows=[{"window_start": "2026-05-16", "window_end": "2026-08-31"}],
        )
        self.assertEqual(compliant.contract_id, f"LIC-PASS1-{self.suffix}")

        # TV Holdback test: Title with TV Premiere on 2026-06-01 -> Earliest allowed window: 2026-06-08 (+7 days)
        t_tv_id = f"T-TV-{self.suffix}"
        self.title_service.register_title(
            title_id=t_tv_id,
            title_name="TV Special Episode",
            runtime_seconds=3600,
            tv_premiere=date(2026, 6, 1),
        )
        # Attempt starting on 2026-06-05 (only 4 days after TV premiere) -> Must fail
        with self.assertRaises(HoldbackViolationError) as ctx_tv:
            self.licence_service.create_licence(
                licence_id=f"LIC-FAIL2-{self.suffix}",
                title_id=t_tv_id,
                licensor_id=lic.licensor_id,
                territory_id="IN",
                exclusivity="NON_EXCLUSIVE",
                revenue_share_type="POOL_ONLY",
                windows=[{"window_start": "2026-06-05", "window_end": "2026-07-31"}],
            )
        self.assertEqual(ctx_tv.exception.premiere_type, "TV")
        self.assertIn("violates the 7-day TV holdback", str(ctx_tv.exception))

    # -------------------------------------------------------------------------
    # Req 12: Exclusivity Conflict Detection (BR-01) & Licence Management (View, Update, Search)
    # -------------------------------------------------------------------------
    def test_09_exclusivity_collision_prevention(self) -> None:
        """Req 12 & BR-01: Reject overlapping windows if either licence is EXCLUSIVE for same (title, territory)."""
        t_id = f"T-EXCL-{self.suffix}"
        self.title_service.register_title(title_id=t_id, title_name="Exclusivity Master", runtime_seconds=5000)
        lic1 = self.licensor_service.register_licensor(licensor_id=f"L-EX1-{self.suffix}", licensor_name="Studio Exclusive", country="United States", country_code="US")
        lic2 = self.licensor_service.register_licensor(licensor_id=f"L-EX2-{self.suffix}", licensor_name="Studio Challenger", country="United States", country_code="US")

        # 1. Create an EXCLUSIVE licence for territory 'IN' (2026-07-01 to 2026-09-30)
        lic_excl = self.licence_service.create_licence(
            licence_id=f"LIC-EXCL-1-{self.suffix}",
            title_id=t_id,
            licensor_id=lic1.licensor_id,
            territory_id="IN",
            exclusivity="EXCLUSIVE",
            revenue_share_type="POOL_AND_AD",
            windows=[{"window_start": "2026-07-01", "window_end": "2026-09-30"}],
        )
        self.assertEqual(lic_excl.exclusivity, "EXCLUSIVE")

        # 2. Candidate 2 attempts to create a NON_EXCLUSIVE licence for same title and territory with overlapping window
        with self.assertRaises(ExclusivityConflictError) as ctx_conflict:
            self.licence_service.create_licence(
                licence_id=f"LIC-EXCL-2-{self.suffix}",
                title_id=t_id,
                licensor_id=lic2.licensor_id,
                territory_id="IN",
                exclusivity="NON_EXCLUSIVE",
                revenue_share_type="POOL_ONLY",
                windows=[{"window_start": "2026-08-01", "window_end": "2026-11-30"}],
            )
        self.assertEqual(ctx_conflict.exception.conflicting_licence_id, f"LIC-EXCL-1-{self.suffix}")

        # 3. Candidate 2 in DIFFERENT territory ('US') with overlapping dates must succeed!
        lic_us = self.licence_service.create_licence(
            licence_id=f"LIC-DIFF-TERR-{self.suffix}",
            title_id=t_id,
            licensor_id=lic2.licensor_id,
            territory_id="US",
            exclusivity="NON_EXCLUSIVE",
            revenue_share_type="POOL_ONLY",
            windows=[{"window_start": "2026-08-01", "window_end": "2026-11-30"}],
        )
        self.assertEqual(lic_us.territory_id, "US")

    def test_10_licence_view_update_search_and_delete(self) -> None:
        """Req 12: View, update terms, search, and delete licence contracts."""
        t_id = f"T-CRUD-{self.suffix}"
        self.title_service.register_title(title_id=t_id, title_name="CRUD Target Film", runtime_seconds=6200)
        lic = self.licensor_service.register_licensor(licensor_id=f"L-CRUD-{self.suffix}", licensor_name="CRUD Studio", country="India", country_code="IN")

        lic_id = f"LIC-CRUD-{self.suffix}"
        created = self.licence_service.create_licence(
            licence_id=lic_id,
            title_id=t_id,
            licensor_id=lic.licensor_id,
            territory_id="IN",
            exclusivity="NON_EXCLUSIVE",
            revenue_share_type="POOL_AND_AD",
            mg_amount=Decimal("10000.00"),
            cap_amount=Decimal("50000.00"),
            windows=[{"window_start": "2026-06-01", "window_end": "2026-08-31"}],
        )
        self.assertEqual(created.status, "ACTIVE")

        # Update terms
        updated = self.licence_service.update_licence(
            licence_id=lic_id,
            mg_amount=Decimal("15000.00"),
            cap_amount=Decimal("75000.00"),
            status="TERMINATED",
        )
        self.assertEqual(updated.mg_amount, Decimal("15000.00"))
        self.assertEqual(updated.cap_amount, Decimal("75000.00"))
        self.assertEqual(updated.status, "TERMINATED")

        # Search licences
        search_res = self.licence_service.search_licences(title_id=t_id)
        self.assertEqual(len(search_res), 1)
        self.assertEqual(search_res[0].contract_id, lic_id)

        # Delete licence
        self.licence_service.delete_licence(lic_id)
        with self.assertRaises(EntityNotFoundError):
            self.licence_service.get_licence(lic_id)

    # -------------------------------------------------------------------------
    # CLI Command Line Testing
    # -------------------------------------------------------------------------
    def test_11_cli_end_to_end_execution(self) -> None:
        """Verify CLI commands execute cleanly and return proper exit codes."""
        cli_tid = f"T-CLI-{self.suffix}"
        cli_lid = f"L-CLI-{self.suffix}"
        cli_lic_id = f"C-CLI-{self.suffix}"

        # 1. Register Licensor via CLI
        code = cli_main(["licensor", "register", "--licensor-id", cli_lid, "--name", "CLI Studios", "--country", "India"])
        self.assertEqual(code, 0)

        # 2. Register Title via CLI
        code = cli_main(["title", "register", "--title-id", cli_tid, "--name", "CLI Title Test", "--runtime", "6000", "--category", "FILM"])
        self.assertEqual(code, 0)

        # 3. Set Splits via CLI (100%)
        code = cli_main(["title", "splits-set", "--title-id", cli_tid, "--splits", f"{cli_lid}:100.00"])
        self.assertEqual(code, 0)

        # 4. Create Licence via CLI
        code = cli_main([
            "licence", "create",
            "--licence-id", cli_lic_id,
            "--title-id", cli_tid,
            "--licensor-id", cli_lid,
            "--territory", "IN",
            "--exclusivity", "NON_EXCLUSIVE",
            "--rev-share-type", "POOL_AND_AD",
            "--windows", "2026-06-01:2026-08-31",
        ])
        self.assertEqual(code, 0)

        # 5. Get Licence via CLI
        code = cli_main(["licence", "get", "--licence-id", cli_lic_id])
        self.assertEqual(code, 0)

        # 6. Expect failure on invalid splits via CLI (90%)
        code = cli_main(["title", "splits-set", "--title-id", cli_tid, "--splits", f"{cli_lid}:90.00"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
