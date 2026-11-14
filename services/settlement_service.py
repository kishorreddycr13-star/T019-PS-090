"""
Monthly Settlement and Reporting Service Module.
Implements BR-12 (Settlement Timing & Cutoffs), 18-step Monthly Settlement Workflow,
Database Persistence with Transaction Rollbacks, Idempotency Checks, and CSV Export.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from sqlalchemy.orm import Session

from database.connection import get_db_session
from models.settlement import MonthlySettlement, PaymentTransaction
from models.audit import AuditLog
from repositories.payment_repository import PaymentRepository
from engine.revenue_settlement_engine import RevenueSettlementEngine
from validators.exceptions import SettlementTimingError, DuplicateSettlementError


class SettlementService:
    """Orchestrates monthly settlement timing, execution, database persistence, and evaluation outputs."""

    def __init__(
        self,
        settlement_engine: Optional[RevenueSettlementEngine] = None,
        data_dir: Optional[Union[str, Path]] = None,
        session: Optional[Session] = None,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "sample_data"
        self.settlement_engine = settlement_engine
        self._session = session
        self.payment_repo = PaymentRepository(session=session, data_dir=self.data_dir)

        # In-memory history of executed settlement periods
        self.executed_settlement_months: Set[str] = set()
        self.settlement_history: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def get_earliest_permitted_timestamp(month: str) -> str:
        """
        Calculates the earliest allowable settlement timestamp for a given month (BR-12).
        Settlement for month M is permitted on the 10th of M+1 at 00:00:00 UTC.
        Example: '2026-07' -> '2026-08-10 00:00:00'
        """
        parts = month.strip().split("-")
        if len(parts) != 2:
            raise ValueError(f"Invalid month format '{month}'. Expected YYYY-MM.")
        y, m = int(parts[0]), int(parts[1])
        if m == 12:
            next_y, next_m = y + 1, 1
        else:
            next_y, next_m = y, m + 1
        return f"{next_y:04d}-{next_m:02d}-10 00:00:00"

    @staticmethod
    def get_next_settlement_month(month: str) -> str:
        """Computes next calendar month in 'YYYY-MM' format."""
        y, m = map(int, month.strip().split("-"))
        if m == 12:
            return f"{y + 1:04d}-01"
        return f"{y:04d}-{m + 1:02d}"

    def validate_settlement_timing(self, month: str, run_ts: str) -> None:
        """
        Validates whether the settlement execution timestamp satisfies the BR-12 timing rule.
        Raises SettlementTimingError if run_ts is earlier than the 10th of M+1.
        """
        if not run_ts:
            return

        earliest_permitted_str = self.get_earliest_permitted_timestamp(month)
        run_dt = datetime.strptime(run_ts.strip(), "%Y-%m-%d %H:%M:%S")
        earliest_dt = datetime.strptime(earliest_permitted_str, "%Y-%m-%d %H:%M:%S")

        if run_dt < earliest_dt:
            raise SettlementTimingError(
                f"Settlement for month '{month}' cannot be run before {earliest_permitted_str}. "
                f"Attempted execution at: {run_ts}.",
                month=month,
                run_ts=run_ts,
                earliest_permitted=earliest_permitted_str,
            )

    def is_month_settled(self, month: str, check_db: bool = True) -> bool:
        """Checks if a settlement has already been completed for the specified period."""
        if month in self.executed_settlement_months:
            return True
        if check_db:
            existing = self.payment_repo.query_settlements(month=month)
            return len(existing) > 0
        return False

    def settle_month(
        self,
        month: str,
        run_ts: str,
        view_decisions: List[Dict[str, Any]],
        accepted_licences: List[str],
        allow_rerun: bool = False,
        persist_db: bool = True,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Executes the monthly settlement sequence:
        1. Validates settlement run timestamp (BR-12).
        2. Enforces idempotency (prevents duplicate runs unless allow_rerun=True).
        3. Computes subscription and ad pools, title shares, and partner settlements.
        4. Persists records to database inside an atomic transaction with audit logging.
        5. Returns (title_shares, settlements).
        """
        # Step 1: Validate settlement timing
        self.validate_settlement_timing(month, run_ts)

        # Step 2: Enforce duplicate settlement prevention
        if not allow_rerun and self.is_month_settled(month, check_db=persist_db):
            raise DuplicateSettlementError(
                f"Settlement for period '{month}' has already been finalized and locked.",
                month=month,
                run_id=f"RUN-{month}",
            )

        if not self.settlement_engine:
            raise RuntimeError("SettlementService has no active RevenueSettlementEngine instance.")

        # Step 3: Execute calculations via RevenueSettlementEngine
        title_shares, settlements = self.settlement_engine.settle_month(
            month=month,
            view_decisions=view_decisions,
            accepted_licences=accepted_licences,
        )

        # Step 4: Persist to database with transaction rollback handling
        if persist_db:
            self._persist_settlement_transaction(
                month=month,
                run_ts=run_ts,
                settlements=settlements,
            )

        # Step 5: Update state history
        self.executed_settlement_months.add(month)
        self.settlement_history[month] = {
            "run_ts": run_ts,
            "title_shares_count": len(title_shares),
            "settlements_count": len(settlements),
            "settled_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }

        return title_shares, settlements

    def _persist_settlement_transaction(
        self,
        month: str,
        run_ts: str,
        settlements: List[Dict[str, Any]],
    ) -> None:
        """
        Persists MonthlySettlement entities and AuditLog entries within an atomic database transaction.
        If any database operation fails, rolls back completely to prevent partial state.
        """
        def _execute_save(session: Session) -> None:
            run_number = f"RUN-{month}"
            # 1. Upsert settlement rows
            for s in settlements:
                cid = s["licence_id"]
                lid = s["licensor_id"]
                existing = session.query(MonthlySettlement).filter_by(
                    settlement_run_number=run_number,
                    contract_id=cid,
                    licensor_id=lid,
                ).first()

                s_id = existing.settlement_id if existing else f"SETTLE-{month}-{cid}-{lid}"
                entity = MonthlySettlement(
                    settlement_id=s_id,
                    settlement_run_number=run_number,
                    period_key=s["month"],
                    contract_id=cid,
                    licensor_id=lid,
                    gross_royalty_amount=Decimal(s["gross_share"]),
                    split_pct=Decimal(s["split_pct"]),
                    mg_paid=Decimal(s["mg_paid"]),
                    mg_recouped_amount=Decimal(s["recouped"]),
                    mg_balance=Decimal(s["mg_balance"]),
                    cap_retained=Decimal(s["cap_retained"]),
                    payable_before_tds=Decimal(s["payable_before_tds"]),
                    tds_pct=Decimal(s["tds_pct"]),
                    withholding_tax_amount=Decimal(s["tds"]),
                    net_payable_amount=Decimal(s["net_payable"]),
                    status=s["status"],
                )
                session.merge(entity)

            # 2. Add tamper-evident AuditLog entry
            audit_entry = AuditLog(
                table_name="monthly_settlements",
                record_id=run_number,
                action="SETTLEMENT_LOCK",
                performed_by="SETTLEMENT_SERVICE",
                new_values_json=json.dumps({
                    "month": month,
                    "run_ts": run_ts,
                    "settlements_count": len(settlements),
                    "total_net_payable": str(sum(Decimal(s["net_payable"]) for s in settlements)),
                }),
            )
            session.add(audit_entry)
            session.flush()

        if self._session:
            _execute_save(self._session)
        else:
            with get_db_session() as session:
                try:
                    _execute_save(session)
                    session.commit()
                except Exception:
                    session.rollback()
                    raise

    @staticmethod
    def export_evaluation_outputs(
        output_dir: Union[str, Path],
        licence_validations: List[Dict[str, Any]],
        view_decisions: List[Dict[str, Any]],
        title_shares: List[Dict[str, Any]],
        settlements: List[Dict[str, Any]],
    ) -> None:
        """
        Generates the exact four evaluation CSV files required by PS-090 specification:
        1. licence_validation.csv
        2. view_decisions.csv
        3. title_shares.csv
        4. settlements.csv
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # 1. licence_validation.csv
        with open(out_path / "licence_validation.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["licence_id", "result", "reason", "conflicting_licence_id"])
            for r in licence_validations:
                w.writerow([r.get("licence_id", ""), r.get("result", ""), r.get("reason", ""), r.get("conflicting_licence_id", "")])

        # 2. view_decisions.csv
        with open(out_path / "view_decisions.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "view_id", "decision", "reason", "licence_id", "local_start",
                "settlement_month", "qualifying", "counted", "view_hours", "tag"
            ])
            for vd in view_decisions:
                w.writerow([
                    vd.get("view_id", ""), vd.get("decision", ""), vd.get("reason", ""),
                    vd.get("licence_id", ""), vd.get("local_start", ""), vd.get("settlement_month", ""),
                    vd.get("qualifying", ""), vd.get("counted", ""), vd.get("view_hours", ""),
                    vd.get("tag", "")
                ])

        # 3. title_shares.csv
        with open(out_path / "title_shares.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "month", "territory_id", "title_id", "premium_view_hours", "pool_ratio",
                "pool_share", "ad_impressions", "ad_ratio", "ad_share", "title_share"
            ])
            for ts in title_shares:
                w.writerow([
                    ts.get("month", ""), ts.get("territory_id", ""), ts.get("title_id", ""),
                    ts.get("premium_view_hours", ""), ts.get("pool_ratio", ""), ts.get("pool_share", ""),
                    ts.get("ad_impressions", ""), ts.get("ad_ratio", ""), ts.get("ad_share", ""),
                    ts.get("title_share", "")
                ])

        # 4. settlements.csv
        with open(out_path / "settlements.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "month", "licence_id", "licensor_id", "split_pct", "gross_share", "mg_paid",
                "recouped", "mg_balance", "cap_retained", "payable_before_tds", "tds_pct",
                "tds", "net_payable", "status"
            ])
            for s in settlements:
                w.writerow([
                    s.get("month", ""), s.get("licence_id", ""), s.get("licensor_id", ""),
                    s.get("split_pct", ""), s.get("gross_share", ""), s.get("mg_paid", ""),
                    s.get("recouped", ""), s.get("mg_balance", ""), s.get("cap_retained", ""),
                    s.get("payable_before_tds", ""), s.get("tds_pct", ""), s.get("tds", ""),
                    s.get("net_payable", ""), s.get("status", "")
                ])
