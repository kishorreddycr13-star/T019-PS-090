"""
Windowing Service Module.
Implements BR-01, BR-03, and BR-11 (Territory timezone conversion, window evaluation, and rights calendar).
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any


class WindowingService:
    """Evaluates territory availability windows, local timezone offsets, and rights calendars."""

    def __init__(
        self,
        territories: Dict[str, Dict[str, Any]],
        licences: Dict[str, Dict[str, Any]],
        windows: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        self.territories = territories
        self.licences = licences
        self.windows = windows

    def to_local_time(self, start_utc: str | datetime, territory_id: str) -> datetime:
        """Converts UTC timestamp string or datetime to territory local time."""
        if isinstance(start_utc, str):
            utc_dt = datetime.strptime(start_utc, "%Y-%m-%d %H:%M:%S")
        else:
            utc_dt = start_utc
        offset_minutes = int(self.territories[territory_id]["utc_offset_minutes"])
        return utc_dt + timedelta(minutes=offset_minutes)

    def find_active_licence(
        self,
        title_id: str,
        territory_id: str,
        local_dt: datetime,
        accepted_licences: List[str],
    ) -> Optional[str]:
        """
        Finds the first-created accepted licence whose window is active at local_dt.
        Local time is playable from 00:00:00 on window_start to 23:59:59 on window_end (EC-01).
        """
        local_date = local_dt.date()

        for licence_id in accepted_licences:
            lic = self.licences[licence_id]
            if lic["title_id"] == title_id and lic["territory_id"] == territory_id:
                # Check each window of this licence
                for w in self.windows.get(licence_id, []):
                    w_start = date.fromisoformat(w["window_start"])
                    w_end = date.fromisoformat(w["window_end"])
                    if w_start <= local_date <= w_end:
                        return licence_id
        return None

    def get_rights_calendar_rows(
        self, title_id: str, accepted_licences: List[str]
    ) -> List[Dict[str, Any]]:
        """Returns ordered active rights windows for PRINT_RIGHTS_CALENDAR command."""
        rows = []
        for licence_id in accepted_licences:
            lic = self.licences[licence_id]
            if lic["title_id"] == title_id:
                for w in self.windows.get(licence_id, []):
                    rows.append({
                        "territory_id": lic["territory_id"],
                        "licence_id": licence_id,
                        "window_no": int(w["window_no"]),
                        "window_start": w["window_start"],
                        "window_end": w["window_end"],
                        "exclusivity": lic["exclusivity"],
                    })
        # Sort by territory_id, licence_id, window_no
        rows.sort(key=lambda r: (r["territory_id"], r["licence_id"], r["window_no"]))
        return rows
