"""
OTT Rights, Windowing, and Revenue-Share Engine Package.
Implements BR-01 through BR-12, evaluation CSV outputs, and command stream processing.
"""
from engine.licence_validation_engine import (
    LicenceValidationEngine,
    ValidationDecision,
    WindowRange,
)
from engine.licence_manager import LicenceManager
from engine.playback_eligibility_engine import (
    PlaybackEligibilityEngine,
    PlaybackRequest,
    PlaybackDecision,
)
from engine.windowing_service import WindowingService
from engine.view_processor import ViewProcessor
from engine.revenue_settlement_engine import RevenueSettlementEngine
from engine.command_processor import CommandProcessor
from services.qualification_service import QualificationService, QualificationResult, TierContribution
from services.duplicate_detection import DuplicateDetector, DuplicateCheckResult
from services.metering_service import MeteringService
from services.subscription_calculator import SubscriptionCalculator, SubscriptionShareResult
from services.advertisement_calculator import AdvertisementCalculator, AdShareResult
from services.revenue_service import RevenueService
from services.mg_service import MGService, MGRecord
from services.recoupment_service import RecoupmentService, RecoupmentResult
from services.cap_service import CapService, CapEvaluationResult
from services.tax_service import TaxService, TaxCalculationResult
from services.licensor_split_service import LicensorSplitService, floor_paisa
from services.royalty_service import RoyaltyService
from services.settlement_service import SettlementService
from services.reporting_service import ReportingService

__all__ = [
    "LicenceValidationEngine",
    "ValidationDecision",
    "WindowRange",
    "LicenceManager",
    "PlaybackEligibilityEngine",
    "PlaybackRequest",
    "PlaybackDecision",
    "WindowingService",
    "ViewProcessor",
    "RevenueSettlementEngine",
    "CommandProcessor",
    "QualificationService",
    "QualificationResult",
    "TierContribution",
    "DuplicateDetector",
    "DuplicateCheckResult",
    "MeteringService",
    "SubscriptionCalculator",
    "SubscriptionShareResult",
    "AdvertisementCalculator",
    "AdShareResult",
    "RevenueService",
    "MGService",
    "MGRecord",
    "RecoupmentService",
    "RecoupmentResult",
    "CapService",
    "CapEvaluationResult",
    "TaxService",
    "TaxCalculationResult",
    "LicensorSplitService",
    "floor_paisa",
    "RoyaltyService",
    "SettlementService",
    "ReportingService",
]
