"""
Playback Eligibility Engine Module.
Implements BR-04 (Window Eligibility), BR-05 (Exclusivity & Territory Rights),
and BR-06 (Catalogue Removal & 4-Hour In-Progress Stream Completion Rule).

Provides:
- Precise UTC to territory-local time conversions.
- Playback window boundaries [00:00:00 to 23:59:59 local].
- Window gap denial and rejected licence enforcement.
- Multiple NON_EXCLUSIVE licences arbitration (first created wins).
- Catalogue removal at window expiry with 4-hour completion allowance for active streams.
- Deterministic decision IDs and decision history tracking.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

DEFAULT_TERRITORY_OFFSETS: Dict[str, int] = {
    "IN": 330,   # Asia/Kolkata (UTC+05:30)
    "AE": 240,   # Asia/Dubai (UTC+04:00)
    "SG": 480,   # Asia/Singapore (UTC+08:00)
    "US": -240,  # America/New_York (EDT UTC-04:00)
    "GB": 0,     # Europe/London (UTC+00:00)
    "DE": 120,   # Europe/Berlin (CEST UTC+02:00)
    "JP": 540,   # Asia/Tokyo (JST UTC+09:00)
}

MAX_IN_PROGRESS_STREAM_SECONDS: int = 14400  # 4 hours


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class PlaybackRequest:
    """Represents an incoming client playback heartbeat or playback start request."""
    title_id: str
    subscriber_id: str
    tier: str
    territory_id: str
    playback_timestamp_utc: Union[datetime, str]
    watch_seconds: int = 0
    view_id: Optional[str] = None
    ad_impressions: int = 0
    ingested_utc: Optional[Union[datetime, str]] = None
    device_category: str = "SMART_TV"
    ip_address: Optional[str] = None
    is_vpn_detected: bool = False

    def get_parsed_timestamp(self) -> datetime:
        """Returns standard naive datetime in UTC."""
        ts = self.playback_timestamp_utc
        if isinstance(ts, str):
            clean_ts = ts.strip().replace("T", " ")
            if len(clean_ts) == 19:
                return datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
            return datetime.fromisoformat(clean_ts)
        if isinstance(ts, datetime):
            if ts.tzinfo is not None:
                return ts.astimezone(timezone.utc).replace(tzinfo=None)
            return ts
        raise ValueError(f"Invalid timestamp: {ts}")


@dataclass
class PlaybackDecision:
    """Encapsulates the entitlement decision for a playback request."""
    decision_id: str
    view_id: str
    title_id: str
    licence_id: str
    subscriber_id: str
    tier: str
    territory_id: str
    playback_start_utc: datetime
    local_start_time: datetime
    local_start_str: str
    decision: str  # "ALLOWED" or "DENIED"
    reason: str  # "" if ALLOWED, else "OUTSIDE_WINDOW", "WINDOW_GAP", "REJECTED_LICENCE", etc.
    watch_seconds: int
    effective_watch_seconds: int
    stream_completed_within_4h: bool = True
    exceeded_4h_limit: bool = False
    message: str = ""
    timestamp_evaluated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_allowed(self) -> bool:
        return self.decision == "ALLOWED"

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary representation of the playback decision."""
        return {
            "decision_id": self.decision_id,
            "view_id": self.view_id,
            "title_id": self.title_id,
            "licence_id": self.licence_id,
            "subscriber_id": self.subscriber_id,
            "tier": self.tier,
            "territory_id": self.territory_id,
            "playback_start_utc": self.playback_start_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "local_start": self.local_start_str,
            "decision": self.decision,
            "reason": self.reason,
            "watch_seconds": self.watch_seconds,
            "effective_watch_seconds": self.effective_watch_seconds,
            "stream_completed_within_4h": self.stream_completed_within_4h,
            "exceeded_4h_limit": self.exceeded_4h_limit,
            "message": self.message,
        }

    def to_view_decision_row(
        self,
        settlement_month: str,
        qualifying: bool,
        counted: bool,
        view_hours: Decimal,
        tag: str = "",
    ) -> Dict[str, str]:
        """Converts to exact official evaluation schema for view_decisions.csv."""
        return {
            "view_id": self.view_id,
            "decision": self.decision,
            "reason": self.reason,
            "licence_id": self.licence_id,
            "local_start": self.local_start_str,
            "settlement_month": settlement_month,
            "qualifying": "true" if qualifying else "false",
            "counted": "true" if counted else "false",
            "view_hours": f"{view_hours:.4f}",
            "tag": tag,
        }


# ---------------------------------------------------------------------------
# Playback Eligibility Engine
# ---------------------------------------------------------------------------

class PlaybackEligibilityEngine:
    """
    Core engine enforcing playback entitlements, territory timezone conversions,
    licence availability, catalogue removal, and in-progress stream completion rules.
    """

    def __init__(
        self,
        territories: Optional[Dict[str, Dict[str, Any]]] = None,
        licences: Optional[Dict[str, Dict[str, Any]]] = None,
        windows: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        titles: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self.territories = territories or {}
        self.licences = licences or {}
        self.windows = windows or {}
        self.titles = titles or {}

        # Historical decisions ledger
        self.decision_history: List[PlaybackDecision] = []

    # -----------------------------------------------------------------------
    # BR-04: Territory Timezone Conversion
    # -----------------------------------------------------------------------
    def to_local_time(
        self, utc_dt: datetime, territory_id: str
    ) -> datetime:
        """
        Converts UTC timestamp to territory-local time using dataset offsets.
        Supports fixed territory offset minutes and defaults.
        """
        tid = territory_id.strip().upper()
        if tid in self.territories and "utc_offset_minutes" in self.territories[tid]:
            offset_minutes = int(self.territories[tid]["utc_offset_minutes"])
        elif tid in DEFAULT_TERRITORY_OFFSETS:
            offset_minutes = DEFAULT_TERRITORY_OFFSETS[tid]
        else:
            offset_minutes = 0

        return utc_dt + timedelta(minutes=offset_minutes)

    # -----------------------------------------------------------------------
    # BR-05: Licence Finding & Exclusivity Arbitration
    # -----------------------------------------------------------------------
    def find_eligible_licence(
        self,
        title_id: str,
        territory_id: str,
        local_dt: datetime,
        accepted_licences: Optional[Sequence[str]] = None,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], str]:
        """
        Finds the active accepted licence authorizing playback at local_dt.
        
        Rules:
        - Only ACCEPTED and ACTIVE licences can authorize playback (BR-05).
        - Must match both title_id and territory_id.
        - Playback local date must fall within a licence window [window_start, window_end].
        - If multiple NON_EXCLUSIVE licences match, select the first created in accepted_licences order.
        
        Returns:
            (assigned_licence_id, matched_window_dict, rejection_reason)
        """
        tid = title_id.strip()
        ter = territory_id.strip().upper()
        local_date = local_dt.date()

        candidate_licence_ids = (
            list(accepted_licences) if accepted_licences is not None else list(self.licences.keys())
        )

        matching_licences: List[Tuple[str, Dict[str, Any]]] = []
        has_licence_for_title_territory = False
        saw_window_in_past = False
        saw_window_in_future = False

        for lic_id in candidate_licence_ids:
            lic = self.licences.get(lic_id)
            if not lic:
                continue

            # Must match title and territory
            if lic.get("title_id") != tid or lic.get("territory_id") != ter:
                continue

            has_licence_for_title_territory = True
            lic_windows = self.windows.get(lic_id, [])

            for w in lic_windows:
                w_start_str = str(w.get("window_start", "")).strip()
                w_end_str = str(w.get("window_end", "")).strip()
                if not w_start_str or not w_end_str:
                    continue

                w_start = date.fromisoformat(w_start_str)
                w_end = date.fromisoformat(w_end_str)

                # Check if local_date is inside this window
                if w_start <= local_date <= w_end:
                    matching_licences.append((lic_id, w))
                elif local_date < w_start:
                    saw_window_in_future = True
                elif local_date > w_end:
                    saw_window_in_past = True

        if matching_licences:
            # Overlapping NON_EXCLUSIVE licences of different licensors: views go to the licence created first
            selected_lic_id, selected_window = matching_licences[0]
            return selected_lic_id, selected_window, ""

        # Determine precise reason for rejection
        if not has_licence_for_title_territory:
            return None, None, "OUTSIDE_WINDOW"

        if saw_window_in_past and saw_window_in_future:
            # Between two windows: window gap
            return None, None, "OUTSIDE_WINDOW"
        elif saw_window_in_future:
            return None, None, "OUTSIDE_WINDOW"
        elif saw_window_in_past:
            return None, None, "OUTSIDE_WINDOW"

        return None, None, "OUTSIDE_WINDOW"

    # -----------------------------------------------------------------------
    # BR-04, BR-05, BR-06: Master Playback Evaluation
    # -----------------------------------------------------------------------
    def evaluate_playback(
        self,
        request: PlaybackRequest,
        accepted_licences: Optional[Sequence[str]] = None,
    ) -> PlaybackDecision:
        """
        Evaluates a playback request against BR-04, BR-05, and BR-06.
        Returns PlaybackDecision with deterministic ID and watch time calculation.
        """
        # Validate request payload
        if not request.title_id or not request.territory_id or not request.subscriber_id:
            return self._create_decision(
                request=request,
                decision_str="DENIED",
                reason="INVALID_PLAYBACK_DATA",
                licence_id="",
                local_dt=datetime.now(),
                effective_secs=0,
                message="Missing mandatory playback parameters.",
            )

        if request.watch_seconds < 0:
            return self._create_decision(
                request=request,
                decision_str="DENIED",
                reason="INVALID_PLAYBACK_DATA",
                licence_id="",
                local_dt=datetime.now(),
                effective_secs=0,
                message="Watch duration cannot be negative.",
            )

        # 1. Parse UTC start time and convert to territory-local time
        utc_dt = request.get_parsed_timestamp()
        local_dt = self.to_local_time(utc_dt, request.territory_id)

        # 2. Find eligible accepted licence for this title and territory
        matched_lic_id, matched_window, reason = self.find_eligible_licence(
            title_id=request.title_id,
            territory_id=request.territory_id,
            local_dt=local_dt,
            accepted_licences=accepted_licences,
        )

        if not matched_lic_id or not matched_window:
            return self._create_decision(
                request=request,
                decision_str="DENIED",
                reason=reason or "OUTSIDE_WINDOW",
                licence_id="",
                local_dt=local_dt,
                effective_secs=0,
                message=(
                    f"Playback on {local_dt} is outside active licence windows for title "
                    f"'{request.title_id}' in territory '{request.territory_id}'."
                ),
            )

        # 3. Apply BR-06: Catalogue removal and 4-Hour in-progress stream completion rule
        w_end_date = date.fromisoformat(str(matched_window["window_end"]).strip())
        local_date = local_dt.date()
        raw_watch = request.watch_seconds

        # A stream starting on or before 23:59:59 on window_end is ALLOWED
        # If it runs past window_end, it is allowed to complete for up to 4 hours (14,400s)
        effective_secs = raw_watch
        stream_completed_within_4h = True
        exceeded_4h_limit = False

        if local_date == w_end_date:
            # End of window day: check duration past window boundary (23:59:59)
            seconds_until_midnight = (
                datetime(local_date.year, local_date.month, local_date.day, 23, 59, 59) - local_dt
            ).total_seconds() + 1

            if raw_watch > seconds_until_midnight:
                # Stream runs past window expiration
                seconds_past_window = raw_watch - seconds_until_midnight
                if seconds_past_window > MAX_IN_PROGRESS_STREAM_SECONDS:
                    # Exceeds 4-hour post-window allowance: capped at 4 hours past window
                    effective_secs = int(seconds_until_midnight + MAX_IN_PROGRESS_STREAM_SECONDS)
                    stream_completed_within_4h = False
                    exceeded_4h_limit = True

        decision = self._create_decision(
            request=request,
            decision_str="ALLOWED",
            reason="",
            licence_id=matched_lic_id,
            local_dt=local_dt,
            effective_secs=effective_secs,
            stream_completed_within_4h=stream_completed_within_4h,
            exceeded_4h_limit=exceeded_4h_limit,
            message=f"Playback authorized under licence '{matched_lic_id}'.",
        )
        return decision

    # -----------------------------------------------------------------------
    # Decision Construction & Deterministic ID Generation
    # -----------------------------------------------------------------------
    def _create_decision(
        self,
        request: PlaybackRequest,
        decision_str: str,
        reason: str,
        licence_id: str,
        local_dt: datetime,
        effective_secs: int,
        message: str = "",
        stream_completed_within_4h: bool = True,
        exceeded_4h_limit: bool = False,
    ) -> PlaybackDecision:
        v_id = request.view_id or self._generate_deterministic_view_id(request)
        dec_id = f"DEC-{v_id}"

        decision = PlaybackDecision(
            decision_id=dec_id,
            view_id=v_id,
            title_id=request.title_id,
            licence_id=licence_id,
            subscriber_id=request.subscriber_id,
            tier=request.tier,
            territory_id=request.territory_id,
            playback_start_utc=request.get_parsed_timestamp() if isinstance(request.playback_timestamp_utc, (str, datetime)) else datetime.now(timezone.utc),
            local_start_time=local_dt,
            local_start_str=local_dt.strftime("%Y-%m-%d %H:%M:%S"),
            decision=decision_str,
            reason=reason,
            watch_seconds=request.watch_seconds,
            effective_watch_seconds=effective_secs,
            stream_completed_within_4h=stream_completed_within_4h,
            exceeded_4h_limit=exceeded_4h_limit,
            message=message,
        )
        self.decision_history.append(decision)
        return decision

    @staticmethod
    def _generate_deterministic_view_id(request: PlaybackRequest) -> str:
        """Generates a stable, reproducible view identifier from event parameters."""
        raw_key = f"{request.subscriber_id}:{request.title_id}:{request.territory_id}:{request.playback_timestamp_utc}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:10].upper()
        return f"VW-{digest}"

    # -----------------------------------------------------------------------
    # Batch Processing
    # -----------------------------------------------------------------------
    def evaluate_batch(
        self,
        requests: Sequence[PlaybackRequest],
        accepted_licences: Optional[Sequence[str]] = None,
    ) -> List[PlaybackDecision]:
        """Evaluates a batch of playback requests in sequence."""
        return [self.evaluate_playback(req, accepted_licences=accepted_licences) for req in requests]

    def export_decisions_csv(
        self,
        output_file: Union[str, Path],
        decisions: Sequence[PlaybackDecision],
        settlement_month_func: Optional[Any] = None,
    ) -> None:
        """Exports decisions matching view_decisions.csv format."""
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
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
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for d in decisions:
                # Default formatting if no settlement func supplied
                s_month = d.local_start_time.strftime("%Y-%m")
                v_hours = (Decimal(d.effective_watch_seconds) / Decimal(3600)).quantize(Decimal("0.0001"))
                row = d.to_view_decision_row(
                    settlement_month=s_month,
                    qualifying=d.is_allowed and d.effective_watch_seconds >= 30,
                    counted=d.is_allowed,
                    view_hours=v_hours,
                )
                writer.writerow(row)
