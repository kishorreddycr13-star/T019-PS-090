"""
Domain Exceptions for Title, Licensor, and Licence Management.
Provides clear, actionable error reporting across services and CLI.
"""
from __future__ import annotations


class ManagementEngineError(Exception):
    """Base exception for management domain errors."""
    def __init__(self, message: str, code: str = "MANAGEMENT_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class EntityNotFoundError(ManagementEngineError):
    """Raised when a requested title, licensor, or licence does not exist."""
    def __init__(self, entity_type: str, identifier: str) -> None:
        super().__init__(
            f"{entity_type} with ID '{identifier}' was not found.",
            code="ENTITY_NOT_FOUND"
        )
        self.entity_type = entity_type
        self.identifier = identifier


class ValidationError(ManagementEngineError):
    """Raised when input fails validation constraints."""
    def __init__(self, message: str, field: str = "") -> None:
        super().__init__(message, code="VALIDATION_ERROR")
        self.field = field


class SplitValidationError(ValidationError):
    """Raised when licensor splits fail the 100.00% sum rule or range constraints."""
    def __init__(self, message: str) -> None:
        super().__init__(message, field="splits")
        self.code = "SPLIT_VALIDATION_ERROR"


class HoldbackViolationError(ValidationError):
    """Raised when a licence window violates theatrical or TV premiere holdback intervals."""
    def __init__(self, message: str, premiere_type: str, min_date: str) -> None:
        super().__init__(message, field="window_start")
        self.code = "HOLDBACK_VIOLATION"
        self.premiere_type = premiere_type
        self.min_date = min_date


class ExclusivityConflictError(ManagementEngineError):
    """Raised when a licence conflicts with an existing exclusive licence for overlapping windows."""
    def __init__(self, message: str, conflicting_licence_id: str) -> None:
        super().__init__(message, code="EXCLUSIVITY_CONFLICT")
        self.conflicting_licence_id = conflicting_licence_id


class SettlementTimingError(ManagementEngineError):
    """Raised when a monthly settlement run is attempted before the 10th of M+1 (BR-12)."""
    def __init__(self, message: str, month: str = "", run_ts: str = "", earliest_permitted: str = "") -> None:
        super().__init__(message, code="SETTLEMENT_TIMING_ERROR")
        self.month = month
        self.run_ts = run_ts
        self.earliest_permitted = earliest_permitted


class DuplicateSettlementError(ManagementEngineError):
    """Raised when a settlement for a period has already been executed and finalized."""
    def __init__(self, message: str, month: str = "", run_id: str = "") -> None:
        super().__init__(message, code="DUPLICATE_SETTLEMENT_ERROR")
        self.month = month
        self.run_id = run_id

