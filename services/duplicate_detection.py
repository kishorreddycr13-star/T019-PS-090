"""
Duplicate Detection Service Module.
Implements BR-08 (24-Hour Duplicate View Prevention).

Business Rules:
- The same subscriber watching the same title within 24 hours counts only once.
- Maintain the first qualifying and counted view.
- A view counts if ALLOWED, qualifying, and no counted view of the same subscriber
  and title started less than 24 h earlier (delta_seconds >= 86400).
- Handled per (subscriber_id, title_id) partition.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, Union

TWENTY_FOUR_HOURS_SECONDS: int = 86400


@dataclass(frozen=True)
class DuplicateCheckResult:
    """Encapsulates the de-duplication check result for a playback event."""
    is_duplicate: bool
    subscriber_id: str
    title_id: str
    current_start_utc: datetime
    previous_counted_utc: Optional[datetime]
    delta_seconds: Optional[float]
    message: str

    def to_dict(self) -> dict:
        return {
            "is_duplicate": self.is_duplicate,
            "subscriber_id": self.subscriber_id,
            "title_id": self.title_id,
            "current_start_utc": self.current_start_utc.isoformat(),
            "previous_counted_utc": self.previous_counted_utc.isoformat() if self.previous_counted_utc else None,
            "delta_seconds": self.delta_seconds,
            "message": self.message,
        }


class DuplicateDetector:
    """
    Maintains session-level or cross-batch 24-hour viewership de-duplication state.
    """

    def __init__(self) -> None:
        # Map: (subscriber_id, title_id) -> last counted view start timestamp (UTC)
        self._last_counted_time: Dict[Tuple[str, str], datetime] = {}

    def _normalize_timestamp(self, ts: Union[datetime, str]) -> datetime:
        """Ensures naive UTC datetime for comparison."""
        if isinstance(ts, str):
            clean_ts = ts.strip().replace("T", " ")
            if len(clean_ts) == 19:
                return datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
            return datetime.fromisoformat(clean_ts)
        if isinstance(ts, datetime):
            if ts.tzinfo is not None:
                return ts.astimezone(timezone.utc).replace(tzinfo=None)
            return ts
        raise ValueError(f"Invalid timestamp value: {ts}")

    def is_duplicate(
        self,
        subscriber_id: str,
        title_id: str,
        start_utc: Union[datetime, str],
    ) -> DuplicateCheckResult:
        """
        Checks whether the playback start time falls within 24 hours (< 86,400s)
        of the last counted view of the same title by the same subscriber.
        """
        curr_dt = self._normalize_timestamp(start_utc)
        sub_key = (subscriber_id.strip(), title_id.strip())

        if sub_key not in self._last_counted_time:
            return DuplicateCheckResult(
                is_duplicate=False,
                subscriber_id=sub_key[0],
                title_id=sub_key[1],
                current_start_utc=curr_dt,
                previous_counted_utc=None,
                delta_seconds=None,
                message="First view of this title by subscriber; not a duplicate.",
            )

        prev_dt = self._last_counted_time[sub_key]
        delta_secs = (curr_dt - prev_dt).total_seconds()

        # BR-08: Duplicate if time elapsed is strictly less than 24 hours (86,400s)
        if delta_secs < TWENTY_FOUR_HOURS_SECONDS:
            hours = delta_secs / 3600.0
            return DuplicateCheckResult(
                is_duplicate=True,
                subscriber_id=sub_key[0],
                title_id=sub_key[1],
                current_start_utc=curr_dt,
                previous_counted_utc=prev_dt,
                delta_seconds=delta_secs,
                message=f"Duplicate view: started {delta_secs:.1f}s ({hours:.2f}h) after previous counted view (< 24h).",
            )

        return DuplicateCheckResult(
            is_duplicate=False,
            subscriber_id=sub_key[0],
            title_id=sub_key[1],
            current_start_utc=curr_dt,
            previous_counted_utc=prev_dt,
            delta_seconds=delta_secs,
            message=f"Elapsed time {delta_secs:.1f}s is >= 24h boundary; eligible to count as a new window.",
        )

    def record_counted_view(
        self,
        subscriber_id: str,
        title_id: str,
        start_utc: Union[datetime, str],
    ) -> None:
        """
        Records the timestamp of an ALLOWED, qualifying, non-duplicate view as the
        new benchmark for future 24h checks for this subscriber and title.
        """
        curr_dt = self._normalize_timestamp(start_utc)
        sub_key = (subscriber_id.strip(), title_id.strip())
        self._last_counted_time[sub_key] = curr_dt

    def get_last_counted_time(
        self, subscriber_id: str, title_id: str
    ) -> Optional[datetime]:
        """Returns the recorded UTC timestamp for a subscriber-title pair, if any."""
        return self._last_counted_time.get((subscriber_id.strip(), title_id.strip()))

    def reset(self) -> None:
        """Clears all tracking history."""
        self._last_counted_time.clear()

    @property
    def total_tracked_pairs(self) -> int:
        return len(self._last_counted_time)
