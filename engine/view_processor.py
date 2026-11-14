"""
View Processor Module.
Implements BR-07 (Qualifying stream evaluation), BR-08 (24-hr de-duplication),
BR-09 (Subscriber tier classification), and late view tagging.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Set, Tuple, Any

from engine.windowing_service import WindowingService
from services.qualification_service import QualificationService
from services.duplicate_detection import DuplicateDetector


class ViewProcessor:
    """Processes raw playback heartbeats, evaluates entitlement, qualifying rules, and de-duplication."""

    def __init__(
        self,
        titles: Dict[str, Dict[str, Any]],
        view_events: List[Dict[str, Any]],
        windowing_service: WindowingService,
    ) -> None:
        self.titles = titles
        self.view_events = view_events
        self.windowing_service = windowing_service

        # Ingestion state tracking
        self.last_ingested_index: int = 0
        self.settled_months: Set[str] = set()
        self.active_settlement_month: str = "2026-07"

        # Modular qualification & duplicate detection services
        self.qualification_service = QualificationService()
        self.duplicate_detector = DuplicateDetector()

        # Audit records for view_decisions.csv (in original file order)
        self.view_decisions: List[Dict[str, Any]] = []

    @property
    def last_counted_time(self) -> Dict[Tuple[str, str], datetime]:
        """Provides backwards-compatible access to de-duplication state."""
        return self.duplicate_detector._last_counted_time

    def process_views_until(
        self, cutoff_utc: str, accepted_licences: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Decides every view ingested before cutoff_utc that has not yet been processed.
        Maintains global session-level 24h de-duplication and records view decisions.
        """
        cutoff_dt = datetime.strptime(cutoff_utc, "%Y-%m-%d %H:%M:%S")
        newly_processed = []

        while self.last_ingested_index < len(self.view_events):
            v = self.view_events[self.last_ingested_index]
            ing_dt = datetime.strptime(v["ingested_utc"], "%Y-%m-%d %H:%M:%S")

            if ing_dt >= cutoff_dt:
                break  # Views are sorted by ingested_utc

            # Convert start_utc to territory local time
            utc_dt = datetime.strptime(v["start_utc"], "%Y-%m-%d %H:%M:%S")
            local_dt = self.windowing_service.to_local_time(utc_dt, v["territory_id"])
            local_start_str = local_dt.strftime("%Y-%m-%d %H:%M:%S")
            local_month = local_dt.strftime("%Y-%m")

            # Check late view condition (Extra Trap / VW-001661)
            tag = ""
            settlement_month = local_month
            if local_month in self.settled_months:
                tag = "LATE_VIEW"
                settlement_month = self.active_settlement_month

            # Find active licence window (BR-01 / EC-01 / EC-06 / VW-001046)
            matched_licence = self.windowing_service.find_active_licence(
                v["title_id"], v["territory_id"], local_dt, accepted_licences
            )

            if matched_licence:
                decision = "ALLOWED"
                reason = ""
                assigned_licence_id = matched_licence
            else:
                decision = "DENIED"
                reason = "OUTSIDE_WINDOW"
                assigned_licence_id = ""

            # Check qualifying stream definition (BR-07 / EC-02)
            runtime_seconds = int(self.titles[v["title_id"]]["runtime_seconds"])
            watch_seconds = int(v["watch_seconds"])
            qual_result = self.qualification_service.evaluate_qualification(
                watch_seconds=watch_seconds,
                runtime_seconds=runtime_seconds,
            )
            qualifying = qual_result.is_qualifying

            # Check 24h de-duplication (BR-08 / EC-03)
            counted = False
            view_hours = Decimal("0.0000")

            if decision == "ALLOWED" and qualifying:
                dup_check = self.duplicate_detector.is_duplicate(
                    subscriber_id=v["subscriber_id"],
                    title_id=v["title_id"],
                    start_utc=utc_dt,
                )

                if not dup_check.is_duplicate:
                    self.duplicate_detector.record_counted_view(
                        subscriber_id=v["subscriber_id"],
                        title_id=v["title_id"],
                        start_utc=utc_dt,
                    )
                    counted = True
                    view_hours = self.qualification_service.calculate_view_hours(watch_seconds)

            record = {
                "view_id": v["view_id"],
                "decision": decision,
                "reason": reason,
                "licence_id": assigned_licence_id,
                "local_start": local_start_str,
                "settlement_month": settlement_month,
                "qualifying": "true" if qualifying else "false",
                "counted": "true" if counted else "false",
                "view_hours": f"{view_hours:.4f}",
                "tag": tag,
                # Metadata preserved for downstream settlement
                "_tier": v["tier"],
                "_territory_id": v["territory_id"],
                "_title_id": v["title_id"],
                "_ad_impressions": int(v["ad_impressions"]),
                "_watch_seconds": watch_seconds,
            }

            self.view_decisions.append(record)
            newly_processed.append(record)
            self.last_ingested_index += 1

        return newly_processed

    def mark_month_settled(self, month: str, next_month: str) -> None:
        """Locks a settlement month so subsequent views arriving late are tagged LATE_VIEW."""
        self.settled_months.add(month)
        self.active_settlement_month = next_month
