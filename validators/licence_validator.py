"""
Licence Validator Module.
Validates territory, exclusivity, revenue models, MG/Cap terms, holdbacks, and window date ranges.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Any

from validators.exceptions import (
    ValidationError,
    HoldbackViolationError,
)

ALLOWED_EXCLUSIVITY: set[str] = {"EXCLUSIVE", "NON_EXCLUSIVE"}
ALLOWED_REV_SHARE_TYPES: set[str] = {"POOL_AND_AD", "POOL_ONLY"}


def validate_licence_terms(
    licence_id: str,
    title_id: str,
    licensor_id: str,
    territory_id: str,
    exclusivity: str,
    revenue_share_type: str,
    mg_amount: Decimal,
    cap_amount: Decimal,
) -> None:
    """Validates commercial and territorial licence terms."""
    if not licence_id or not licence_id.strip():
        raise ValidationError("Licence ID cannot be blank.", field="licence_id")

    if not title_id or not title_id.strip():
        raise ValidationError("Title ID cannot be blank.", field="title_id")

    if not licensor_id or not licensor_id.strip():
        raise ValidationError("Licensor ID cannot be blank.", field="licensor_id")

    if not territory_id or not territory_id.strip():
        raise ValidationError("Territory ID cannot be blank.", field="territory_id")

    ex_upper = exclusivity.strip().upper()
    if ex_upper not in ALLOWED_EXCLUSIVITY:
        raise ValidationError(
            f"Invalid exclusivity '{exclusivity}'. Must be one of: {sorted(ALLOWED_EXCLUSIVITY)}",
            field="exclusivity"
        )

    rev_upper = revenue_share_type.strip().upper()
    if rev_upper not in ALLOWED_REV_SHARE_TYPES:
        raise ValidationError(
            f"Invalid revenue-share type '{revenue_share_type}'. Must be one of: {sorted(ALLOWED_REV_SHARE_TYPES)}",
            field="revenue_share_type"
        )

    if mg_amount < Decimal("0.00"):
        raise ValidationError(
            f"Minimum guarantee amount cannot be negative (received: {mg_amount}).",
            field="mg_amount"
        )

    if cap_amount < Decimal("0.00"):
        raise ValidationError(
            f"Payment cap amount cannot be negative (received: {cap_amount}).",
            field="cap_amount"
        )


def validate_licence_windows(
    windows: Sequence[Dict[str, Any]],
    theatrical_premiere: Optional[date] = None,
    tv_premiere: Optional[date] = None,
) -> None:
    """
    Validates licence availability windows:
    1. At least one window required.
    2. Window start must be on or before window end.
    3. Theatrical holdback: window start >= theatrical_premiere + 45 days.
    4. TV holdback: window start >= tv_premiere + 7 days.
    """
    if not windows:
        raise ValidationError("A licence must have at least one availability window defined.", field="windows")

    parsed_ranges = []
    for idx, w in enumerate(windows, start=1):
        s_val = w.get("window_start")
        e_val = w.get("window_end")

        if isinstance(s_val, str):
            start_dt = date.fromisoformat(s_val)
        else:
            start_dt = s_val

        if isinstance(e_val, str):
            end_dt = date.fromisoformat(e_val)
        else:
            end_dt = e_val

        if not start_dt or not end_dt:
            raise ValidationError(f"Window #{idx} is missing start or end date.", field="windows")

        if start_dt > end_dt:
            raise ValidationError(
                f"Window #{idx} start date ({start_dt}) cannot be after end date ({end_dt}).",
                field="windows"
            )

        parsed_ranges.append((idx, start_dt, end_dt))

        # 45-day Theatrical holdback check
        if theatrical_premiere:
            min_start = theatrical_premiere + timedelta(days=45)
            if start_dt < min_start:
                raise HoldbackViolationError(
                    f"Window #{idx} starts on {start_dt}, which violates the 45-day theatrical "
                    f"holdback from premiere {theatrical_premiere} (earliest allowed: {min_start}).",
                    premiere_type="THEATRICAL",
                    min_date=str(min_start)
                )

        # 7-day TV holdback check
        if tv_premiere:
            min_start = tv_premiere + timedelta(days=7)
            if start_dt < min_start:
                raise HoldbackViolationError(
                    f"Window #{idx} starts on {start_dt}, which violates the 7-day TV "
                    f"holdback from premiere {tv_premiere} (earliest allowed: {min_start}).",
                    premiere_type="TV",
                    min_date=str(min_start)
                )

    # Check for internal window overlaps within the same contract (adjacent windows allowed)
    for i in range(len(parsed_ranges)):
        for j in range(i + 1, len(parsed_ranges)):
            idx1, s1, e1 = parsed_ranges[i]
            idx2, s2, e2 = parsed_ranges[j]
            if max(s1, s2) <= min(e1, e2):
                raise ValidationError(
                    f"Windows #{idx1} ({s1} to {e1}) and #{idx2} ({s2} to {e2}) under the same licence overlap.",
                    field="windows"
                )
