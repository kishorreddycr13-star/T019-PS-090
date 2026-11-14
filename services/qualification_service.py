"""
Qualification Service Module.
Implements BR-07 (Qualifying Views) and BR-09 (Subscriber Tier Classification).

Business Rules:
- BR-07: A view qualifies only when watch seconds are at least min(120, runtime * 0.50).
- BR-09: FREE tier views contribute to ad impressions only (view_hours = 0.0000).
         PREMIUM tier views contribute to subscription view-hours only (ad_impressions = 0).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple, Union


@dataclass(frozen=True)
class QualificationResult:
    """Holds the result of evaluating watch duration against the title runtime threshold."""
    is_qualifying: bool
    threshold_seconds: int
    watch_seconds: int
    runtime_seconds: int
    qualification_status: str
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "is_qualifying": self.is_qualifying,
            "threshold_seconds": self.threshold_seconds,
            "watch_seconds": self.watch_seconds,
            "runtime_seconds": self.runtime_seconds,
            "qualification_status": self.qualification_status,
            "message": self.message,
        }


@dataclass(frozen=True)
class TierContribution:
    """Represents the metered revenue contribution according to subscriber tier."""
    tier: str
    is_qualifying: bool
    is_counted: bool
    view_hours: Decimal
    ad_impressions: int
    pool_eligible: bool  # True for PREMIUM
    ad_eligible: bool    # True for FREE

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "is_qualifying": self.is_qualifying,
            "is_counted": self.is_counted,
            "view_hours": str(self.view_hours),
            "ad_impressions": self.ad_impressions,
            "pool_eligible": self.pool_eligible,
            "ad_eligible": self.ad_eligible,
        }


class QualificationService:
    """Service encapsulating qualifying threshold calculation and tier classification."""

    @staticmethod
    def compute_qualifying_threshold(runtime_seconds: int) -> int:
        """
        Computes the qualification threshold in seconds:
        Threshold = min(120, Runtime * 0.50)

        Examples:
        - Runtime 180s -> min(120, 90) = 90s
        - Runtime 300s -> min(120, 150) = 120s
        - Runtime 600s -> min(120, 300) = 120s
        """
        if runtime_seconds <= 0:
            raise ValueError(f"Runtime seconds must be positive, got {runtime_seconds}")
        
        half_runtime = int(runtime_seconds * 0.5)
        return min(120, half_runtime)

    @classmethod
    def evaluate_qualification(
        cls,
        watch_seconds: int,
        runtime_seconds: int,
    ) -> QualificationResult:
        """
        Evaluates whether a view event meets the minimum watch duration threshold.
        """
        if watch_seconds < 0:
            raise ValueError(f"Watch seconds cannot be negative, got {watch_seconds}")

        threshold = cls.compute_qualifying_threshold(runtime_seconds)
        is_qualifying = watch_seconds >= threshold

        if is_qualifying:
            status = "QUALIFIED"
            msg = f"Watch duration {watch_seconds}s meets or exceeds threshold {threshold}s (runtime {runtime_seconds}s)"
        else:
            status = "UNDER_THRESHOLD"
            msg = f"Watch duration {watch_seconds}s is below qualifying threshold {threshold}s (runtime {runtime_seconds}s)"

        return QualificationResult(
            is_qualifying=is_qualifying,
            threshold_seconds=threshold,
            watch_seconds=watch_seconds,
            runtime_seconds=runtime_seconds,
            qualification_status=status,
            message=msg,
        )

    @staticmethod
    def calculate_view_hours(watch_seconds: int) -> Decimal:
        """
        Converts watch seconds to view hours with 4 decimal places rounding half-up.
        View Hours = Watch Seconds / 3600
        """
        if watch_seconds <= 0:
            return Decimal("0.0000")
        return (Decimal(watch_seconds) / Decimal(3600)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

    @classmethod
    def classify_tier_contribution(
        cls,
        tier: str,
        watch_seconds: int,
        ad_impressions: int,
        is_qualifying: bool,
        is_counted: bool,
    ) -> TierContribution:
        """
        Applies BR-09 Subscriber Tier Classification:
        - FREE tier:
          * Qualifying & counted views contribute to advertisement revenue only.
          * Excluded from subscription revenue pool (view_hours = 0.0000).
        - PREMIUM tier:
          * Qualifying & counted views contribute to subscription revenue pool.
          * Excluded from advertisement revenue calculations (ad_impressions = 0).
        """
        clean_tier = tier.strip().upper()
        is_free = "FREE" in clean_tier or "AD" in clean_tier
        is_premium = "PREM" in clean_tier or clean_tier in {"STANDARD_HD", "MOBILE", "FAMILY"}

        if not (is_qualifying and is_counted):
            # Uncounted or non-qualifying views contribute nothing to revenue
            return TierContribution(
                tier=clean_tier,
                is_qualifying=is_qualifying,
                is_counted=is_counted,
                view_hours=Decimal("0.0000"),
                ad_impressions=0,
                pool_eligible=is_premium,
                ad_eligible=is_free,
            )

        if is_free:
            # FREE tier: ad impressions count, view_hours = 0.0000
            return TierContribution(
                tier=clean_tier,
                is_qualifying=True,
                is_counted=True,
                view_hours=Decimal("0.0000"),
                ad_impressions=max(0, ad_impressions),
                pool_eligible=False,
                ad_eligible=True,
            )
        else:
            # PREMIUM tier: view-hours count, ad impressions = 0
            vh = cls.calculate_view_hours(watch_seconds)
            return TierContribution(
                tier=clean_tier,
                is_qualifying=True,
                is_counted=True,
                view_hours=vh,
                ad_impressions=0,
                pool_eligible=True,
                ad_eligible=False,
            )
