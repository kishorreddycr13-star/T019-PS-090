"""
Reporting Service Module.
Generates readable command-line reports and tables for Rights Calendars,
Settlement Statements, and View Decisions (from database or in-memory state).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Union
from sqlalchemy.orm import Session

from repositories.payment_repository import PaymentRepository
from models.settlement import MonthlySettlement


class ReportingService:
    """Provides formatted reports and data access for rights calendars, settlements, and viewership."""

    def __init__(
        self,
        payment_repo: Optional[PaymentRepository] = None,
        session: Optional[Session] = None,
    ) -> None:
        self.payment_repo = payment_repo or PaymentRepository(session=session)

    @staticmethod
    def format_rights_calendar(
        title_id: str,
        rows: Sequence[Dict[str, Any]],
        title_name: str = "",
    ) -> str:
        """
        Formats the Rights Calendar for a given title.
        Includes Title ID, Licence ID, Territory, Window Start, Window End, Exclusivity, Status.
        """
        lines = []
        header = f"=== RIGHTS CALENDAR: {title_id} ==="
        if title_name:
            header += f" ({title_name})"
        lines.append(header)

        if not rows:
            lines.append("  No active windows found for this title.")
            return "\n".join(lines)

        lines.append("+------------+------------+-----------+------------+------------+---------------+--------+")
        lines.append("| Title ID   | Licence ID | Territory | Start Date | End Date   | Exclusivity   | Status |")
        lines.append("+------------+------------+-----------+------------+------------+---------------+--------+")

        for r in rows:
            lic_id = r.get("licence_id", "N/A")
            terr = r.get("territory_id", "N/A")
            w_start = str(r.get("window_start", "N/A"))
            w_end = str(r.get("window_end", "N/A"))
            excl = r.get("exclusivity", "N/A")
            status = r.get("status", "ACTIVE")
            lines.append(
                f"| {title_id:<10} | {lic_id:<10} | {terr:<9} | {w_start:<10} | {w_end:<10} | {excl:<13} | {status:<6} |"
            )

        lines.append("+------------+------------+-----------+------------+------------+---------------+--------+")
        return "\n".join(lines)

    @staticmethod
    def format_settlement_statement(
        licensor_id: str,
        period: str,
        records: Sequence[Union[Dict[str, Any], MonthlySettlement]],
    ) -> str:
        """
        Formats the Settlement Statement for a given licensor and period.
        Includes Month, Licensor ID, Licence ID, Gross share, MG paid, Recouped, Cap retained, TDS, Net payable, Status.
        """
        lines = []
        lines.append(f"=== SETTLEMENT STATEMENT: {licensor_id} [{period}] ===")

        if not records:
            lines.append("  No settlement records found for this period.")
            return "\n".join(lines)

        lines.append("+---------+-------------+------------+------------+----------+----------+----------+----------+------------+---------+")
        lines.append("| Month   | Licensor ID | Licence ID | Gross Rs   | MG Paid  | Recouped | Cap Ret  | TDS Rs   | Net Pay Rs | Status  |")
        lines.append("+---------+-------------+------------+------------+----------+----------+----------+----------+------------+---------+")

        tot_gross = 0.0
        tot_mg_paid = 0.0
        tot_recouped = 0.0
        tot_cap_ret = 0.0
        tot_tds = 0.0
        tot_net = 0.0

        for r in records:
            if isinstance(r, MonthlySettlement):
                month = r.period_key
                lic_id = r.contract_id
                gross = float(r.gross_royalty_amount)
                mg_p = float(r.mg_paid)
                rec = float(r.mg_recouped_amount)
                cap_r = float(r.cap_retained)
                tds = float(r.withholding_tax_amount)
                net = float(r.net_payable_amount)
                status = r.status
            else:
                month = r.get("month", period)
                lic_id = r.get("licence_id", "N/A")
                gross = float(r.get("gross_share", 0.0))
                mg_p = float(r.get("mg_paid", 0.0))
                rec = float(r.get("recouped", 0.0))
                cap_r = float(r.get("cap_retained", 0.0))
                tds = float(r.get("tds", 0.0))
                net = float(r.get("net_payable", 0.0))
                status = r.get("status", "SETTLED")

            tot_gross += gross
            tot_mg_paid += mg_p
            tot_recouped += rec
            tot_cap_ret += cap_r
            tot_tds += tds
            tot_net += net

            lines.append(
                f"| {month:<7} | {licensor_id:<11} | {lic_id:<10} | {gross:>10.2f} | {mg_p:>8.2f} | {rec:>8.2f} | {cap_r:>8.2f} | {tds:>8.2f} | {net:>10.2f} | {status:<7} |"
            )

        lines.append("+---------+-------------+------------+------------+----------+----------+----------+----------+------------+---------+")
        lines.append(
            f"| TOTAL   | {licensor_id:<11} |            | {tot_gross:>10.2f} | {tot_mg_paid:>8.2f} | {tot_recouped:>8.2f} | {tot_cap_ret:>8.2f} | {tot_tds:>8.2f} | {tot_net:>10.2f} |         |"
        )
        lines.append("+---------+-------------+------------+------------+----------+----------+----------+----------+------------+---------+")
        return "\n".join(lines)

    @staticmethod
    def format_view_decisions_report(
        from_date: str,
        to_date: str,
        decisions: Sequence[Dict[str, Any]],
        max_rows: int = 50,
    ) -> str:
        """
        Formats the View Decisions report for playback events between from_date and to_date.
        Includes View ID, Title ID, Decision, Reason, Local start, Qualifying, Counted, Settlement Month, Tag.
        """
        lines = []
        filtered = [
            d for d in decisions
            if from_date <= str(d.get("local_start", ""))[:10] <= to_date
        ]
        lines.append(f"=== VIEW DECISIONS REPORT [{from_date} to {to_date}] (Total: {len(filtered)} views) ===")

        if not filtered:
            lines.append("  No view events found in the specified date range.")
            return "\n".join(lines)

        lines.append("+-----------+----------+----------+-----------------+---------------------+-------+---------+------------+-----------+")
        lines.append("| View ID   | Title ID | Decision | Reason          | Local Start         | Qual? | Counted | Settle Mon | Tag       |")
        lines.append("+-----------+----------+----------+-----------------+---------------------+-------+---------+------------+-----------+")

        display_subset = filtered[:max_rows]
        for vd in display_subset:
            v_id = vd.get("view_id", "N/A")
            title_id = vd.get("_title_id", vd.get("title_id", "N/A"))
            dec = vd.get("decision", "N/A")
            reason = vd.get("reason", "")
            local_s = str(vd.get("local_start", "N/A"))
            qual = str(vd.get("qualifying", "false"))
            counted = str(vd.get("counted", "false"))
            s_month = vd.get("settlement_month", "N/A")
            tag = vd.get("tag", "")

            lines.append(
                f"| {v_id:<9} | {title_id:<8} | {dec:<8} | {reason:<15} | {local_s:<19} | {qual:<5} | {counted:<7} | {s_month:<10} | {tag:<9} |"
            )

        lines.append("+-----------+----------+----------+-----------------+---------------------+-------+---------+------------+-----------+")
        if len(filtered) > max_rows:
            lines.append(f"  ... showing first {max_rows} of {len(filtered)} records. Full list exported to view_decisions.csv.")

        return "\n".join(lines)
