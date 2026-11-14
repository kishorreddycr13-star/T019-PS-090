"""
Comprehensive Test Suite for All Planted Scenarios & Edge Cases (EC-01 to EC-08 + Traps).
Validates mathematical precision down to the exact paisa, de-duplication, holdbacks, and settlement balances.
"""
from __future__ import annotations

import csv
import sys
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from run_engine import run_pipeline


def load_csv_rows_by_key(csv_path: Path, key_col: str):
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {r[key_col]: r for r in reader}


def load_csv_rows_multi_key(csv_path: Path, key_func):
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {key_func(r): r for r in reader}


def test_all_scenarios():
    local_sample_dir = PROJECT_ROOT / "sample_data"
    data_dir = local_sample_dir if local_sample_dir.exists() else Path(r"C:\Users\kisho\Downloads\T019-PS-090-sample-data\T019-PS-090-sample-data")
    output_dir = PROJECT_ROOT / "evaluation_outputs"

    # Execute full pipeline
    run_pipeline(data_dir, output_dir)

    print("\n" + "=" * 70)
    print("VERIFYING PLANTED SCENARIOS AGAINST ENGINE EVALUATION OUTPUTS")
    print("=" * 70)

    # Load produced CSVs
    lic_val = load_csv_rows_by_key(output_dir / "licence_validation.csv", "licence_id")
    views = load_csv_rows_by_key(output_dir / "view_decisions.csv", "view_id")
    title_shares = load_csv_rows_multi_key(
        output_dir / "title_shares.csv",
        lambda r: (r["month"], r["territory_id"], r["title_id"])
    )
    settlements = load_csv_rows_multi_key(
        output_dir / "settlements.csv",
        lambda r: (r["month"], r["licence_id"], r["licensor_id"])
    )

    # -------------------------------------------------------------------------
    # EC-01: View starting at 23:59:59 local time on the window end day
    # -------------------------------------------------------------------------
    v_1417 = views["VW-001417"]
    assert v_1417["decision"] == "ALLOWED", f"EC-01 failed: {v_1417}"
    assert v_1417["licence_id"] == "LCN-028", f"EC-01 licence mismatch: {v_1417}"
    assert v_1417["local_start"] == "2026-08-31 23:59:59", f"EC-01 local_start mismatch: {v_1417}"
    print("  [PASS] EC-01: VW-001417 at 23:59:59 local is ALLOWED under LCN-028.")

    # -------------------------------------------------------------------------
    # EC-02: Title runtime 180s -> qualifying threshold is 90s, not 120s
    # -------------------------------------------------------------------------
    v_997 = views["VW-000997"]   # 95 seconds
    v_999 = views["VW-000999"]   # 85 seconds
    assert v_997["qualifying"] == "true", f"EC-02 failed for 95s: {v_997}"
    assert v_999["qualifying"] == "false", f"EC-02 failed for 85s: {v_999}"
    print("  [PASS] EC-02: 180s runtime threshold is 90s (95s qualifies, 85s fails).")

    # -------------------------------------------------------------------------
    # EC-03: Same subscriber watching title within 24 hours counts once
    # -------------------------------------------------------------------------
    v_491 = views["VW-000491"]   # 2026-07-21 10:00 IST
    v_512 = views["VW-000512"]   # 2026-07-22 09:59 IST (23h 59m apart)
    assert v_491["counted"] == "true", f"EC-03 failed: {v_491}"
    assert v_512["counted"] == "false", f"EC-03 duplicate was counted: {v_512}"
    assert v_512["view_hours"] == "0.0000", f"EC-03 duplicate added view_hours: {v_512}"
    print("  [PASS] EC-03: 24h de-duplication correctly discarded VW-000512 (view_hours=0.0000).")

    # -------------------------------------------------------------------------
    # EC-04: MG recouped exactly in final month of the window (LCN-015)
    # -------------------------------------------------------------------------
    s_015_jul = settlements[("2026-07", "LCN-015", "LIC-02")]
    s_015_aug = settlements[("2026-08", "LCN-015", "LIC-02")]
    s_015_sep = settlements[("2026-09", "LCN-015", "LIC-02")]

    assert s_015_jul["gross_share"] == "185069.73", f"EC-04 July gross mismatch: {s_015_jul}"
    assert s_015_jul["mg_paid"] == "389735.59", f"EC-04 July MG paid mismatch: {s_015_jul}"
    assert s_015_jul["recouped"] == "185069.73", f"EC-04 July recouped mismatch: {s_015_jul}"
    assert s_015_jul["mg_balance"] == "204665.86", f"EC-04 July mg_balance mismatch: {s_015_jul}"

    assert s_015_aug["gross_share"] == "79284.27", f"EC-04 August gross mismatch: {s_015_aug}"
    assert s_015_aug["recouped"] == "79284.27", f"EC-04 August recouped mismatch: {s_015_aug}"
    assert s_015_aug["mg_balance"] == "125381.59", f"EC-04 August mg_balance mismatch: {s_015_aug}"
    assert s_015_aug["payable_before_tds"] == "0.00", f"EC-04 August payable mismatch: {s_015_aug}"

    assert s_015_sep["gross_share"] == "125381.59", f"EC-04 September gross mismatch: {s_015_sep}"
    assert s_015_sep["recouped"] == "125381.59", f"EC-04 September recouped mismatch: {s_015_sep}"
    assert s_015_sep["mg_balance"] == "0.00", f"EC-04 September mg_balance mismatch: {s_015_sep}"
    assert s_015_sep["payable_before_tds"] == "0.00", f"EC-04 September payable mismatch: {s_015_sep}"
    assert s_015_sep["net_payable"] == "0.00", f"EC-04 September net mismatch: {s_015_sep}"
    print("  [PASS] EC-04: LCN-015 MG (Rs 389,735.59) recouped exactly in Sept (Rs 0.00 payable).")

    # -------------------------------------------------------------------------
    # EC-05: Cap reached mid-month - partial share paid up to cap (LCN-032)
    # -------------------------------------------------------------------------
    s_032_jul = settlements[("2026-07", "LCN-032", "LIC-07")]
    s_032_aug = settlements[("2026-08", "LCN-032", "LIC-07")]
    s_032_sep = settlements[("2026-09", "LCN-032", "LIC-07")]

    assert s_032_jul["gross_share"] == "556769.78", f"EC-05 July mismatch: {s_032_jul}"
    assert s_032_jul["payable_before_tds"] == "556769.78", f"EC-05 July payable: {s_032_jul}"
    assert s_032_jul["status"] == "SETTLED", f"EC-05 July status: {s_032_jul}"

    assert s_032_aug["gross_share"] == "563266.75", f"EC-05 August gross mismatch: {s_032_aug}"
    assert s_032_aug["payable_before_tds"] == "208408.70", f"EC-05 August partial payable: {s_032_aug}"
    assert s_032_aug["cap_retained"] == "354858.05", f"EC-05 August cap retained: {s_032_aug}"
    assert s_032_aug["status"] == "CAPPED", f"EC-05 August status: {s_032_aug}"

    assert s_032_sep["payable_before_tds"] == "0.00", f"EC-05 September payable: {s_032_sep}"
    assert s_032_sep["cap_retained"] == s_032_sep["gross_share"], f"EC-05 September cap retained: {s_032_sep}"
    assert s_032_sep["status"] == "CAPPED", f"EC-05 September status: {s_032_sep}"
    print("  [PASS] EC-05: LCN-032 Cap (Rs 765,178.48) reached in Aug (Rs 208,408.70 paid, CAPPED).")

    # -------------------------------------------------------------------------
    # EC-06: Two territories straddling UTC midnight
    # -------------------------------------------------------------------------
    v_1418 = views["VW-001418"]   # IN territory (offset +05:30 -> 2026-09-01 04:00 IST)
    v_1419 = views["VW-001419"]   # US territory (offset -04:00 -> 2026-08-31 18:30 EDT)
    assert v_1418["decision"] == "DENIED", f"EC-06 IN view should be DENIED: {v_1418}"
    assert v_1419["decision"] == "ALLOWED", f"EC-06 US view should be ALLOWED: {v_1419}"
    print("  [PASS] EC-06: UTC midnight straddle: VW-001418 (IN) is DENIED, VW-001419 (US) is ALLOWED.")

    # -------------------------------------------------------------------------
    # EC-07: Co-licensor split 33.33/33.33/33.34 with 1 paisa residue (LCN-012)
    # -------------------------------------------------------------------------
    s_012_l1 = settlements[("2026-07", "LCN-012", "LIC-01")]
    s_012_l9 = settlements[("2026-07", "LCN-012", "LIC-09")]
    s_012_l4 = settlements[("2026-07", "LCN-012", "LIC-04")]

    assert s_012_l1["gross_share"] == "50526.19", f"EC-07 LIC-01 gross mismatch: {s_012_l1}"
    assert s_012_l9["gross_share"] == "50526.19", f"EC-07 LIC-09 gross mismatch: {s_012_l9}"
    # LIC-04 receives the 1 paisa residue (50541.35 + 0.01 = 50541.36)
    assert s_012_l4["gross_share"] == "50541.36", f"EC-07 LIC-04 gross mismatch: {s_012_l4}"
    sum_parts = Decimal(s_012_l1["gross_share"]) + Decimal(s_012_l9["gross_share"]) + Decimal(s_012_l4["gross_share"])
    assert sum_parts == Decimal("151593.74"), f"EC-07 sum mismatch: {sum_parts}"
    print("  [PASS] EC-07: Co-licensor split (33.33/33.33/33.34): 50526.19 + 50526.19 + 50541.36 = 151593.74.")

    # -------------------------------------------------------------------------
    # EC-08: Holdback validations
    # -------------------------------------------------------------------------
    assert lic_val["LCN-019"]["result"] == "ACCEPTED", f"EC-08 LCN-019 should be ACCEPTED: {lic_val['LCN-019']}"
    assert lic_val["LCN-054"]["result"] == "REJECTED", f"EC-08 LCN-054 should be REJECTED: {lic_val['LCN-054']}"
    assert lic_val["LCN-054"]["reason"] == "HOLDBACK", f"EC-08 LCN-054 reason: {lic_val['LCN-054']}"
    assert lic_val["LCN-009"]["result"] == "ACCEPTED", f"EC-08 LCN-009 should be ACCEPTED: {lic_val['LCN-009']}"
    print("  [PASS] EC-08: Holdbacks verified (LCN-019 ACCEPTED 45d, LCN-054 REJECTED 44d, LCN-009 ACCEPTED 7d TV).")

    # -------------------------------------------------------------------------
    # Extra Traps
    # -------------------------------------------------------------------------
    # Trap 1: LCN-055 exclusivity conflict with LCN-046
    assert lic_val["LCN-055"]["result"] == "REJECTED", f"Trap 1 LCN-055 should be REJECTED: {lic_val['LCN-055']}"
    assert lic_val["LCN-055"]["reason"] == "EXCLUSIVITY", f"Trap 1 LCN-055 reason: {lic_val['LCN-055']}"
    assert lic_val["LCN-055"]["conflicting_licence_id"] == "LCN-046", f"Trap 1 conflict mismatch: {lic_val['LCN-055']}"
    print("  [PASS] Trap 1: LCN-055 correctly rejected for EXCLUSIVITY conflict citing LCN-046.")

    # Trap 2: VW-001046 in window gap is DENIED
    assert views["VW-001046"]["decision"] == "DENIED", f"Trap 2 VW-001046 should be DENIED: {views['VW-001046']}"
    print("  [PASS] Trap 2: VW-001046 in window gap correctly DENIED.")

    # Trap 3: VW-001661 late view ingested after settlement is tagged LATE_VIEW
    v_1661 = views["VW-001661"]
    assert v_1661["tag"] == "LATE_VIEW", f"Trap 3 VW-001661 tag mismatch: {v_1661}"
    assert v_1661["settlement_month"] == "2026-09", f"Trap 3 VW-001661 settlement month mismatch: {v_1661}"
    print("  [PASS] Trap 3: VW-001661 correctly tagged LATE_VIEW and settled in September.")

    print("\n" + "=" * 70)
    print("[ALL PLANTED SCENARIOS VERIFIED 100% CORRECT]")
    print("=" * 70)


if __name__ == "__main__":
    test_all_scenarios()
