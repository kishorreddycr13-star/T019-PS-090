"""
OTT Rights & Royalty Engine CLI Runner.
Executes commands.txt on input CSV masters and exports the 4 evaluation CSV files.
Usage:
    python run_engine.py [path_to_sample_data_dir] [output_dir]
"""
from __future__ import annotations

import csv
import sys
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine import (
    LicenceManager,
    WindowingService,
    ViewProcessor,
    RevenueSettlementEngine,
    CommandProcessor,
)


def load_csv_as_dict_by_key(csv_path: Path, key_col: str):
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {r[key_col]: r for r in reader}


def load_csv_as_list(csv_path: Path):
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def run_pipeline(data_dir: Path, output_dir: Path) -> None:
    print("=" * 70)
    print("OTT Rights & Royalty Engine (PS-090) - Evaluation Runner")
    print(f"Data Directory:   {data_dir}")
    print(f"Output Directory: {output_dir}")
    print("=" * 70)

    # 1. Load CSV Master Data
    print("Loading input CSV files...")
    territories = load_csv_as_dict_by_key(data_dir / "territories.csv", "territory_id")
    licensors = load_csv_as_dict_by_key(data_dir / "licensors.csv", "licensor_id")
    titles = load_csv_as_dict_by_key(data_dir / "titles.csv", "title_id")
    licences = load_csv_as_dict_by_key(data_dir / "licences.csv", "licence_id")

    # Title splits (grouped by title_id)
    title_splits = {}
    for r in load_csv_as_list(data_dir / "title_splits.csv"):
        title_splits.setdefault(r["title_id"], []).append(r)

    # Windows (grouped by licence_id)
    windows = {}
    for r in load_csv_as_list(data_dir / "licence_windows.csv"):
        windows.setdefault(r["licence_id"], []).append(r)

    # Revenues
    sub_rev = {
        (r["month"], r["territory_id"]): Decimal(r["premium_revenue"])
        for r in load_csv_as_list(data_dir / "subscription_revenue.csv")
    }
    ad_rev = {
        (r["month"], r["territory_id"]): Decimal(r["ad_revenue"])
        for r in load_csv_as_list(data_dir / "ad_revenue.csv")
    }

    # View events
    view_events = load_csv_as_list(data_dir / "view_events.csv")
    print(f"Loaded {len(titles)} titles, {len(licences)} licences, {len(view_events)} view events.")

    # 2. Instantiate Subsystems
    licence_mgr = LicenceManager(titles, licences, windows)
    windowing_svc = WindowingService(territories, licences, windows)
    view_proc = ViewProcessor(titles, view_events, windowing_svc)
    settlement_eng = RevenueSettlementEngine(
        territories, licensors, titles, title_splits, licences, windows, sub_rev, ad_rev
    )

    cmd_proc = CommandProcessor(licence_mgr, windowing_svc, view_proc, settlement_eng)

    # 3. Execute commands.txt
    commands_file = data_dir / "commands.txt"
    print(f"\nProcessing command stream: {commands_file}...")
    cmd_proc.execute_command_file(commands_file)

    # 4. Export Evaluation Deliverables
    print(f"\nExporting 4 evaluation CSV files to: {output_dir}...")
    cmd_proc.export_csv_outputs(output_dir)

    print("[SUCCESS] All commands processed and deliverables generated successfully.")
    print(f"  1. licence_validation.csv ({len(licence_mgr.validation_records)} rows)")
    print(f"  2. view_decisions.csv     ({len(view_proc.view_decisions)} rows)")
    print(f"  3. title_shares.csv       ({len(settlement_eng.all_title_shares)} rows)")
    print(f"  4. settlements.csv        ({len(settlement_eng.all_settlements)} rows)")


if __name__ == "__main__":
    local_sample_data = PROJECT_ROOT / "sample_data"
    download_sample_data = Path(r"C:\Users\kisho\Downloads\T019-PS-090-sample-data\T019-PS-090-sample-data")
    default_data_dir = local_sample_data if local_sample_data.exists() else download_sample_data
    default_output_dir = PROJECT_ROOT / "evaluation_outputs"

    data_dir_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else default_data_dir
    output_dir_arg = Path(sys.argv[2]) if len(sys.argv) > 2 else default_output_dir

    run_pipeline(data_dir_arg, output_dir_arg)
