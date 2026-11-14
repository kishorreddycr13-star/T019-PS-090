"""
Command Processor Module.
Parses commands.txt in strict sequential order, coordinates engine subsystems,
executes settlement validation and database persistence, and writes out the exact 4 evaluation CSV deliverables.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional, Any

from engine.licence_manager import LicenceManager
from engine.windowing_service import WindowingService
from engine.view_processor import ViewProcessor
from engine.revenue_settlement_engine import RevenueSettlementEngine
from services.settlement_service import SettlementService
from services.reporting_service import ReportingService


class CommandProcessor:
    """Executes the pipeline command stream and generates evaluation CSV outputs."""

    def __init__(
        self,
        licence_manager: LicenceManager,
        windowing_service: WindowingService,
        view_processor: ViewProcessor,
        settlement_engine: RevenueSettlementEngine,
        settlement_service: Optional[SettlementService] = None,
        reporting_service: Optional[ReportingService] = None,
    ) -> None:
        self.licence_manager = licence_manager
        self.windowing_service = windowing_service
        self.view_processor = view_processor
        self.settlement_engine = settlement_engine
        self.settlement_service = settlement_service or SettlementService(settlement_engine=self.settlement_engine)
        self.reporting_service = reporting_service or ReportingService()

    def execute_command_file(self, commands_path: str | Path) -> None:
        """Parses and executes commands.txt in strict file order."""
        path = Path(commands_path)
        with open(path, "r", encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split("|")
                cmd = parts[0].strip()
                args = [p.strip() for p in parts[1:]]

                if cmd == "CREATE_LICENCE":
                    lic_id = args[0]
                    self.licence_manager.create_licence(lic_id)

                elif cmd == "INGEST_VIEWS_UNTIL":
                    cutoff_utc = args[0]
                    self.view_processor.process_views_until(
                        cutoff_utc, self.licence_manager.accepted_licences
                    )

                elif cmd == "SETTLE":
                    settle_month = args[0]
                    run_ts = args[1] if len(args) > 1 else ""

                    # Execute settlement workflow with BR-12 validation & DB persistence
                    self.settlement_service.settle_month(
                        month=settle_month,
                        run_ts=run_ts,
                        view_decisions=self.view_processor.view_decisions,
                        accepted_licences=self.licence_manager.accepted_licences,
                        allow_rerun=True,  # Allows pipeline re-runs
                        persist_db=True,
                    )

                    # Determine next month for late view tagging
                    next_m_str = SettlementService.get_next_settlement_month(settle_month)
                    self.view_processor.mark_month_settled(settle_month, next_m_str)

                elif cmd == "PRINT_RIGHTS_CALENDAR":
                    title_id = args[0]
                    rows = self.windowing_service.get_rights_calendar_rows(
                        title_id, self.licence_manager.accepted_licences
                    )
                    print(f"--- RIGHTS CALENDAR: {title_id} ---")
                    for r in rows:
                        print(
                            f"  {r['territory_id']} | {r['licence_id']} | "
                            f"Win #{r['window_no']} | {r['window_start']} to {r['window_end']} | "
                            f"{r['exclusivity']}"
                        )

                elif cmd == "PRINT_SETTLEMENT":
                    licensor_id = args[0]
                    period = args[1]
                    matches = [
                        s for s in self.settlement_engine.all_settlements
                        if s["licensor_id"] == licensor_id and s["month"] == period
                    ]
                    print(f"--- SETTLEMENT: {licensor_id} [{period}] ---")
                    for m in matches:
                        print(
                            f"  Licence: {m['licence_id']} | Gross: Rs {m['gross_share']} | "
                            f"Recouped: Rs {m['recouped']} | Cap Retained: Rs {m['cap_retained']} | "
                            f"TDS: Rs {m['tds']} ({m['tds_pct']}%) | Net: Rs {m['net_payable']} | "
                            f"Status: {m['status']}"
                        )

                elif cmd == "PRINT_VIEW_DECISIONS":
                    from_date = args[0]
                    to_date = args[1]
                    matches = [
                        vd for vd in self.view_processor.view_decisions
                        if from_date <= vd["local_start"][:10] <= to_date
                    ]
                    print(f"--- VIEW DECISIONS [{from_date} to {to_date}]: {len(matches)} views ---")

    def export_csv_outputs(self, output_dir: str | Path) -> None:
        """Writes out the 4 evaluation CSV files with exact headers and conventions."""
        SettlementService.export_evaluation_outputs(
            output_dir=output_dir,
            licence_validations=self.licence_manager.validation_records,
            view_decisions=self.view_processor.view_decisions,
            title_shares=self.settlement_engine.all_title_shares,
            settlements=self.settlement_engine.all_settlements,
        )
