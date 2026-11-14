"""
Metering Service Module.
Orchestrates Playback Eligibility (BR-04, BR-05, BR-06), Qualification (BR-07),
Duplicate Detection (BR-08), Subscriber Tier Metering (BR-09), and Aggregations (BR-10).
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from engine.playback_eligibility_engine import (
    PlaybackEligibilityEngine,
    PlaybackRequest,
    PlaybackDecision,
    DEFAULT_TERRITORY_OFFSETS,
)
from services.qualification_service import (
    QualificationService,
    QualificationResult,
    TierContribution,
)
from services.duplicate_detection import (
    DuplicateDetector,
    DuplicateCheckResult,
)
from repositories.view_repository import ViewRepository
from repositories.metering_repository import MeteringRepository


class MeteringService:
    """
    Central orchestration service for viewership tracking, stream qualification,
    24h de-duplication, tier categorization, and monthly consumption metering.
    """

    def __init__(
        self,
        playback_engine: Optional[PlaybackEligibilityEngine] = None,
        titles: Optional[Dict[str, Dict[str, Any]]] = None,
        territories: Optional[Dict[str, Dict[str, Any]]] = None,
        view_repository: Optional[ViewRepository] = None,
        metering_repository: Optional[MeteringRepository] = None,
        data_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self.playback_engine = playback_engine or self._init_playback_engine(data_dir)
        self.titles: Dict[str, Dict[str, Any]] = titles or self.playback_engine.titles
        self.territories: Dict[str, Dict[str, Any]] = territories or self.playback_engine.territories

        self.qualification_service = QualificationService()
        self.duplicate_detector = DuplicateDetector()
        self.view_repo = view_repository or ViewRepository()
        self.metering_repo = metering_repository or MeteringRepository()

        # Late-view ingestion tracking
        self.settled_months: Set[str] = set()
        self.active_settlement_month: str = "2026-07"

        # In-memory evaluation cache
        self.processed_records: List[Dict[str, Any]] = []

    def _init_playback_engine(self, data_dir: Optional[Union[str, Path]]) -> PlaybackEligibilityEngine:
        """Initializes PlaybackEligibilityEngine from sample data files if available."""
        target_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "sample_data"
        territories = {}
        licences = {}
        windows = {}
        titles = {}

        if target_dir.exists() and (target_dir / "titles.csv").exists():
            with open(target_dir / "territories.csv", "r", encoding="utf-8") as f:
                territories = {r["territory_id"]: r for r in csv.DictReader(f)}
            with open(target_dir / "licences.csv", "r", encoding="utf-8") as f:
                licences = {r["licence_id"]: r for r in csv.DictReader(f)}
            with open(target_dir / "licence_windows.csv", "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    windows.setdefault(r["licence_id"], []).append(r)
            with open(target_dir / "titles.csv", "r", encoding="utf-8") as f:
                titles = {r["title_id"]: r for r in csv.DictReader(f)}

        return PlaybackEligibilityEngine(
            territories=territories,
            licences=licences,
            windows=windows,
            titles=titles,
        )

    def mark_month_settled(self, settled_month: str, next_active_month: str) -> None:
        """Locks a settlement month so subsequent views arriving late are tagged LATE_VIEW."""
        self.settled_months.add(settled_month)
        self.active_settlement_month = next_active_month

    def reset_state(self) -> None:
        """Resets deduplication history, processed cache, and settled months."""
        self.duplicate_detector.reset()
        self.processed_records.clear()
        self.settled_months.clear()
        self.active_settlement_month = "2026-07"

    def process_view_event(
        self,
        event_dict: Dict[str, Any],
        accepted_licences: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """
        Processes a single playback event through:
        1. Playback entitlement check (BR-04, BR-05, BR-06).
        2. Local time and local month determination.
        3. Late event tagging (Trap 3 / VW-001661).
        4. Qualification threshold evaluation (BR-07).
        5. 24-hour duplicate view prevention (BR-08).
        6. Subscriber tier classification (BR-09).
        7. View-hour conversion (BR-10).
        """
        view_id = event_dict.get("view_id") or event_dict.get("event_id") or ""
        subscriber_id = event_dict.get("subscriber_id") or event_dict.get("user_id") or ""
        tier = (event_dict.get("tier") or event_dict.get("tier_id") or "PREMIUM").strip().upper()
        territory_id = event_dict.get("territory_id") or event_dict.get("territory_code") or ""
        title_id = event_dict.get("title_id") or ""
        start_utc_raw = event_dict.get("start_utc") or event_dict.get("playback_start_utc") or ""
        watch_seconds = int(event_dict.get("watch_seconds") or event_dict.get("raw_watch_seconds") or 0)
        ad_impressions = int(event_dict.get("ad_impressions") or 0)

        # 1. Evaluate Playback Eligibility
        pb_req = PlaybackRequest(
            view_id=view_id,
            subscriber_id=subscriber_id,
            tier=tier,
            territory_id=territory_id,
            title_id=title_id,
            playback_timestamp_utc=start_utc_raw,
            watch_seconds=watch_seconds,
            ad_impressions=ad_impressions,
            ingested_utc=event_dict.get("ingested_utc"),
        )
        pb_decision = self.playback_engine.evaluate_playback(pb_req, accepted_licences=accepted_licences)

        # 2. Local Time and Month Assignment
        local_dt = pb_decision.local_start_time
        local_start_str = pb_decision.local_start_str
        local_month = local_dt.strftime("%Y-%m")

        # 3. Late Event Handling
        tag = ""
        settlement_month = local_month
        if local_month in self.settled_months:
            tag = "LATE_VIEW"
            settlement_month = self.active_settlement_month

        # 4. BR-07: Qualification Threshold Evaluation
        runtime_seconds = int(self.titles.get(title_id, {}).get("runtime_seconds", 7200))
        qual_res = self.qualification_service.evaluate_qualification(
            watch_seconds=watch_seconds,
            runtime_seconds=runtime_seconds,
        )
        is_qualifying = qual_res.is_qualifying

        # 5. BR-08 & BR-09: Duplicate Prevention and Tier Classification
        is_counted = False
        view_hours = Decimal("0.0000")
        effective_ad_impressions = 0

        # Only ALLOWED and qualifying views are eligible to be counted
        if pb_decision.is_allowed and is_qualifying:
            dup_res = self.duplicate_detector.is_duplicate(
                subscriber_id=subscriber_id,
                title_id=title_id,
                start_utc=pb_decision.playback_start_utc,
            )

            if not dup_res.is_duplicate:
                is_counted = True
                self.duplicate_detector.record_counted_view(
                    subscriber_id=subscriber_id,
                    title_id=title_id,
                    start_utc=pb_decision.playback_start_utc,
                )

                # Classify by tier
                tier_contrib = self.qualification_service.classify_tier_contribution(
                    tier=tier,
                    watch_seconds=watch_seconds,
                    ad_impressions=ad_impressions,
                    is_qualifying=True,
                    is_counted=True,
                )
                view_hours = tier_contrib.view_hours
                effective_ad_impressions = tier_contrib.ad_impressions

        # Formulate exact decision record
        record = {
            "view_id": view_id,
            "decision": pb_decision.decision,
            "reason": pb_decision.reason,
            "licence_id": pb_decision.licence_id,
            "local_start": local_start_str,
            "settlement_month": settlement_month,
            "qualifying": "true" if is_qualifying else "false",
            "counted": "true" if is_counted else "false",
            "view_hours": f"{view_hours:.4f}",
            "tag": tag,
            # Metadata preserved for downstream aggregations & database persistence
            "_tier": tier,
            "_territory_id": territory_id,
            "_title_id": title_id,
            "_subscriber_id": subscriber_id,
            "_watch_seconds": watch_seconds,
            "_runtime_seconds": runtime_seconds,
            "_threshold_seconds": qual_res.threshold_seconds,
            "_ad_impressions": effective_ad_impressions,
            "_raw_ad_impressions": ad_impressions,
            "_start_utc": pb_decision.playback_start_utc,
            "_local_dt": local_dt,
            "_ingested_utc": event_dict.get("ingested_utc"),
        }

        self.processed_records.append(record)
        return record

    def process_views_batch(
        self,
        view_events: List[Dict[str, Any]],
        cutoff_utc: Optional[str] = None,
        accepted_licences: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Batch processes a list of view events up to cutoff_utc.
        """
        cutoff_dt = (
            datetime.strptime(cutoff_utc, "%Y-%m-%d %H:%M:%S")
            if cutoff_utc
            else None
        )
        batch_results = []

        for v in view_events:
            if cutoff_dt and v.get("ingested_utc"):
                ing_dt = datetime.strptime(v["ingested_utc"], "%Y-%m-%d %H:%M:%S")
                if ing_dt >= cutoff_dt:
                    continue

            res = self.process_view_event(v, accepted_licences=accepted_licences)
            batch_results.append(res)

        return batch_results

    def get_metering_aggregations(
        self,
        month: Optional[str] = None,
        territory_id: Optional[str] = None,
        title_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Calculates monthly and territory-wise aggregations from processed in-memory records.
        """
        return self.metering_repo.aggregate_metrics_from_records(
            self.processed_records,
            month=month,
            territory_id=territory_id,
            title_id=title_id,
        )

    def export_view_decisions_csv(self, output_path: Union[str, Path]) -> None:
        """
        Exports the official view_decisions.csv file in the required evaluation format.
        Columns: view_id,decision,reason,licence_id,local_start,settlement_month,qualifying,counted,view_hours,tag
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "view_id",
            "decision",
            "reason",
            "licence_id",
            "local_start",
            "settlement_month",
            "qualifying",
            "counted",
            "view_hours",
            "tag",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in self.processed_records:
                row = {fn: r.get(fn, "") for fn in fieldnames}
                writer.writerow(row)
