"""
Licence Manager Module.
Thin adapter around LicenceValidationEngine providing backwards compatibility
with the command processor and batch evaluation pipeline.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from engine.licence_validation_engine import (
    LicenceValidationEngine,
    ValidationDecision,
    WindowRange,
)


class LicenceManager(LicenceValidationEngine):
    """Manages licence lifecycle, holdback validation, and exclusivity conflict detection."""

    def __init__(
        self,
        titles: Dict[str, Dict[str, Any]],
        licences: Dict[str, Dict[str, Any]],
        windows: Dict[str, List[Dict[str, Any]]],
        territories: Optional[Dict[str, Dict[str, Any]]] = None,
        enable_db_audit: bool = True,
    ) -> None:
        super().__init__(
            titles=titles,
            licences=licences,
            windows=windows,
            territories=territories,
            enable_db_audit=enable_db_audit,
        )

    def create_licence(self, licence_id: str) -> Tuple[str, str, str]:
        """
        Validates holdback and exclusivity rules for a licence request in stream order:
        Returns:
            (result, reason, conflicting_licence_id)
        """
        decision = self.validate_licence(licence_id)
        return (decision.result, decision.reason, decision.conflicting_licence_id)
