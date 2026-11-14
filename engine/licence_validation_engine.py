"""
Licence Validation Engine Module.
Implements BR-01 (Window Validation), BR-02 (Exclusivity Validation), and BR-03 (Holdback Validation).

Provides:
- Window validity, sequence parsing, internal overlap detection, and adjacent window handling.
- Territorial exclusivity conflict detection with identification of conflicting licence ID.
- Theatrical (45-day) and TV premiere (7-day) holdback boundary validation.
- Territory-local date comparisons and multi-territory independence.
- Full audit logging to the database (AuditLog table) and evaluation record generation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# Database integration
from database.connection import get_db_session
from models.audit import AuditLog
from models.contract import LicenceContract
from models.title import Title
from models.window import LicenceWindow


# ---------------------------------------------------------------------------
# Value Objects and Domain Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WindowRange:
    """Represents a validated playback availability window in territory-local dates."""
    window_no: int
    start_date: date
    end_date: date
    window_type: str = "SVOD"

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError(
                f"Invalid window range: start date ({self.start_date}) cannot be after end date ({self.end_date})."
            )

    @property
    def duration_days(self) -> int:
        """Inclusive count of days in window."""
        return (self.end_date - self.start_date).days + 1

    def overlaps(self, other: WindowRange) -> bool:
        """Returns True if two inclusive calendar date ranges overlap."""
        return max(self.start_date, other.start_date) <= min(self.end_date, other.end_date)

    def is_adjacent_to(self, other: WindowRange) -> bool:
        """
        Returns True if two windows touch contiguously without overlapping
        (e.g., one ends on 2026-07-20 and the next starts on 2026-07-21).
        """
        return (
            self.end_date + timedelta(days=1) == other.start_date
            or other.end_date + timedelta(days=1) == self.start_date
        )


@dataclass
class ValidationDecision:
    """Result of a licence validation check."""
    licence_id: str
    result: str  # "ACCEPTED" or "REJECTED"
    reason: str = ""  # "HOLDBACK", "EXCLUSIVITY", "INVALID_WINDOW_DATES", "OVERLAPPING_INTERNAL_WINDOWS", etc.
    conflicting_licence_id: str = ""
    message: str = ""
    audit_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_accepted(self) -> bool:
        return self.result == "ACCEPTED"

    def to_dict(self) -> Dict[str, str]:
        """Evaluation CSV format compatible dictionary."""
        return {
            "licence_id": self.licence_id,
            "result": self.result,
            "reason": self.reason,
            "conflicting_licence_id": self.conflicting_licence_id,
        }


# ---------------------------------------------------------------------------
# Helper Date Functions
# ---------------------------------------------------------------------------

def parse_date(val: Union[str, date]) -> date:
    """Parses ISO date string or returns existing date object."""
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        return date.fromisoformat(val.strip())
    raise TypeError(f"Expected str or date, got {type(val)}")


# ---------------------------------------------------------------------------
# Licence Validation Engine
# ---------------------------------------------------------------------------

class LicenceValidationEngine:
    """
    Core engine for validating content licence contracts against window,
    territorial exclusivity, and theatrical/TV holdback business rules.
    """

    def __init__(
        self,
        titles: Optional[Dict[str, Dict[str, Any]]] = None,
        licences: Optional[Dict[str, Dict[str, Any]]] = None,
        windows: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        territories: Optional[Dict[str, Dict[str, Any]]] = None,
        enable_db_audit: bool = True,
    ) -> None:
        self.titles = titles or {}
        self.licences = licences or {}
        self.windows = windows or {}
        self.territories = territories or {}
        self.enable_db_audit = enable_db_audit

        # In-memory tracking of accepted licences in sequential stream order
        self.accepted_licences: List[str] = []
        # Full accepted licence cache: licence_id -> dict(licence_info + parsed_windows)
        self.accepted_licence_records: Dict[str, Dict[str, Any]] = {}
        # Validation audit trail for CSV reporting
        self.validation_records: List[Dict[str, str]] = []
        # Detailed decision objects
        self.decisions: List[ValidationDecision] = []

    # -----------------------------------------------------------------------
    # BR-01: Window Validation & Sequence Parsing
    # -----------------------------------------------------------------------
    @staticmethod
    def validate_and_parse_windows(
        raw_windows: Sequence[Dict[str, Any]]
    ) -> Tuple[bool, str, List[WindowRange]]:
        """
        Validates playback window syntax, start/end date logic, and checks
        for invalid internal overlaps within the candidate licence itself.

        Returns:
            (is_valid, error_reason, list_of_WindowRange)
        """
        if not raw_windows:
            return False, "NO_WINDOWS_DEFINED", []

        parsed: List[WindowRange] = []
        for idx, w in enumerate(raw_windows, start=1):
            s_raw = w.get("window_start")
            e_raw = w.get("window_end")
            w_no = int(w.get("window_no", idx))
            w_type = str(w.get("window_type", "SVOD")).strip().upper()

            if not s_raw or not e_raw:
                return False, "INVALID_WINDOW_DATES", []

            try:
                s_dt = parse_date(s_raw)
                e_dt = parse_date(e_raw)
            except Exception:
                return False, "INVALID_WINDOW_DATES", []

            # Check start <= end
            if s_dt > e_dt:
                return False, "INVALID_WINDOW_DATES", []

            parsed.append(WindowRange(window_no=w_no, start_date=s_dt, end_date=e_dt, window_type=w_type))

        # Sort windows by start date
        parsed.sort(key=lambda wr: wr.start_date)

        # Detect internal overlaps between distinct windows of the same contract
        for i in range(len(parsed)):
            for j in range(i + 1, len(parsed)):
                w1, w2 = parsed[i], parsed[j]
                if w1.overlaps(w2):
                    return False, "OVERLAPPING_INTERNAL_WINDOWS", []

        return True, "", parsed

    # -----------------------------------------------------------------------
    # BR-03: Holdback Validation (Theatrical & TV Premiere Rules)
    # -----------------------------------------------------------------------
    @staticmethod
    def validate_holdbacks(
        windows: List[WindowRange],
        theatrical_premiere: Optional[Union[str, date]] = None,
        tv_premiere: Optional[Union[str, date]] = None,
    ) -> Tuple[bool, str, str]:
        """
        Validates holdback constraints:
        - Theatrical holdback: window_start >= theatrical_premiere + 45 days.
          (Day 44 is rejected; exact 45th day is accepted).
        - TV holdback: window_start >= tv_premiere + 7 days.
          (Day 6 is rejected; exact 7th day is accepted).

        Returns:
            (is_valid, reason, explanatory_message)
        """
        if theatrical_premiere:
            th_dt = parse_date(theatrical_premiere)
            min_allowed_theatrical = th_dt + timedelta(days=45)
            for w in windows:
                if w.start_date < min_allowed_theatrical:
                    days_diff = (w.start_date - th_dt).days
                    msg = (
                        f"Window #{w.window_no} starts on {w.start_date} ({days_diff} days after "
                        f"theatrical premiere {th_dt}), which violates the 45-day theatrical "
                        f"holdback (earliest allowed: {min_allowed_theatrical})."
                    )
                    return False, "HOLDBACK", msg

        if tv_premiere:
            tv_dt = parse_date(tv_premiere)
            min_allowed_tv = tv_dt + timedelta(days=7)
            for w in windows:
                if w.start_date < min_allowed_tv:
                    days_diff = (w.start_date - tv_dt).days
                    msg = (
                        f"Window #{w.window_no} starts on {w.start_date} ({days_diff} days after "
                        f"TV premiere {tv_dt}), which violates the 7-day TV "
                        f"holdback (earliest allowed: {min_allowed_tv})."
                    )
                    return False, "HOLDBACK", msg

        return True, "", ""

    # -----------------------------------------------------------------------
    # BR-02: Territorial Exclusivity Collision Validation
    # -----------------------------------------------------------------------
    def validate_exclusivity(
        self,
        candidate_title_id: str,
        candidate_territory_id: str,
        candidate_exclusivity: str,
        candidate_windows: List[WindowRange],
        exclude_licence_id: Optional[str] = None,
    ) -> Tuple[bool, str, str, str]:
        """
        Evaluates territorial exclusivity:
        - Compares candidate licence against already accepted active licences.
        - Only licences with the SAME title_id and SAME territory_id can conflict.
        - Licences for different territories or different titles never conflict.
        - If candidate is EXCLUSIVE or existing licence is EXCLUSIVE:
          Any overlapping window between them is prohibited.
        - Non-overlapping windows (including contiguous adjacent windows) are allowed.
        - Two NON_EXCLUSIVE licences can freely overlap.

        Returns:
            (is_valid, reason, conflicting_licence_id, message)
        """
        cand_excl = candidate_exclusivity.strip().upper()

        for accepted_id in self.accepted_licences:
            if exclude_licence_id and accepted_id == exclude_licence_id:
                continue

            accepted_rec = self.accepted_licence_records.get(accepted_id)
            if not accepted_rec:
                continue

            acc_title = accepted_rec["title_id"]
            acc_territory = accepted_rec["territory_id"]
            acc_excl = accepted_rec["exclusivity"].strip().upper()

            # Rule: Only licences for the SAME title AND SAME territory can conflict
            if acc_title != candidate_title_id or acc_territory != candidate_territory_id:
                continue

            # If either licence is EXCLUSIVE, check for window overlaps
            if cand_excl == "EXCLUSIVE" or acc_excl == "EXCLUSIVE":
                acc_windows: List[WindowRange] = accepted_rec["parsed_windows"]
                for cw in candidate_windows:
                    for aw in acc_windows:
                        if cw.overlaps(aw):
                            msg = (
                                f"Candidate licence window ({cw.start_date} to {cw.end_date}, {cand_excl}) "
                                f"overlaps with existing licence '{accepted_id}' window "
                                f"({aw.start_date} to {aw.end_date}, {acc_excl}) for title '{candidate_title_id}' "
                                f"in territory '{candidate_territory_id}'."
                            )
                            return False, "EXCLUSIVITY", accepted_id, msg

        return True, "", "", ""

    # -----------------------------------------------------------------------
    # Master Licence Validation Entrypoint
    # -----------------------------------------------------------------------
    def validate_licence(
        self,
        licence_id: str,
        title_id: Optional[str] = None,
        territory_id: Optional[str] = None,
        exclusivity: Optional[str] = None,
        windows: Optional[Sequence[Dict[str, Any]]] = None,
        theatrical_premiere: Optional[Union[str, date]] = None,
        tv_premiere: Optional[Union[str, date]] = None,
    ) -> ValidationDecision:
        """
        Validates licence in stream order against BR-01, BR-02, and BR-03.
        Supports both in-memory evaluation and DB-backed operations.
        Logs every decision to DB AuditLog and tracking records.
        """
        lid = licence_id.strip()

        # 1. Resolve licence terms from parameters or in-memory master dictionary
        lic_data = self.licences.get(lid, {})
        tid = (title_id or lic_data.get("title_id", "")).strip()
        ter = (territory_id or lic_data.get("territory_id", "")).strip().upper()
        excl = (exclusivity or lic_data.get("exclusivity", "NON_EXCLUSIVE")).strip().upper()

        if not tid:
            decision = self._record_rejection(lid, "LICENCE_NOT_FOUND", "", f"Licence '{lid}' was not found.")
            return decision

        # 2. Resolve Title metadata
        title_meta = self.titles.get(tid, {})
        th_prem = theatrical_premiere or title_meta.get("theatrical_premiere")
        tv_prem = tv_premiere or title_meta.get("tv_premiere")

        # 3. Resolve Windows
        raw_windows = windows or self.windows.get(lid, [])

        # --- Rule BR-01: Window Validation ---
        w_valid, w_reason, parsed_windows = self.validate_and_parse_windows(raw_windows)
        if not w_valid:
            decision = self._record_rejection(
                lid,
                w_reason,
                "",
                f"Window validation failed for licence '{lid}': {w_reason}",
                title_id=tid,
                territory_id=ter,
            )
            return decision

        # --- Rule BR-03: Holdback Validation ---
        h_valid, h_reason, h_msg = self.validate_holdbacks(
            parsed_windows,
            theatrical_premiere=th_prem,
            tv_premiere=tv_prem,
        )
        if not h_valid:
            decision = self._record_rejection(
                lid,
                h_reason,
                "",
                h_msg,
                title_id=tid,
                territory_id=ter,
            )
            return decision

        # --- Rule BR-02: Exclusivity Validation ---
        e_valid, e_reason, conflict_id, e_msg = self.validate_exclusivity(
            candidate_title_id=tid,
            candidate_territory_id=ter,
            candidate_exclusivity=excl,
            candidate_windows=parsed_windows,
            exclude_licence_id=lid,
        )
        if not e_valid:
            decision = self._record_rejection(
                lid,
                e_reason,
                conflict_id,
                e_msg,
                title_id=tid,
                territory_id=ter,
            )
            return decision

        # --- Passed All Rules: ACCEPTED ---
        decision = self._record_acceptance(
            lid,
            title_id=tid,
            territory_id=ter,
            exclusivity=excl,
            parsed_windows=parsed_windows,
            raw_data=lic_data,
        )
        return decision

    # -----------------------------------------------------------------------
    # Decision Recording and Audit Logging
    # -----------------------------------------------------------------------
    def _record_rejection(
        self,
        licence_id: str,
        reason: str,
        conflicting_licence_id: str,
        message: str,
        title_id: str = "",
        territory_id: str = "",
    ) -> ValidationDecision:
        audit_id = self._log_audit(
            licence_id=licence_id,
            action="VALIDATION_REJECTED",
            payload={
                "result": "REJECTED",
                "reason": reason,
                "conflicting_licence_id": conflicting_licence_id,
                "message": message,
                "title_id": title_id,
                "territory_id": territory_id,
            },
        )
        decision = ValidationDecision(
            licence_id=licence_id,
            result="REJECTED",
            reason=reason,
            conflicting_licence_id=conflicting_licence_id,
            message=message,
            audit_id=audit_id,
        )
        self.validation_records.append(decision.to_dict())
        self.decisions.append(decision)
        return decision

    def _record_acceptance(
        self,
        licence_id: str,
        title_id: str,
        territory_id: str,
        exclusivity: str,
        parsed_windows: List[WindowRange],
        raw_data: Dict[str, Any],
    ) -> ValidationDecision:
        audit_id = self._log_audit(
            licence_id=licence_id,
            action="VALIDATION_ACCEPTED",
            payload={
                "result": "ACCEPTED",
                "title_id": title_id,
                "territory_id": territory_id,
                "exclusivity": exclusivity,
                "window_count": len(parsed_windows),
                "windows": [
                    {"no": w.window_no, "start": str(w.start_date), "end": str(w.end_date)}
                    for w in parsed_windows
                ],
            },
        )
        self.accepted_licences.append(licence_id)
        self.accepted_licence_records[licence_id] = {
            "licence_id": licence_id,
            "title_id": title_id,
            "territory_id": territory_id,
            "exclusivity": exclusivity,
            "parsed_windows": parsed_windows,
            "raw_data": raw_data,
        }
        decision = ValidationDecision(
            licence_id=licence_id,
            result="ACCEPTED",
            reason="",
            conflicting_licence_id="",
            message=f"Licence '{licence_id}' successfully validated and accepted.",
            audit_id=audit_id,
        )
        self.validation_records.append(decision.to_dict())
        self.decisions.append(decision)
        return decision

    def _log_audit(self, licence_id: str, action: str, payload: Dict[str, Any]) -> Optional[str]:
        """Writes tamper-evident audit log record to DB if enabled."""
        if not self.enable_db_audit:
            return None

        try:
            with get_db_session() as session:
                payload_str = json.dumps(payload, default=str)
                hash_digest = hashlib.sha256(f"{licence_id}:{action}:{payload_str}".encode("utf-8")).hexdigest()
                log_entry = AuditLog(
                    table_name="licence_contracts",
                    record_id=licence_id,
                    action=action,
                    performed_by="LICENCE_VALIDATION_ENGINE",
                    new_values_json=payload_str,
                    cryptographic_hash=hash_digest,
                )
                session.add(log_entry)
                session.flush()
                return log_entry.log_id
        except Exception:
            # Fallback gracefully if database session is outside a migration/context
            return None

    # -----------------------------------------------------------------------
    # CSV Deliverable Export
    # -----------------------------------------------------------------------
    def export_validation_csv(self, output_file: Union[str, Path]) -> None:
        """Exports licence_validation.csv in exact evaluation format."""
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["licence_id", "result", "reason", "conflicting_licence_id"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in self.validation_records:
                writer.writerow(r)
