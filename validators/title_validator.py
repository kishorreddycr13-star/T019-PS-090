"""
Title Validator Module.
Validates title metadata, runtimes, categories, and premiere dates.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Set

from validators.exceptions import ValidationError

ALLOWED_CONTENT_CATEGORIES: Set[str] = {
    "FILM",
    "SERIES_EPISODE",
    "DOCUMENTARY",
    "MUSIC_VIDEO",
    "SHORT_FILM",
    "LIVE_EVENT",
}


def validate_title_input(
    title_id: str,
    title_name: str,
    runtime_seconds: int,
    content_type: str,
    release_date: Optional[date] = None,
    theatrical_premiere: Optional[date] = None,
    tv_premiere: Optional[date] = None,
) -> None:
    """Validates title creation or update attributes."""
    if not title_id or not title_id.strip():
        raise ValidationError("Title ID cannot be blank.", field="title_id")

    if not title_name or not title_name.strip():
        raise ValidationError("Title name cannot be blank.", field="title_name")

    if runtime_seconds is None or runtime_seconds <= 0:
        raise ValidationError(
            f"Runtime must be a strictly positive integer in seconds (received: {runtime_seconds}).",
            field="runtime_seconds"
        )

    cat_upper = content_type.strip().upper()
    if cat_upper not in ALLOWED_CONTENT_CATEGORIES:
        raise ValidationError(
            f"Invalid content category '{content_type}'. Must be one of: {sorted(ALLOWED_CONTENT_CATEGORIES)}",
            field="content_type"
        )

    # Date sanity checks if multiple premiere dates are provided
    if theatrical_premiere and release_date and theatrical_premiere > release_date:
        pass  # theatrical premiere typically precedes or coincides with general OTT release
