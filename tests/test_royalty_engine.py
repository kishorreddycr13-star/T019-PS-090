"""
Unit Tests for Phase 8: Royalty Adjustment and Payment Calculation Engine.
Covers BR-07 (Minimum Guarantee & Recoupment), BR-08 (Payment Caps),
BR-09 (Withholding Tax & Treaty Rates), and BR-10 (Co-Licensor Splits with Residue).

Verifies all 20 required scenarios:
 1. MG paid in the first month of the first window.
 2. Licence without MG (contract_mg = 0.00).
 3. Partial MG recoupment.
 4. MG fully recouped.
 5. MG never fully recouped (no clawback).
 6. MG recouped exactly in the final month of the window (EC-04).
 7. Duplicate MG payment prevention.
 8. Licence without payment cap (unlimited).
 9. Cap reached mid-month (EC-05).
10. Cap exhausted across multiple months.
11. No additional payment after cap exhaustion.
12. Indian licensor with 10% TDS.
13. Foreign licensor with 20% TDS.
14. Foreign licensor with treaty rate (e.g. 15%).
15. Co-licensor split of 33.33/33.33/33.34 (EC-07).
16. One-paisa rounding residue allocation.
17. Multiple co-licensors with unequal splits.
18. Zero revenue share handling.
19. MG and cap interaction.
20. TDS calculated on net amount after MG recoupment.
"""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.mg_service import MGService
from services.recoupment_service import RecoupmentService
from services.cap_service import CapService
from services.tax_service import TaxService
from services.licensor_split_service import LicensorSplitService
from services.royalty_service import RoyaltyService
from validators.exceptions import SplitValidationError


class TestRoyaltyEngine(unittest.TestCase):
    """Test suite verifying BR-07, BR-08, BR-09, and BR-10 across all 20 required scenarios."""

    def setUp(self) -> None:
        self.mg_svc = MGService(
            windows_map={
                "LCN-TEST": [{"window_start": "2026-07-01", "window_end": "2026-09-30"}],
                "LCN-015": [{"window_start": "2026-07-01", "window_end": "2026-09-30"}],
            }
        )
        self.recoup_svc = RecoupmentService()
        self.cap_svc = CapService()
        self.tax_svc = TaxService()
        self.split_svc = LicensorSplitService()
        self.royalty_svc = RoyaltyService()

    # -------------------------------------------------------------------------
    # Scenario 1: MG paid in the first month of the first window
    # -------------------------------------------------------------------------
    def test_01_mg_paid_in_first_month_of_first_window(self) -> None:
        mg_paid, is_new = self.mg_svc.evaluate_mg_payout(
            licence_id="LCN-TEST",
            month="2026-07",
            contract_mg=Decimal("100000.00"),
            split_pct=Decimal("100.00"),
        )
        self.assertTrue(is_new)
        self.assertEqual(mg_paid, Decimal("100000.00"))

    # -------------------------------------------------------------------------
    # Scenario 2: Licence without MG (contract_mg = 0.00)
    # -------------------------------------------------------------------------
    def test_02_licence_without_mg(self) -> None:
        mg_paid, is_new = self.mg_svc.evaluate_mg_payout(
            licence_id="LCN-TEST",
            month="2026-07",
            contract_mg=Decimal("0.00"),
        )
        self.assertFalse(is_new)
        self.assertEqual(mg_paid, Decimal("0.00"))
        self.assertEqual(self.mg_svc.get_outstanding_balance("LCN-TEST"), Decimal("0.00"))

    # -------------------------------------------------------------------------
    # Scenario 3: Partial MG recoupment
    # -------------------------------------------------------------------------
    def test_03_partial_mg_recoupment(self) -> None:
        res = self.recoup_svc.calculate_recoupment(
            gross_share=Decimal("20000.00"),
            outstanding_mg=Decimal("50000.00"),
        )
        self.assertEqual(res.recouped_amount, Decimal("20000.00"))
        self.assertEqual(res.outstanding_mg_after, Decimal("30000.00"))
        self.assertEqual(res.excess_payable, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # Scenario 4: MG fully recouped
    # -------------------------------------------------------------------------
    def test_04_mg_fully_recouped(self) -> None:
        res = self.recoup_svc.calculate_recoupment(
            gross_share=Decimal("50000.00"),
            outstanding_mg=Decimal("30000.00"),
        )
        self.assertEqual(res.recouped_amount, Decimal("30000.00"))
        self.assertEqual(res.outstanding_mg_after, Decimal("0.00"))
        self.assertEqual(res.excess_payable, Decimal("20000.00"))

    # -------------------------------------------------------------------------
    # Scenario 5: MG never fully recouped (no clawback)
    # -------------------------------------------------------------------------
    def test_05_mg_never_fully_recouped(self) -> None:
        # Initial MG = 100,000; total gross across run = 10,000
        res = self.recoup_svc.calculate_recoupment(
            gross_share=Decimal("10000.00"),
            outstanding_mg=Decimal("100000.00"),
        )
        self.assertEqual(res.recouped_amount, Decimal("10000.00"))
        self.assertEqual(res.outstanding_mg_after, Decimal("90000.00"))
        # Licensor is not forced to refund the remaining 90,000 unrecouped MG advance
        self.assertEqual(res.excess_payable, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # Scenario 6: MG recouped exactly in the final month of the window (EC-04)
    # -------------------------------------------------------------------------
    def test_06_mg_recouped_exactly_in_final_month(self) -> None:
        contract_mg = Decimal("389735.59")
        # Month 1 (July): Gross 185,069.73
        res1 = self.recoup_svc.calculate_recoupment(Decimal("185069.73"), contract_mg)
        self.assertEqual(res1.recouped_amount, Decimal("185069.73"))
        self.assertEqual(res1.outstanding_mg_after, Decimal("204665.86"))

        # Month 2 (August): Gross 79,284.27
        res2 = self.recoup_svc.calculate_recoupment(Decimal("79284.27"), res1.outstanding_mg_after)
        self.assertEqual(res2.recouped_amount, Decimal("79284.27"))
        self.assertEqual(res2.outstanding_mg_after, Decimal("125381.59"))

        # Month 3 (September): Gross exactly 125,381.59
        res3 = self.recoup_svc.calculate_recoupment(Decimal("125381.59"), res2.outstanding_mg_after)
        self.assertEqual(res3.recouped_amount, Decimal("125381.59"))
        self.assertEqual(res3.outstanding_mg_after, Decimal("0.00"))
        self.assertEqual(res3.excess_payable, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # Scenario 7: Duplicate MG payment prevention
    # -------------------------------------------------------------------------
    def test_07_duplicate_mg_payment_prevention(self) -> None:
        # Payout in July (Month 1)
        mg_paid1, is_new1 = self.mg_svc.evaluate_mg_payout("LCN-TEST", "2026-07", Decimal("50000.00"))
        self.assertTrue(is_new1)
        self.mg_svc.record_mg_advance_initialized("LCN-TEST", Decimal("50000.00"))

        # Subsequent check in July or August does not disburse MG again
        mg_paid2, is_new2 = self.mg_svc.evaluate_mg_payout("LCN-TEST", "2026-08", Decimal("50000.00"))
        self.assertFalse(is_new2)
        self.assertEqual(mg_paid2, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # Scenario 8: Licence without payment cap (unlimited)
    # -------------------------------------------------------------------------
    def test_08_licence_without_payment_cap(self) -> None:
        res = self.cap_svc.apply_payment_cap(
            licence_id="LCN-NOCAP",
            payable_amount=Decimal("1500000.00"),
            contract_cap=Decimal("0.00"),
        )
        self.assertEqual(res.payable_after_cap, Decimal("1500000.00"))
        self.assertEqual(res.cap_retained, Decimal("0.00"))
        self.assertEqual(res.status, "SETTLED")

    # -------------------------------------------------------------------------
    # Scenario 9: Cap reached mid-month (EC-05)
    # -------------------------------------------------------------------------
    def test_09_cap_reached_mid_month(self) -> None:
        cap = Decimal("765178.48")
        # Month 1: 556,769.78 paid
        res1 = self.cap_svc.apply_payment_cap("LCN-032", Decimal("556769.78"), cap)
        self.assertEqual(res1.payable_after_cap, Decimal("556769.78"))
        self.assertEqual(res1.status, "SETTLED")

        # Month 2: Candidate 563,266.75; headroom is 208,408.70
        res2 = self.cap_svc.apply_payment_cap("LCN-032", Decimal("563266.75"), cap)
        self.assertEqual(res2.payable_after_cap, Decimal("208408.70"))
        self.assertEqual(res2.cap_retained, Decimal("354858.05"))
        self.assertEqual(res2.status, "CAPPED")
        self.assertEqual(res2.cumulative_paid_after, cap)

    # -------------------------------------------------------------------------
    # Scenario 10: Cap exhausted across multiple months
    # -------------------------------------------------------------------------
    def test_10_cap_exhausted_across_multiple_months(self) -> None:
        cap = Decimal("100000.00")
        # Month 1: 60,000 paid
        res1 = self.cap_svc.apply_payment_cap("LCN-CAP2", Decimal("60000.00"), cap)
        self.assertEqual(res1.payable_after_cap, Decimal("60000.00"))
        self.assertEqual(res1.status, "SETTLED")

        # Month 2: 40,000 paid (hits exact cap)
        res2 = self.cap_svc.apply_payment_cap("LCN-CAP2", Decimal("40000.00"), cap)
        self.assertEqual(res2.payable_after_cap, Decimal("40000.00"))
        self.assertEqual(res2.status, "CAPPED")

    # -------------------------------------------------------------------------
    # Scenario 11: No additional payment after cap exhaustion
    # -------------------------------------------------------------------------
    def test_11_no_additional_payment_after_cap_exhaustion(self) -> None:
        cap = Decimal("100000.00")
        self.cap_svc.apply_payment_cap("LCN-CAP3", Decimal("100000.00"), cap)

        # Subsequent month attempt to pay 50,000
        res = self.cap_svc.apply_payment_cap("LCN-CAP3", Decimal("50000.00"), cap)
        self.assertEqual(res.payable_after_cap, Decimal("0.00"))
        self.assertEqual(res.cap_retained, Decimal("50000.00"))
        self.assertEqual(res.status, "CAPPED")

    # -------------------------------------------------------------------------
    # Scenario 12: Indian licensor with 10% TDS
    # -------------------------------------------------------------------------
    def test_12_indian_licensor_10_percent_tds(self) -> None:
        res = self.tax_svc.calculate_tax(
            licensor_id="LIC-IN-01",
            payable_before_tds=Decimal("100000.00"),
            is_indian=True,
        )
        self.assertEqual(res.tds_pct, Decimal("10.00"))
        self.assertEqual(res.tds_amount, Decimal("10000.00"))
        self.assertEqual(res.net_payable, Decimal("90000.00"))

    # -------------------------------------------------------------------------
    # Scenario 13: Foreign licensor with 20% TDS
    # -------------------------------------------------------------------------
    def test_13_foreign_licensor_20_percent_tds(self) -> None:
        res = self.tax_svc.calculate_tax(
            licensor_id="LIC-FR-01",
            payable_before_tds=Decimal("100000.00"),
            is_indian=False,
            treaty_tds_pct=None,
        )
        self.assertEqual(res.tds_pct, Decimal("20.00"))
        self.assertEqual(res.tds_amount, Decimal("20000.00"))
        self.assertEqual(res.net_payable, Decimal("80000.00"))

    # -------------------------------------------------------------------------
    # Scenario 14: Foreign licensor with treaty rate (e.g. 15%)
    # -------------------------------------------------------------------------
    def test_14_foreign_licensor_with_treaty_rate(self) -> None:
        res = self.tax_svc.calculate_tax(
            licensor_id="LIC-FR-02",
            payable_before_tds=Decimal("100000.00"),
            is_indian=False,
            treaty_tds_pct="15.00",
        )
        self.assertEqual(res.tds_pct, Decimal("15.00"))
        self.assertEqual(res.tds_amount, Decimal("15000.00"))
        self.assertEqual(res.net_payable, Decimal("85000.00"))

    # -------------------------------------------------------------------------
    # Scenario 15: Co-licensor split of 33.33/33.33/33.34 (EC-07)
    # -------------------------------------------------------------------------
    def test_15_co_licensor_split_33_33_33_34(self) -> None:
        splits = [
            {"licensor_id": "LIC-01", "split_pct": "33.33"},
            {"licensor_id": "LIC-09", "split_pct": "33.33"},
            {"licensor_id": "LIC-04", "split_pct": "33.34"},
        ]
        gross = Decimal("151593.74")
        allocs = self.split_svc.allocate_splits(gross, splits, title_id="TTL-008")

        self.assertEqual(allocs["LIC-01"], Decimal("50526.19"))
        self.assertEqual(allocs["LIC-09"], Decimal("50526.19"))
        self.assertEqual(allocs["LIC-04"], Decimal("50541.36"))

        # Zero financial leakage
        self.assertEqual(sum(allocs.values()), gross)

    # -------------------------------------------------------------------------
    # Scenario 16: One-paisa rounding residue allocation
    # -------------------------------------------------------------------------
    def test_16_one_paisa_rounding_residue(self) -> None:
        # 100.01 split 50.00% and 50.00%
        # floor(100.01 * 0.50) = 50.00 each -> sum = 100.00 -> residue = 0.01
        splits = [
            {"licensor_id": "LIC-A", "split_pct": "50.00"},
            {"licensor_id": "LIC-B", "split_pct": "50.00"},
        ]
        allocs = self.split_svc.allocate_splits(Decimal("100.01"), splits)
        # Residue allocated deterministically
        self.assertEqual(sum(allocs.values()), Decimal("100.01"))
        self.assertIn(Decimal("50.01"), allocs.values())
        self.assertIn(Decimal("50.00"), allocs.values())

    # -------------------------------------------------------------------------
    # Scenario 17: Multiple co-licensors with unequal splits
    # -------------------------------------------------------------------------
    def test_17_multiple_co_licensors_unequal_splits(self) -> None:
        splits = [
            {"licensor_id": "LIC-MAIN", "split_pct": "60.00"},
            {"licensor_id": "LIC-SUB1", "split_pct": "25.00"},
            {"licensor_id": "LIC-SUB2", "split_pct": "15.00"},
        ]
        gross = Decimal("777777.77")
        allocs = self.split_svc.allocate_splits(gross, splits)
        self.assertEqual(sum(allocs.values()), gross)

    # -------------------------------------------------------------------------
    # Scenario 18: Zero revenue share handling
    # -------------------------------------------------------------------------
    def test_18_zero_revenue_share_handling(self) -> None:
        recoup_res = self.recoup_svc.calculate_recoupment(Decimal("0.00"), Decimal("5000.00"))
        self.assertEqual(recoup_res.recouped_amount, Decimal("0.00"))
        self.assertEqual(recoup_res.outstanding_mg_after, Decimal("5000.00"))

        tax_res = self.tax_svc.calculate_tax("LIC-01", Decimal("0.00"), is_indian=True)
        self.assertEqual(tax_res.tds_amount, Decimal("0.00"))
        self.assertEqual(tax_res.net_payable, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # Scenario 19: MG and cap interaction
    # -------------------------------------------------------------------------
    def test_19_mg_and_cap_interaction(self) -> None:
        # Contract with both MG (100,000) and Cap (150,000)
        cap = Decimal("150000.00")
        # Month 1: 100,000 advance paid counts toward the 150,000 cap headroom
        res1 = self.cap_svc.apply_payment_cap("LCN-MGCAP", Decimal("100000.00"), cap)
        self.assertEqual(res1.payable_after_cap, Decimal("100000.00"))
        self.assertEqual(res1.status, "SETTLED")

        # Month 2: Candidate payable 70,000 -> only 50,000 permitted
        res2 = self.cap_svc.apply_payment_cap("LCN-MGCAP", Decimal("70000.00"), cap)
        self.assertEqual(res2.payable_after_cap, Decimal("50000.00"))
        self.assertEqual(res2.cap_retained, Decimal("20000.00"))
        self.assertEqual(res2.status, "CAPPED")

    # -------------------------------------------------------------------------
    # Scenario 20: TDS calculated on net amount after MG recoupment
    # -------------------------------------------------------------------------
    def test_20_tds_calculated_after_mg_recoupment(self) -> None:
        # Gross = 50,000; Outstanding MG = 30,000 -> Recouped = 30,000 -> Excess = 20,000
        gross = Decimal("50000.00")
        mg_bal = Decimal("30000.00")
        recoup_res = self.recoup_svc.calculate_recoupment(gross, mg_bal)
        payable_before_tds = recoup_res.excess_payable  # 20,000.00

        # TDS applies to 20,000.00, NOT 50,000.00
        tax_res = self.tax_svc.calculate_tax(
            licensor_id="LIC-TEST",
            payable_before_tds=payable_before_tds,
            is_indian=True,  # 10%
        )
        self.assertEqual(tax_res.tds_amount, Decimal("2000.00"))
        self.assertEqual(tax_res.net_payable, Decimal("18000.00"))


if __name__ == "__main__":
    unittest.main()
