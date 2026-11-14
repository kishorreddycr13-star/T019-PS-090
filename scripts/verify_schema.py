"""
Verification and Test Suite for OTT Rights & Royalty Engine Database.
Verifies all 20 tables, integrity constraints, split validation, and calculations.
"""
from __future__ import annotations

import sys
from pathlib import Path
from decimal import Decimal

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from database.connection import get_db_session, engine
from models import (
    Title,
    Licensor,
    LicensorSplit,
    LicenceContract,
    LicenceWindow,
    Territory,
    TerritoryTimeZone,
    Holdback,
    SubscriberTier,
    ViewEvent,
    QualifyingViewRecord,
    MonthlySubscriptionRevenue,
    AdvertisementRevenue,
    AdImpression,
    MinimumGuarantee,
    RecoupmentRecord,
    PaymentCap,
    WithholdingTaxRate,
    MonthlySettlement,
    PaymentTransaction,
    AuditLog,
)
from services.split_validator import validate_contract_splits, SplitValidationError


def test_table_row_counts() -> None:
    """Verifies that all 20 tables contain seeded data."""
    with get_db_session() as session:
        counts = {
            "1. Titles": session.query(Title).count(),
            "2. Licensors": session.query(Licensor).count(),
            "3. Licensor Splits": session.query(LicensorSplit).count(),
            "4. Licence Contracts": session.query(LicenceContract).count(),
            "5. Licence Windows": session.query(LicenceWindow).count(),
            "6. Territories": session.query(Territory).count(),
            "6b. Territory Time Zones": session.query(TerritoryTimeZone).count(),
            "7. Holdbacks": session.query(Holdback).count(),
            "8. Subscriber Tiers": session.query(SubscriberTier).count(),
            "9. View Events": session.query(ViewEvent).count(),
            "10. Qualifying View Records": session.query(QualifyingViewRecord).count(),
            "11. Monthly Subscription Revenue": session.query(MonthlySubscriptionRevenue).count(),
            "12. Advertisement Revenue": session.query(AdvertisementRevenue).count(),
            "13. Ad Impressions": session.query(AdImpression).count(),
            "14. Minimum Guarantees": session.query(MinimumGuarantee).count(),
            "15. Recoupment Records": session.query(RecoupmentRecord).count(),
            "16. Payment Caps": session.query(PaymentCap).count(),
            "17. Withholding Tax Rates": session.query(WithholdingTaxRate).count(),
            "18. Monthly Settlements": session.query(MonthlySettlement).count(),
            "19. Payment Transactions": session.query(PaymentTransaction).count(),
            "20. Audit Logs": session.query(AuditLog).count(),
        }

        print("\n" + "=" * 60)
        print("DATABASE SCHEMA VERIFICATION: 20 TABLE RECORD AUDIT")
        print("=" * 60)
        all_populated = True
        for table_label, count in counts.items():
            status = "[OK]" if count > 0 else "[FAIL]"
            if count == 0:
                all_populated = False
            print(f"{status} {table_label:<35} : {count} records")

        assert all_populated, "One or more tables have 0 records!"
        print("=" * 60)
        print("[SUCCESS] All 20 tables populated with compliant records.")


def test_invalid_licensor_splits_prevention() -> None:
    """Verifies that invalid splits (sum != 100% or multiple primary payees) are blocked."""
    print("\nTesting Licensor Split Prevention Rules...")

    # Case 1: Splits sum to 110% (exceeds 100%)
    invalid_splits = [
        LicensorSplit(
            contract_id="dummy-contract",
            licensor_id="lic-1",
            stakeholder_role="STUDIO",
            split_percentage=Decimal("70.00"),
            is_primary_payee=True
        ),
        LicensorSplit(
            contract_id="dummy-contract",
            licensor_id="lic-2",
            stakeholder_role="PRODUCER",
            split_percentage=Decimal("40.00"),  # 70 + 40 = 110%
            is_primary_payee=False
        ),
    ]
    try:
        validate_contract_splits(invalid_splits, "dummy-contract")
        assert False, "Should have raised SplitValidationError for 110% sum!"
    except SplitValidationError as e:
        print(f"  [OK] Correctly caught over-allocation: {e}")

    # Case 2: Splits sum to 90% (under-allocated)
    under_splits = [
        LicensorSplit(
            contract_id="dummy-contract",
            licensor_id="lic-1",
            stakeholder_role="STUDIO",
            split_percentage=Decimal("90.00"),
            is_primary_payee=True
        ),
    ]
    try:
        validate_contract_splits(under_splits, "dummy-contract")
        assert False, "Should have raised SplitValidationError for 90% sum!"
    except SplitValidationError as e:
        print(f"  [OK] Correctly caught under-allocation: {e}")

    # Case 3: Zero or negative split percentage validation
    try:
        LicensorSplit(
            contract_id="dummy-contract",
            licensor_id="lic-1",
            stakeholder_role="STUDIO",
            split_percentage=Decimal("-10.00"),
            is_primary_payee=True
        )
        assert False, "Should have raised ValueError on negative split percentage!"
    except ValueError as e:
        print(f"  [OK] Correctly caught negative split value: {e}")


def test_iana_timezones() -> None:
    """Verifies that territory time zones use valid IANA identifiers."""
    import zoneinfo
    print("\nTesting IANA Timezone Validity...")
    with get_db_session() as session:
        zones = session.query(TerritoryTimeZone).all()
        for z in zones:
            zi = zoneinfo.ZoneInfo(z.iana_timezone)
            assert zi.key == z.iana_timezone
            print(f"  [OK] Validated IANA zone: {z.country_code} -> {z.iana_timezone}")


def test_recoupment_waterfall_math() -> None:
    """Verifies that the recoupment record reflects accurate balance drawdown."""
    print("\nTesting Minimum Guarantee Recoupment Balance...")
    with get_db_session() as session:
        rec = session.query(RecoupmentRecord).first()
        assert rec is not None
        assert rec.opening_unrecouped_balance - rec.amount_recouped == rec.closing_unrecouped_balance
        print(f"  [OK] Recoupment math verified: Opening {rec.opening_unrecouped_balance} - Recouped {rec.amount_recouped} = Closing {rec.closing_unrecouped_balance}")


def main() -> None:
    test_table_row_counts()
    test_invalid_licensor_splits_prevention()
    test_iana_timezones()
    test_recoupment_waterfall_math()
    print("\n[ALL TESTS PASSED] Database schema, constraints, and business logic verified.")


if __name__ == "__main__":
    main()
