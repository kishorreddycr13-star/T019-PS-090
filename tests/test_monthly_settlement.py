"""
Comprehensive Unit Tests for Monthly Settlement and Output Generation Engine (Phase 9).
Covers all 20 required scenarios specified in Section 9 of PS-090:
 1. Normal monthly settlement.
 2. Settlement on the 10th of the following month.
 3. Settlement before the permitted date (SettlementTimingError).
 4. Events ingested before cutoff.
 5. Events ingested exactly at cutoff.
 6. Late events shifted to M+1.
 7. LATE_VIEW tagging.
 8. Late events settled at M+1 rates.
 9. FREE and PREMIUM revenue separation.
10. Multiple territories.
11. Multiple licensors.
12. MG recoupment integration.
13. Cap integration.
14. TDS integration.
15. Co-licensor split integration.
16. POOL_ONLY licence.
17. POOL_AND_AD licence.
18. Duplicate settlement prevention.
19. Failed settlement rollback.
20. Exact CSV column formatting and ordering.
"""
from __future__ import annotations

import csv
import io
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.settlement_service import SettlementService
from services.reporting_service import ReportingService
from engine.revenue_settlement_engine import RevenueSettlementEngine
from engine.view_processor import ViewProcessor
from engine.windowing_service import WindowingService
from validators.exceptions import SettlementTimingError, DuplicateSettlementError
from models.settlement import MonthlySettlement


class TestMonthlySettlementEngine(unittest.TestCase):
    """Test suite for Phase 9 Monthly Settlement & Output Generation."""

    def setUp(self) -> None:
        self.territories = {
            "IN": {"territory_id": "IN", "utc_offset_minutes": "330"},
            "US": {"territory_id": "US", "utc_offset_minutes": "-240"},
            "SG": {"territory_id": "SG", "utc_offset_minutes": "480"},
            "AE": {"territory_id": "AE", "utc_offset_minutes": "240"},
        }
        self.licensors = {
            "LIC-IND": {"licensor_id": "LIC-IND", "is_indian": "true", "treaty_tds_pct": ""},
            "LIC-FOR": {"licensor_id": "LIC-FOR", "is_indian": "false", "treaty_tds_pct": ""},
            "LIC-TRY": {"licensor_id": "LIC-TRY", "is_indian": "false", "treaty_tds_pct": "15.00"},
            "LIC-LEAD": {"licensor_id": "LIC-LEAD", "is_indian": "true", "treaty_tds_pct": ""},
            "LIC-CO": {"licensor_id": "LIC-CO", "is_indian": "true", "treaty_tds_pct": ""},
        }
        self.titles = {
            "TTL-01": {"title_id": "TTL-01", "runtime_seconds": "3600", "theatrical_premiere": "", "tv_premiere": ""},
            "TTL-02": {"title_id": "TTL-02", "runtime_seconds": "180", "theatrical_premiere": "", "tv_premiere": ""},
        }
        self.title_splits = {
            "TTL-01": [
                {"title_id": "TTL-01", "licensor_id": "LIC-LEAD", "split_pct": "60.00"},
                {"title_id": "TTL-01", "licensor_id": "LIC-CO", "split_pct": "40.00"},
            ]
        }
        self.licences = {
            "LCN-POOLAD": {
                "licence_id": "LCN-POOLAD",
                "title_id": "TTL-01",
                "licensor_id": "LIC-LEAD",
                "territory_id": "IN",
                "exclusivity": "EXCLUSIVE",
                "revenue_share_type": "POOL_AND_AD",
                "mg_amount": "0.00",
                "cap_amount": "0.00",
            },
            "LCN-POOLONLY": {
                "licence_id": "LCN-POOLONLY",
                "title_id": "TTL-02",
                "licensor_id": "LIC-IND",
                "territory_id": "IN",
                "exclusivity": "NON_EXCLUSIVE",
                "revenue_share_type": "POOL_ONLY",
                "mg_amount": "0.00",
                "cap_amount": "0.00",
            },
            "LCN-MG": {
                "licence_id": "LCN-MG",
                "title_id": "TTL-02",
                "licensor_id": "LIC-FOR",
                "territory_id": "US",
                "exclusivity": "EXCLUSIVE",
                "revenue_share_type": "POOL_AND_AD",
                "mg_amount": "1000.00",
                "cap_amount": "0.00",
            },
            "LCN-CAP": {
                "licence_id": "LCN-CAP",
                "title_id": "TTL-02",
                "licensor_id": "LIC-TRY",
                "territory_id": "SG",
                "exclusivity": "EXCLUSIVE",
                "revenue_share_type": "POOL_AND_AD",
                "mg_amount": "0.00",
                "cap_amount": "500.00",
            },
        }
        self.windows = {
            "LCN-POOLAD": [{"licence_id": "LCN-POOLAD", "window_no": 1, "window_start": "2026-07-01", "window_end": "2026-09-30"}],
            "LCN-POOLONLY": [{"licence_id": "LCN-POOLONLY", "window_no": 1, "window_start": "2026-07-01", "window_end": "2026-09-30"}],
            "LCN-MG": [{"licence_id": "LCN-MG", "window_no": 1, "window_start": "2026-07-01", "window_end": "2026-09-30"}],
            "LCN-CAP": [{"licence_id": "LCN-CAP", "window_no": 1, "window_start": "2026-07-01", "window_end": "2026-09-30"}],
        }
        self.sub_rev = {
            ("2026-07", "IN"): Decimal("10000.00"),
            ("2026-07", "US"): Decimal("5000.00"),
            ("2026-07", "SG"): Decimal("8000.00"),
            ("2026-07", "AE"): Decimal("3000.00"),
            ("2026-08", "IN"): Decimal("12000.00"),
            ("2026-08", "US"): Decimal("6000.00"),
            ("2026-08", "SG"): Decimal("9000.00"),
            ("2026-08", "AE"): Decimal("4000.00"),
        }
        self.ad_rev = {
            ("2026-07", "IN"): Decimal("2000.00"),
            ("2026-07", "US"): Decimal("1000.00"),
            ("2026-07", "SG"): Decimal("1500.00"),
            ("2026-07", "AE"): Decimal("500.00"),
            ("2026-08", "IN"): Decimal("2500.00"),
            ("2026-08", "US"): Decimal("1200.00"),
            ("2026-08", "SG"): Decimal("1800.00"),
            ("2026-08", "AE"): Decimal("600.00"),
        }

        self.engine = RevenueSettlementEngine(
            territories=self.territories,
            licensors=self.licensors,
            titles=self.titles,
            title_splits=self.title_splits,
            licences=self.licences,
            windows=self.windows,
            subscription_revenue=self.sub_rev,
            ad_revenue=self.ad_rev,
        )
        self.service = SettlementService(settlement_engine=self.engine)

    # 1. Normal monthly settlement
    def test_normal_monthly_settlement(self):
        views = [
            {
                "view_id": "VW-01",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "IN",
                "_title_id": "TTL-01",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            }
        ]
        t_shares, settlements = self.service.settle_month(
            month="2026-07",
            run_ts="2026-08-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-POOLAD"],
            persist_db=False,
        )
        self.assertGreater(len(t_shares), 0)
        self.assertGreater(len(settlements), 0)
        self.assertTrue(self.service.is_month_settled("2026-07"))

    # 2. Settlement on the 10th of following month
    def test_settlement_on_10th_of_following_month(self):
        # Permitted run on 10th at 00:00:00 UTC
        earliest = SettlementService.get_earliest_permitted_timestamp("2026-07")
        self.assertEqual(earliest, "2026-08-10 00:00:00")
        # Validating at or after 10th should succeed without exception
        self.service.validate_settlement_timing("2026-07", "2026-08-10 00:00:00")
        self.service.validate_settlement_timing("2026-07", "2026-08-10 15:30:00")
        self.service.validate_settlement_timing("2026-07", "2026-08-11 00:00:00")

    # 3. Settlement before permitted date (SettlementTimingError)
    def test_settlement_before_permitted_date(self):
        with self.assertRaises(SettlementTimingError) as ctx:
            self.service.validate_settlement_timing("2026-07", "2026-08-09 23:59:59")
        self.assertEqual(ctx.exception.month, "2026-07")
        self.assertEqual(ctx.exception.earliest_permitted, "2026-08-10 00:00:00")

        with self.assertRaises(SettlementTimingError):
            self.service.settle_month(
                month="2026-07",
                run_ts="2026-07-31 23:59:59",
                view_decisions=[],
                accepted_licences=["LCN-POOLAD"],
                persist_db=False,
            )

    # 4. Events ingested before cutoff
    def test_events_ingested_before_cutoff(self):
        window_svc = WindowingService(self.territories, self.licences, self.windows)
        view_events = [
            {
                "view_id": "VW-PRE",
                "subscriber_id": "SUB-1",
                "tier": "PREMIUM",
                "territory_id": "IN",
                "title_id": "TTL-01",
                "start_utc": "2026-07-15 10:00:00",
                "watch_seconds": "3000",
                "ad_impressions": "0",
                "ingested_utc": "2026-08-09 18:00:00",  # strictly before cutoff 2026-08-10 00:00:00
            }
        ]
        vp = ViewProcessor(self.titles, view_events, window_svc)
        processed = vp.process_views_until("2026-08-10 00:00:00", ["LCN-POOLAD"])
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0]["view_id"], "VW-PRE")
        self.assertEqual(processed[0]["settlement_month"], "2026-07")

    # 5. Events ingested exactly at cutoff
    def test_events_ingested_exactly_at_cutoff(self):
        window_svc = WindowingService(self.territories, self.licences, self.windows)
        view_events = [
            {
                "view_id": "VW-EXACT",
                "subscriber_id": "SUB-1",
                "tier": "PREMIUM",
                "territory_id": "IN",
                "title_id": "TTL-01",
                "start_utc": "2026-07-15 10:00:00",
                "watch_seconds": "3000",
                "ad_impressions": "0",
                "ingested_utc": "2026-08-10 00:00:00",  # exactly at cutoff instant
            }
        ]
        vp = ViewProcessor(self.titles, view_events, window_svc)
        # Process views until cutoff instant
        processed = vp.process_views_until("2026-08-10 00:00:00", ["LCN-POOLAD"])
        # Exactly at cutoff must be deferred to next cycle
        self.assertEqual(len(processed), 0)

    # 6. Late events shifted to M+1
    def test_late_events_shifted_to_next_month(self):
        window_svc = WindowingService(self.territories, self.licences, self.windows)
        view_events = [
            {
                "view_id": "VW-LATE",
                "subscriber_id": "SUB-2",
                "tier": "PREMIUM",
                "territory_id": "IN",
                "title_id": "TTL-01",
                "start_utc": "2026-07-20 12:00:00",  # Local July
                "watch_seconds": "2000",
                "ad_impressions": "0",
                "ingested_utc": "2026-08-15 00:00:00",  # Ingested after July settlement
            }
        ]
        vp = ViewProcessor(self.titles, view_events, window_svc)
        vp.mark_month_settled("2026-07", "2026-08")
        processed = vp.process_views_until("2026-09-10 00:00:00", ["LCN-POOLAD"])
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0]["settlement_month"], "2026-08")

    # 7. LATE_VIEW tagging
    def test_late_view_tagging(self):
        window_svc = WindowingService(self.territories, self.licences, self.windows)
        view_events = [
            {
                "view_id": "VW-TAG",
                "subscriber_id": "SUB-3",
                "tier": "PREMIUM",
                "territory_id": "IN",
                "title_id": "TTL-01",
                "start_utc": "2026-07-25 12:00:00",
                "watch_seconds": "2000",
                "ad_impressions": "0",
                "ingested_utc": "2026-08-20 00:00:00",
            }
        ]
        vp = ViewProcessor(self.titles, view_events, window_svc)
        vp.mark_month_settled("2026-07", "2026-08")
        processed = vp.process_views_until("2026-09-10 00:00:00", ["LCN-POOLAD"])
        self.assertEqual(processed[0]["tag"], "LATE_VIEW")

    # 8. Late events settled at M+1 rates
    def test_late_events_settled_at_next_month_rates(self):
        views = [
            {
                "view_id": "VW-SHIFTED",
                "settlement_month": "2026-08",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "IN",
                "_title_id": "TTL-01",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            }
        ]
        t_shares, settlements = self.service.settle_month(
            month="2026-08",
            run_ts="2026-09-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-POOLAD"],
            persist_db=False,
        )
        # August IN sub rev is 12000, 60% pool = 7200. TTL-01 has 100% of hours -> 7200 pool share
        in_ts = next(ts for ts in t_shares if ts["territory_id"] == "IN" and ts["title_id"] == "TTL-01")
        self.assertEqual(Decimal(in_ts["pool_share"]), Decimal("7200.00"))

    # 9. FREE and PREMIUM revenue separation
    def test_free_and_premium_revenue_separation(self):
        views = [
            {
                "view_id": "VW-PREM",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "IN",
                "_title_id": "TTL-01",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            },
            {
                "view_id": "VW-FREE",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "FREE",
                "_territory_id": "IN",
                "_title_id": "TTL-01",
                "_watch_seconds": 3600,
                "_ad_impressions": 100,
            },
        ]
        t_shares, _ = self.service.settle_month(
            month="2026-07",
            run_ts="2026-08-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-POOLAD"],
            persist_db=False,
        )
        in_ts = next(ts for ts in t_shares if ts["territory_id"] == "IN" and ts["title_id"] == "TTL-01")
        # 60% of 10,000 = 6,000
        self.assertEqual(Decimal(in_ts["pool_share"]), Decimal("6000.00"))
        # 55% of 2,000 = 1,100
        self.assertEqual(Decimal(in_ts["ad_share"]), Decimal("1100.00"))
        self.assertEqual(Decimal(in_ts["title_share"]), Decimal("7100.00"))

    # 10. Multiple territories
    def test_multiple_territories(self):
        views = [
            {
                "view_id": "VW-IN",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "IN",
                "_title_id": "TTL-01",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            },
            {
                "view_id": "VW-US",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "US",
                "_title_id": "TTL-02",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            },
        ]
        t_shares, _ = self.service.settle_month(
            month="2026-07",
            run_ts="2026-08-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-POOLAD", "LCN-MG"],
            persist_db=False,
        )
        terr_ids = {ts["territory_id"] for ts in t_shares}
        self.assertTrue({"IN", "US", "SG", "AE"}.issubset(terr_ids))

    # 11. Multiple licensors
    def test_multiple_licensors(self):
        views = [
            {
                "view_id": "VW-1",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "IN",
                "_title_id": "TTL-01",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            }
        ]
        # TTL-01 is licensed by LIC-LEAD (60%) and LIC-CO (40%)
        _, settlements = self.service.settle_month(
            month="2026-07",
            run_ts="2026-08-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-POOLAD"],
            persist_db=False,
        )
        lic_ids = [s["licensor_id"] for s in settlements]
        self.assertIn("LIC-LEAD", lic_ids)
        self.assertIn("LIC-CO", lic_ids)

    # 12. MG recoupment integration
    def test_mg_recoupment_integration(self):
        # LCN-MG has MG amount = 1000.00
        views = [
            {
                "view_id": "VW-US",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "US",
                "_title_id": "TTL-02",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            }
        ]
        # Month 1: 60% of 5000 = 3000 gross. MG is 1000. Recouped = 1000, MG balance = 0.
        _, settlements = self.service.settle_month(
            month="2026-07",
            run_ts="2026-08-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-MG"],
            persist_db=False,
        )
        s = next(row for row in settlements if row["licence_id"] == "LCN-MG")
        self.assertEqual(Decimal(s["mg_paid"]), Decimal("1000.00"))
        self.assertEqual(Decimal(s["recouped"]), Decimal("1000.00"))
        self.assertEqual(Decimal(s["mg_balance"]), Decimal("0.00"))

    # 13. Cap integration
    def test_cap_integration(self):
        # LCN-CAP has cap = 500.00
        views = [
            {
                "view_id": "VW-SG",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "SG",
                "_title_id": "TTL-02",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            }
        ]
        # Pool is 60% of 8000 = 4800 gross. Cap is 500. Retained = 4300.
        _, settlements = self.service.settle_month(
            month="2026-07",
            run_ts="2026-08-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-CAP"],
            persist_db=False,
        )
        s = next(row for row in settlements if row["licence_id"] == "LCN-CAP")
        self.assertEqual(Decimal(s["payable_before_tds"]), Decimal("500.00"))
        self.assertEqual(Decimal(s["cap_retained"]), Decimal("4300.00"))
        self.assertEqual(s["status"], "CAPPED")

    # 14. TDS integration
    def test_tds_integration(self):
        # LIC-IND -> 10%, LIC-FOR -> 20%, LIC-TRY -> 15%
        views = [
            {
                "view_id": "VW-1",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "SG",
                "_title_id": "TTL-02",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            }
        ]
        # LCN-CAP is with LIC-TRY (treaty TDS 15.00%)
        _, settlements = self.service.settle_month(
            month="2026-07",
            run_ts="2026-08-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-CAP"],
            persist_db=False,
        )
        s = next(row for row in settlements if row["licence_id"] == "LCN-CAP")
        self.assertEqual(Decimal(s["tds_pct"]), Decimal("15.00"))
        # Payable before TDS is 500, TDS is 75.00, net is 425.00
        self.assertEqual(Decimal(s["tds"]), Decimal("75.00"))
        self.assertEqual(Decimal(s["net_payable"]), Decimal("425.00"))

    # 15. Co-licensor split integration
    def test_co_licensor_split_integration(self):
        views = [
            {
                "view_id": "VW-1",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "IN",
                "_title_id": "TTL-01",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            }
        ]
        _, settlements = self.service.settle_month(
            month="2026-07",
            run_ts="2026-08-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-POOLAD"],
            persist_db=False,
        )
        s_lead = next(s for s in settlements if s["licensor_id"] == "LIC-LEAD")
        s_co = next(s for s in settlements if s["licensor_id"] == "LIC-CO")
        total_gross = Decimal(s_lead["gross_share"]) + Decimal(s_co["gross_share"])
        # Pool share = 6000
        self.assertEqual(total_gross, Decimal("6000.00"))
        self.assertEqual(Decimal(s_lead["gross_share"]), Decimal("3600.00"))
        self.assertEqual(Decimal(s_co["gross_share"]), Decimal("2400.00"))

    # 16. POOL_ONLY licence
    def test_pool_only_licence(self):
        views = [
            {
                "view_id": "VW-PREM",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "IN",
                "_title_id": "TTL-02",
                "_watch_seconds": 180,
                "_ad_impressions": 0,
            },
            {
                "view_id": "VW-FREE",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "FREE",
                "_territory_id": "IN",
                "_title_id": "TTL-02",
                "_watch_seconds": 180,
                "_ad_impressions": 50,
            },
        ]
        _, settlements = self.service.settle_month(
            month="2026-07",
            run_ts="2026-08-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-POOLONLY"],
            persist_db=False,
        )
        s = next(row for row in settlements if row["licence_id"] == "LCN-POOLONLY")
        # Gross share must only equal pool share, completely omitting ad share
        self.assertEqual(Decimal(s["gross_share"]), Decimal("6000.00"))

    # 17. POOL_AND_AD licence
    def test_pool_and_ad_licence(self):
        views = [
            {
                "view_id": "VW-PREM",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "IN",
                "_title_id": "TTL-01",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            },
            {
                "view_id": "VW-FREE",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "FREE",
                "_territory_id": "IN",
                "_title_id": "TTL-01",
                "_watch_seconds": 3600,
                "_ad_impressions": 100,
            },
        ]
        _, settlements = self.service.settle_month(
            month="2026-07",
            run_ts="2026-08-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-POOLAD"],
            persist_db=False,
        )
        # Total gross share across licensors = pool share (6000) + ad share (1100) = 7100
        tot_gross = sum(Decimal(s["gross_share"]) for s in settlements if s["licence_id"] == "LCN-POOLAD")
        self.assertEqual(tot_gross, Decimal("7100.00"))

    # 18. Duplicate settlement prevention
    def test_duplicate_settlement_prevention(self):
        views = [
            {
                "view_id": "VW-1",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "IN",
                "_title_id": "TTL-01",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            }
        ]
        # First settlement run
        self.service.settle_month(
            month="2026-07",
            run_ts="2026-08-10 00:00:00",
            view_decisions=views,
            accepted_licences=["LCN-POOLAD"],
            persist_db=False,
        )
        # Second identical run must raise DuplicateSettlementError
        with self.assertRaises(DuplicateSettlementError) as ctx:
            self.service.settle_month(
                month="2026-07",
                run_ts="2026-08-10 00:00:00",
                view_decisions=views,
                accepted_licences=["LCN-POOLAD"],
                allow_rerun=False,
                persist_db=False,
            )
        self.assertEqual(ctx.exception.month, "2026-07")

    # 19. Failed settlement rollback
    def test_failed_settlement_rollback(self):
        mock_session = MagicMock()
        mock_session.merge.side_effect = RuntimeError("Simulated Database I/O Failure")
        service = SettlementService(settlement_engine=self.engine, session=mock_session)

        views = [
            {
                "view_id": "VW-1",
                "settlement_month": "2026-07",
                "counted": "true",
                "_tier": "PREMIUM",
                "_territory_id": "IN",
                "_title_id": "TTL-01",
                "_watch_seconds": 3600,
                "_ad_impressions": 0,
            }
        ]
        with self.assertRaises(RuntimeError):
            service.settle_month(
                month="2026-07",
                run_ts="2026-08-10 00:00:00",
                view_decisions=views,
                accepted_licences=["LCN-POOLAD"],
                persist_db=True,
            )
        # Ensure state was not recorded as finalized
        self.assertNotIn("2026-07", service.executed_settlement_months)

    # 20. Exact CSV column formatting and ordering
    def test_exact_csv_column_formatting_and_ordering(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)

            lic_vals = [{"licence_id": "LCN-01", "result": "ACCEPTED", "reason": "", "conflicting_licence_id": ""}]
            view_decs = [{
                "view_id": "VW-01", "decision": "ALLOWED", "reason": "", "licence_id": "LCN-01",
                "local_start": "2026-07-01 10:00:00", "settlement_month": "2026-07", "qualifying": "true",
                "counted": "true", "view_hours": "1.0000", "tag": ""
            }]
            t_shares = [{
                "month": "2026-07", "territory_id": "IN", "title_id": "TTL-01",
                "premium_view_hours": "1.0000", "pool_ratio": "1.0000", "pool_share": "6000.00",
                "ad_impressions": "0", "ad_ratio": "0.0000", "ad_share": "0.00", "title_share": "6000.00"
            }]
            settlements = [{
                "month": "2026-07", "licence_id": "LCN-01", "licensor_id": "LIC-IND",
                "split_pct": "100.00", "gross_share": "6000.00", "mg_paid": "0.00",
                "recouped": "0.00", "mg_balance": "0.00", "cap_retained": "0.00",
                "payable_before_tds": "6000.00", "tds_pct": "10.00", "tds": "600.00",
                "net_payable": "5400.00", "status": "SETTLED"
            }]

            SettlementService.export_evaluation_outputs(
                output_dir=out_path,
                licence_validations=lic_vals,
                view_decisions=view_decs,
                title_shares=t_shares,
                settlements=settlements,
            )

            # Check 1: licence_validation.csv
            with open(out_path / "licence_validation.csv", "r", encoding="utf-8") as f:
                r = csv.reader(f)
                header = next(r)
                self.assertEqual(header, ["licence_id", "result", "reason", "conflicting_licence_id"])

            # Check 2: view_decisions.csv
            with open(out_path / "view_decisions.csv", "r", encoding="utf-8") as f:
                r = csv.reader(f)
                header = next(r)
                self.assertEqual(header, [
                    "view_id", "decision", "reason", "licence_id", "local_start",
                    "settlement_month", "qualifying", "counted", "view_hours", "tag"
                ])

            # Check 3: title_shares.csv
            with open(out_path / "title_shares.csv", "r", encoding="utf-8") as f:
                r = csv.reader(f)
                header = next(r)
                self.assertEqual(header, [
                    "month", "territory_id", "title_id", "premium_view_hours", "pool_ratio",
                    "pool_share", "ad_impressions", "ad_ratio", "ad_share", "title_share"
                ])

            # Check 4: settlements.csv
            with open(out_path / "settlements.csv", "r", encoding="utf-8") as f:
                r = csv.reader(f)
                header = next(r)
                self.assertEqual(header, [
                    "month", "licence_id", "licensor_id", "split_pct", "gross_share", "mg_paid",
                    "recouped", "mg_balance", "cap_retained", "payable_before_tds", "tds_pct",
                    "tds", "net_payable", "status"
                ])


if __name__ == "__main__":
    unittest.main()
