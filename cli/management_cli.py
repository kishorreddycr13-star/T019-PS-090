"""
Management CLI Module.
Command-line interface for Title, Licensor, and Licence Contract administration.
Provides structured commands, tabular displays, and detailed error handling.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.title_service import TitleService
from services.licensor_service import LicensorService
from services.licence_service import LicenceService
from services.reporting_service import ReportingService
from services.settlement_service import SettlementService
from validators.exceptions import (
    ManagementEngineError,
    EntityNotFoundError,
    ValidationError,
    SplitValidationError,
    HoldbackViolationError,
    ExclusivityConflictError,
    SettlementTimingError,
    DuplicateSettlementError,
)


def _format_table(headers: List[str], rows: List[List[Any]]) -> str:
    """Renders a clean ASCII table."""
    if not rows:
        return "(no records found)"

    str_rows = [[str(cell if cell is not None else "") for cell in row] for row in rows]
    col_widths = [len(h) for h in headers]
    for row in str_rows:
        for idx, cell in enumerate(row):
            if idx < len(col_widths):
                col_widths[idx] = max(col_widths[idx], len(cell))

    separator = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_line = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |"
    
    lines = [separator, header_line, separator]
    for row in str_rows:
        row_line = "| " + " | ".join(c.ljust(w) for c, w in zip(row, col_widths)) + " |"
        lines.append(row_line)
    lines.append(separator)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI Handlers
# ---------------------------------------------------------------------------

def handle_title_register(args: argparse.Namespace) -> int:
    service = TitleService()
    rel_date = date.fromisoformat(args.release_date) if args.release_date else None
    theat_date = date.fromisoformat(args.theatrical_premiere) if args.theatrical_premiere else None
    tv_date = date.fromisoformat(args.tv_premiere) if args.tv_premiere else None

    title = service.register_title(
        title_id=args.title_id,
        title_name=args.title_name,
        runtime_seconds=args.runtime,
        content_type=args.category,
        release_date=rel_date,
        theatrical_premiere=theat_date,
        tv_premiere=tv_date,
    )
    print(f"\n[SUCCESS] Title registered successfully.")
    print(_format_table(
        ["Field", "Value"],
        [
            ["Title ID", title.title_id],
            ["Name", title.title_name],
            ["Category", title.content_type],
            ["Runtime", f"{title.duration_seconds} sec ({round(title.duration_seconds/60, 1)} min)"],
            ["Release Date", title.release_date or "N/A"],
            ["Theatrical Premiere", title.theatrical_premiere or "N/A"],
            ["TV Premiere", title.tv_premiere or "N/A"],
        ]
    ))
    return 0


def handle_title_get(args: argparse.Namespace) -> int:
    service = TitleService()
    title = service.get_title(args.title_id)
    print(f"\n[TITLE DETAILS]")
    print(_format_table(
        ["Field", "Value"],
        [
            ["Title ID", title.title_id],
            ["Name", title.title_name],
            ["Category", title.content_type],
            ["Runtime", f"{title.duration_seconds} sec"],
            ["Release Date", title.release_date or "N/A"],
            ["Theatrical Premiere", title.theatrical_premiere or "N/A"],
            ["TV Premiere", title.tv_premiere or "N/A"],
            ["Active", "Yes" if title.is_active else "No"],
        ]
    ))
    if title.splits:
        print(f"\nCo-Licensor Splits ({len(title.splits)} licensors):")
        split_rows = [
            [s.licensor_id, f"{s.split_percentage:.2f}%", s.effective_from or "N/A", s.effective_to or "N/A"]
            for s in title.splits
        ]
        print(_format_table(["Licensor ID", "Split %", "Effective From", "Effective To"], split_rows))
    return 0


def handle_title_update(args: argparse.Namespace) -> int:
    service = TitleService()
    rel_date = date.fromisoformat(args.release_date) if args.release_date else None
    theat_date = date.fromisoformat(args.theatrical_premiere) if args.theatrical_premiere else None
    tv_date = date.fromisoformat(args.tv_premiere) if args.tv_premiere else None

    title = service.update_title(
        title_id=args.title_id,
        title_name=args.title_name,
        runtime_seconds=args.runtime,
        content_type=args.category,
        release_date=rel_date,
        theatrical_premiere=theat_date,
        tv_premiere=tv_date,
    )
    print(f"\n[SUCCESS] Title '{title.title_id}' updated successfully.")
    return 0


def handle_title_delete(args: argparse.Namespace) -> int:
    service = TitleService()
    service.delete_title(args.title_id)
    print(f"\n[SUCCESS] Title '{args.title_id}' deleted successfully.")
    return 0


def handle_title_search(args: argparse.Namespace) -> int:
    service = TitleService()
    results = service.search_titles(query=args.query, content_type=args.category)
    print(f"\nSearch Results ({len(results)} titles found):")
    rows = [
        [t.title_id, t.title_name, t.content_type, f"{t.duration_seconds}s", t.theatrical_premiere or "-", t.tv_premiere or "-"]
        for t in results
    ]
    print(_format_table(["Title ID", "Title Name", "Category", "Runtime", "Theatrical", "TV"], rows))
    return 0


def handle_title_splits_set(args: argparse.Namespace) -> int:
    service = TitleService()
    # Format expected: "LIC01:60.00,LIC02:40.00"
    raw_splits = args.splits.split(",")
    splits_payload = []
    for s_entry in raw_splits:
        parts = s_entry.strip().split(":")
        if len(parts) != 2:
            raise ValidationError(f"Invalid split specification '{s_entry}'. Expected format: LICENSOR_ID:PERCENTAGE")
        splits_payload.append({
            "licensor_id": parts[0].strip(),
            "split_percentage": Decimal(parts[1].strip()),
        })

    saved = service.register_title_splits(args.title_id, splits_payload)
    print(f"\n[SUCCESS] Registered {len(saved)} co-licensor splits for Title '{args.title_id}' (Total: 100.00%).")
    rows = [[s.licensor_id, f"{s.split_percentage:.2f}%"] for s in saved]
    print(_format_table(["Licensor ID", "Split %"], rows))
    return 0


def handle_title_splits_get(args: argparse.Namespace) -> int:
    service = TitleService()
    splits = service.get_title_splits(args.title_id)
    print(f"\nCo-Licensor Splits for Title '{args.title_id}':")
    rows = [[s.licensor_id, f"{s.split_percentage:.2f}%"] for s in splits]
    print(_format_table(["Licensor ID", "Split %"], rows))
    return 0


def handle_licensor_register(args: argparse.Namespace) -> int:
    service = LicensorService()
    tds = Decimal(args.treaty_tds) if args.treaty_tds else None
    lic = service.register_licensor(
        licensor_name=args.name,
        country=args.country,
        licensor_id=args.licensor_id,
        country_code=args.country_code,
        is_indian=args.is_indian,
        treaty_tds_pct=tds,
        trade_name=args.trade_name,
    )
    print(f"\n[SUCCESS] Licensor registered successfully.")
    print(_format_table(
        ["Field", "Value"],
        [
            ["Licensor ID", lic.licensor_id],
            ["Legal Name", lic.legal_name],
            ["Country", f"{lic.country} ({lic.country_code})"],
            ["Indian Resident", "Yes" if lic.is_indian else "No"],
            ["Treaty TDS %", f"{lic.treaty_tds_pct}%" if lic.treaty_tds_pct is not None else "None (Statutory)"],
        ]
    ))
    return 0


def handle_licensor_get(args: argparse.Namespace) -> int:
    service = LicensorService()
    lic = service.get_licensor(args.licensor_id)
    print(f"\n[LICENSOR DETAILS]")
    print(_format_table(
        ["Field", "Value"],
        [
            ["Licensor ID", lic.licensor_id],
            ["Legal Name", lic.legal_name],
            ["Trade Name", lic.trade_name or "N/A"],
            ["Country", f"{lic.country} ({lic.country_code})"],
            ["Indian Resident", "Yes" if lic.is_indian else "No"],
            ["Treaty TDS %", f"{lic.treaty_tds_pct}%" if lic.treaty_tds_pct is not None else "None"],
            ["Currency", lic.settlement_currency],
            ["Active", "Yes" if lic.is_active else "No"],
        ]
    ))
    return 0


def handle_licensor_update(args: argparse.Namespace) -> int:
    service = LicensorService()
    tds = Decimal(args.treaty_tds) if args.treaty_tds else None
    lic = service.update_licensor(
        licensor_id=args.licensor_id,
        licensor_name=args.name,
        country=args.country,
        country_code=args.country_code,
        is_indian=args.is_indian,
        treaty_tds_pct=tds,
        trade_name=args.trade_name,
    )
    print(f"\n[SUCCESS] Licensor '{lic.licensor_id}' updated successfully.")
    return 0


def handle_licensor_delete(args: argparse.Namespace) -> int:
    service = LicensorService()
    service.delete_licensor(args.licensor_id)
    print(f"\n[SUCCESS] Licensor '{args.licensor_id}' deleted successfully.")
    return 0


def handle_licensor_search(args: argparse.Namespace) -> int:
    service = LicensorService()
    results = service.search_licensors(query=args.query, country=args.country, is_indian=args.is_indian)
    print(f"\nSearch Results ({len(results)} licensors found):")
    rows = [
        [l.licensor_id, l.legal_name, l.country, "IN" if l.is_indian else "Foreign", f"{l.treaty_tds_pct or '-'}%"]
        for l in results
    ]
    print(_format_table(["Licensor ID", "Legal Name", "Country", "Residency", "Treaty TDS"], rows))
    return 0


def handle_licensor_list(args: argparse.Namespace) -> int:
    service = LicensorService()
    results = service.list_licensors()
    print(f"\nAll Licensors ({len(results)} total):")
    rows = [
        [l.licensor_id, l.legal_name, l.country, "IN" if l.is_indian else "Foreign", f"{l.treaty_tds_pct or '-'}%"]
        for l in results
    ]
    print(_format_table(["Licensor ID", "Legal Name", "Country", "Residency", "Treaty TDS"], rows))
    return 0


def handle_licence_create(args: argparse.Namespace) -> int:
    service = LicenceService()
    
    # Windows parsing: "2026-05-01:2026-08-31,2026-10-01:2026-12-31"
    raw_windows = args.windows.split(",")
    windows_payload = []
    for idx, w_entry in enumerate(raw_windows, start=1):
        parts = w_entry.strip().split(":")
        if len(parts) != 2:
            raise ValidationError(f"Invalid window format '{w_entry}'. Expected: START_DATE:END_DATE (e.g. 2026-05-01:2026-08-31)")
        windows_payload.append({
            "window_no": idx,
            "window_start": parts[0].strip(),
            "window_end": parts[1].strip(),
            "window_type": "SVOD",
        })

    mg_amt = Decimal(args.mg) if args.mg else Decimal("0.00")
    cap_amt = Decimal(args.cap) if args.cap else Decimal("0.00")

    lic = service.create_licence(
        licence_id=args.licence_id,
        title_id=args.title_id,
        licensor_id=args.licensor_id,
        territory_id=args.territory,
        exclusivity=args.exclusivity,
        revenue_share_type=args.rev_share_type,
        mg_amount=mg_amt,
        cap_amount=cap_amt,
        windows=windows_payload,
    )
    print(f"\n[SUCCESS] Licence contract created successfully.")
    print(_format_table(
        ["Field", "Value"],
        [
            ["Licence ID", lic.contract_id],
            ["Title ID", lic.title_id],
            ["Licensor ID", lic.licensor_id],
            ["Territory", lic.territory_id],
            ["Exclusivity", lic.exclusivity],
            ["Rev-Share Type", lic.revenue_share_type],
            ["MG Amount", f"${lic.mg_amount:,.2f}"],
            ["Cap Amount", f"${lic.cap_amount:,.2f}"],
            ["Status", lic.status],
        ]
    ))
    print(f"\nLicence Windows ({len(lic.windows)} windows):")
    w_rows = [[w.window_no, w.window_type, str(w.window_start), str(w.window_end), w.exclusivity] for w in lic.windows]
    print(_format_table(["Window #", "Type", "Start Date", "End Date", "Exclusivity"], w_rows))
    return 0


def handle_licence_get(args: argparse.Namespace) -> int:
    service = LicenceService()
    lic = service.get_licence(args.licence_id)
    print(f"\n[LICENCE CONTRACT DETAILS]")
    print(_format_table(
        ["Field", "Value"],
        [
            ["Licence ID", lic.contract_id],
            ["Contract #", lic.contract_number],
            ["Title", f"{lic.title.title_name} ({lic.title_id})" if lic.title else lic.title_id],
            ["Licensor", f"{lic.primary_licensor.legal_name} ({lic.licensor_id})" if lic.primary_licensor else lic.licensor_id],
            ["Territory", lic.territory_id],
            ["Exclusivity", lic.exclusivity],
            ["Rev-Share Model", lic.revenue_share_type],
            ["MG Advance", f"${lic.mg_amount:,.2f}"],
            ["Payment Cap", f"${lic.cap_amount:,.2f}"],
            ["Effective Range", f"{lic.effective_date} to {lic.expiration_date}"],
            ["Status", lic.status],
        ]
    ))
    print(f"\nAvailability Windows ({len(lic.windows)} total):")
    w_rows = [[w.window_no, w.window_type, str(w.window_start), str(w.window_end), w.exclusivity, w.status] for w in lic.windows]
    print(_format_table(["Window #", "Type", "Start Date", "End Date", "Exclusivity", "Status"], w_rows))
    return 0


def handle_licence_update(args: argparse.Namespace) -> int:
    service = LicenceService()
    mg_amt = Decimal(args.mg) if args.mg else None
    cap_amt = Decimal(args.cap) if args.cap else None

    lic = service.update_licence(
        licence_id=args.licence_id,
        territory_id=args.territory,
        exclusivity=args.exclusivity,
        revenue_share_type=args.rev_share_type,
        mg_amount=mg_amt,
        cap_amount=cap_amt,
        status=args.status,
    )
    print(f"\n[SUCCESS] Licence '{lic.contract_id}' updated successfully.")
    return 0


def handle_licence_add_window(args: argparse.Namespace) -> int:
    service = LicenceService()
    win = service.add_window(
        licence_id=args.licence_id,
        window_start=args.start,
        window_end=args.end,
        window_no=args.window_no,
        window_type=args.window_type or "SVOD",
    )
    print(f"\n[SUCCESS] Added window #{win.window_no} ({win.window_start} to {win.window_end}) to Licence '{args.licence_id}'.")
    return 0


def handle_licence_delete(args: argparse.Namespace) -> int:
    service = LicenceService()
    service.delete_licence(args.licence_id)
    print(f"\n[SUCCESS] Licence '{args.licence_id}' deleted successfully.")
    return 0


def handle_licence_search(args: argparse.Namespace) -> int:
    service = LicenceService()
    results = service.search_licences(
        title_id=args.title_id,
        territory_id=args.territory,
        licensor_id=args.licensor_id,
        exclusivity=args.exclusivity,
        status=args.status,
        query=args.query,
    )
    print(f"\nLicence Search Results ({len(results)} found):")
    rows = [
        [
            l.contract_id,
            l.title_id,
            l.licensor_id,
            l.territory_id,
            l.exclusivity,
            l.revenue_share_type,
            f"${l.mg_amount:,.2f}",
            f"${l.cap_amount:,.2f}",
            l.status,
        ]
        for l in results
    ]
    print(_format_table(
        ["Licence ID", "Title", "Licensor", "Territory", "Exclusivity", "Rev Type", "MG", "Cap", "Status"],
        rows
    ))
    return 0


def handle_licence_audit(args: argparse.Namespace) -> int:
    service = LicenceService()
    logs = service.get_audit_logs(licence_id=args.licence_id, limit=args.limit)
    print(f"\nLicence Audit Trail ({len(logs)} records):")
    rows = [
        [l.log_id[:8] + "...", l.record_id, l.action, l.performed_by, str(l.created_at_utc)[:19]]
        for l in logs
    ]
    print(_format_table(["Log ID", "Licence ID", "Action", "Performed By", "Timestamp (UTC)"], rows))
    return 0


def handle_playback_check(args: argparse.Namespace) -> int:
    from services.playback_service import PlaybackService, PlaybackRequest
    service = PlaybackService()
    req = PlaybackRequest(
        title_id=args.title_id,
        subscriber_id=args.subscriber_id or "SUB-CLI-001",
        tier=args.tier or "PREMIUM",
        territory_id=args.territory,
        playback_timestamp_utc=args.start_utc,
        watch_seconds=args.watch_seconds or 3600,
    )
    decision = service.record_playback(req, persist_to_db=args.record)
    print(f"\n[PLAYBACK DECISION: {decision.decision}]")
    print(_format_table(
        ["Field", "Value"],
        [
            ["Decision ID", decision.decision_id],
            ["Decision", decision.decision],
            ["Reason", decision.reason or "None (Authorized)"],
            ["Licence ID", decision.licence_id or "N/A"],
            ["Title ID", decision.title_id],
            ["Territory", decision.territory_id],
            ["Playback UTC", str(decision.playback_start_utc)],
            ["Local Time", decision.local_start_str],
            ["Watch Seconds", f"{decision.watch_seconds}s (effective: {decision.effective_watch_seconds}s)"],
            ["Message", decision.message],
        ]
    ))
    return 0 if decision.is_allowed else 1


def handle_playback_history(args: argparse.Namespace) -> int:
    from services.playback_service import PlaybackService
    service = PlaybackService()
    history = service.get_playback_history(
        subscriber_id=args.subscriber_id,
        title_id=args.title_id,
        limit=args.limit,
    )
    print(f"\nPlayback Decision History ({len(history)} records):")
    rows = [
        [
            d.decision_id[:12] + "...",
            d.decision,
            d.title_id,
            d.territory_id,
            d.licence_id or "-",
            d.local_start_str,
            f"{d.effective_watch_seconds}s",
        ]
        for d in history
    ]
    print(_format_table(
        ["Decision ID", "Decision", "Title", "Territory", "Licence", "Local Start", "Watch Time"],
        rows
    ))
    return 0


def handle_metering_summary(args: argparse.Namespace) -> int:
    import csv
    from services.metering_service import MeteringService
    from repositories.metering_repository import MeteringRepository

    output_dir = PROJECT_ROOT / "evaluation_outputs"
    view_dec_path = output_dir / "view_decisions.csv"
    sample_file = PROJECT_ROOT / "sample_data" / "view_events.csv"

    records = []
    if sample_file.exists():
        # Load views from view_events and evaluate via MeteringService
        service = MeteringService()
        with open(sample_file, "r", encoding="utf-8") as f:
            events = list(csv.DictReader(f))
        records = service.process_views_batch(events)
        repo = MeteringRepository()
        metrics = repo.aggregate_metrics_from_records(
            records, month=args.month, territory_id=args.territory, title_id=args.title_id
        )
    else:
        repo = MeteringRepository()
        metrics = repo.aggregate_metrics_from_db(
            period_key=args.month, territory_code=args.territory, title_id=args.title_id
        )

    print(f"\n[METERING SUMMARY REPORT] ({len(metrics)} aggregates)")
    rows = [
        [
            m["month"],
            m["territory_id"],
            m["title_id"],
            m["total_views"],
            m["qualifying_views"],
            m["qualifying_premium_views"],
            m["qualifying_free_views"],
            f"{m['premium_view_hours']:.4f}",
            m["free_ad_impressions"],
        ]
        for m in metrics[:100]
    ]
    print(_format_table(
        ["Month", "Territory", "Title ID", "Total Views", "Qualifying", "Prem Views", "Free Views", "Prem View-Hours", "Free Ad Impr"],
        rows
    ))
    return 0


def handle_metering_view_check(args: argparse.Namespace) -> int:
    import csv
    from services.metering_service import MeteringService

    service = MeteringService()
    target_view_id = args.view_id.strip()

    sample_file = PROJECT_ROOT / "sample_data" / "view_events.csv"
    matched_event = None
    if sample_file.exists():
        with open(sample_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["view_id"] == target_view_id:
                    matched_event = row
                    break

    if not matched_event:
        print(f"\n[ERROR] View event '{target_view_id}' not found in view events dataset.", file=sys.stderr)
        return 1

    result = service.process_view_event(matched_event)
    print(f"\n[VIEW METERING & QUALIFICATION BREAKDOWN]")
    print(_format_table(
        ["Field", "Value"],
        [
            ["View ID", result["view_id"]],
            ["Title ID", result["_title_id"]],
            ["Subscriber ID", result["_subscriber_id"]],
            ["Tier", result["_tier"]],
            ["Territory", result["_territory_id"]],
            ["Local Start", result["local_start"]],
            ["Settlement Month", result["settlement_month"]],
            ["Runtime / Threshold", f"{result['_runtime_seconds']}s / {result['_threshold_seconds']}s"],
            ["Watch Seconds", f"{result['_watch_seconds']}s"],
            ["Playback Decision", result["decision"]],
            ["Denial Reason", result["reason"] or "N/A (Authorized)"],
            ["Matched Licence", result["licence_id"] or "N/A"],
            ["Qualifying?", result["qualifying"]],
            ["Counted? (BR-08)", result["counted"]],
            ["View Hours", result["view_hours"]],
            ["Ad Impressions", str(result["_ad_impressions"])],
            ["Operational Tag", result["tag"] or "NONE"],
        ]
    ))
    return 0


def handle_revenue_title_shares(args: argparse.Namespace) -> int:
    import csv
    from services.revenue_service import RevenueService
    from services.metering_service import MeteringService

    output_dir = PROJECT_ROOT / "evaluation_outputs"
    shares_path = output_dir / "title_shares.csv"
    rows_data = []

    if shares_path.exists():
        with open(shares_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if args.month and r["month"] != args.month.strip():
                    continue
                if args.territory and r["territory_id"] != args.territory.strip():
                    continue
                if args.title_id and r["title_id"] != args.title_id.strip():
                    continue
                rows_data.append(r)
    else:
        # Calculate dynamically using RevenueService
        rev_service = RevenueService()
        met_service = MeteringService()
        sample_file = PROJECT_ROOT / "sample_data" / "view_events.csv"
        events = []
        if sample_file.exists():
            with open(sample_file, "r", encoding="utf-8") as f:
                events = list(csv.DictReader(f))
        view_decisions = met_service.process_views_batch(events)
        target_month = args.month or "2026-07"
        all_shares = rev_service.calculate_monthly_title_shares(target_month, view_decisions)
        for r in all_shares:
            if args.territory and r["territory_id"] != args.territory.strip():
                continue
            if args.title_id and r["title_id"] != args.title_id.strip():
                continue
            rows_data.append(r)

    print(f"\n[TITLE SHARES REVENUE REPORT] ({len(rows_data)} records)")
    table_rows = [
        [
            r["month"],
            r["territory_id"],
            r["title_id"],
            r["premium_view_hours"],
            r["pool_ratio"],
            f"Rs {Decimal(r['pool_share']):,.2f}",
            r["ad_impressions"],
            r["ad_ratio"],
            f"Rs {Decimal(r['ad_share']):,.2f}",
            f"Rs {Decimal(r['title_share']):,.2f}",
        ]
        for r in rows_data[:100]
    ]
    print(_format_table(
        ["Month", "Territory", "Title ID", "Prem Hours", "Pool Ratio", "Pool Share", "Ad Impr", "Ad Ratio", "Ad Share", "Title Share"],
        table_rows
    ))
    return 0


def handle_revenue_summary(args: argparse.Namespace) -> int:
    from services.revenue_service import RevenueService
    service = RevenueService()
    month = args.month or "2026-07"
    territory = args.territory

    territories_to_show = [territory] if territory else sorted(service.territories.keys())
    print(f"\n[TERRITORY REVENUE POOLS SUMMARY - {month}]")

    summary_rows = []
    for t_id in territories_to_show:
        prem_rev = service.subscription_revenues.get((month, t_id), Decimal("0.00"))
        sub_pool = service.sub_calc.calculate_subscription_pool(prem_rev)
        ad_rev = service.ad_revenues.get((month, t_id), Decimal("0.00"))
        ad_pool = service.ad_calc.calculate_ad_pool(ad_rev)
        total_pool = sub_pool + ad_pool

        summary_rows.append([
            month,
            t_id,
            f"Rs {prem_rev:,.2f}",
            f"Rs {sub_pool:,.2f} (60%)",
            f"Rs {ad_rev:,.2f}",
            f"Rs {ad_pool:,.2f} (55%)",
            f"Rs {total_pool:,.2f}",
        ])

    print(_format_table(
        ["Month", "Territory", "Gross Sub Rev", "Sub Pool (60%)", "Gross Ad Rev", "Ad Pool (55%)", "Total Pool"],
        summary_rows
    ))
    return 0


def handle_royalty_calculate(args: argparse.Namespace) -> int:
    import csv
    from services.royalty_service import RoyaltyService

    output_dir = PROJECT_ROOT / "evaluation_outputs"
    settle_path = output_dir / "settlements.csv"
    rows = []

    if settle_path.exists():
        with open(settle_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if args.month and r["month"] != args.month.strip():
                    continue
                if args.licence_id and r["licence_id"] != args.licence_id.strip():
                    continue
                if args.licensor_id and r["licensor_id"] != args.licensor_id.strip():
                    continue
                rows.append(r)

    print(f"\n[LICENSOR ROYALTY SETTLEMENTS] ({len(rows)} records)")
    table_rows = [
        [
            r["month"],
            r["licence_id"],
            r["licensor_id"],
            f"{float(r['split_pct']):.1f}%",
            f"Rs {Decimal(r['gross_share']):,.2f}",
            f"Rs {Decimal(r['mg_paid']):,.2f}",
            f"Rs {Decimal(r['recouped']):,.2f}",
            f"Rs {Decimal(r['mg_balance']):,.2f}",
            f"Rs {Decimal(r['cap_retained']):,.2f}",
            f"Rs {Decimal(r['payable_before_tds']):,.2f}",
            f"{float(r['tds_pct']):.1f}%",
            f"Rs {Decimal(r['tds']):,.2f}",
            f"Rs {Decimal(r['net_payable']):,.2f}",
            r["status"],
        ]
        for r in rows[:100]
    ]
    print(_format_table(
        ["Month", "Licence", "Licensor", "Split", "Gross Share", "MG Paid", "Recouped", "MG Bal", "Cap Retained", "Payable", "TDS %", "TDS", "Net Payable", "Status"],
        table_rows
    ))
    return 0


def handle_royalty_statement(args: argparse.Namespace) -> int:
    import csv
    output_dir = PROJECT_ROOT / "evaluation_outputs"
    settle_path = output_dir / "settlements.csv"

    matched = None
    if settle_path.exists():
        with open(settle_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["licence_id"] == args.licence_id.strip() and r["month"] == args.month.strip():
                    matched = r
                    break

    if not matched:
        print(f"\n[ERROR] Settlement statement for licence '{args.licence_id}' in month '{args.month}' not found.", file=sys.stderr)
        return 1

    print(f"\n[OFFICIAL ROYALTY SETTLEMENT STATEMENT: {matched['licence_id']} ({matched['month']})]")
    print(_format_table(
        ["Financial Line Item", "Amount / Value"],
        [
            ["Settlement Month", matched["month"]],
            ["Licence ID", matched["licence_id"]],
            ["Licensor ID", matched["licensor_id"]],
            ["Co-Licensor Split", f"{matched['split_pct']}%"],
            ["Gross Revenue Share", f"Rs {Decimal(matched['gross_share']):,.2f}"],
            ["Minimum Guarantee (MG) Paid", f"Rs {Decimal(matched['mg_paid']):,.2f}"],
            ["MG Amortization / Recouped", f"Rs {Decimal(matched['recouped']):,.2f}"],
            ["Closing Unrecouped MG Balance", f"Rs {Decimal(matched['mg_balance']):,.2f}"],
            ["Contractual Cap Retained", f"Rs {Decimal(matched['cap_retained']):,.2f}"],
            ["Payable Amount Before TDS", f"Rs {Decimal(matched['payable_before_tds']):,.2f}"],
            ["Withholding Tax (TDS Rate)", f"{matched['tds_pct']}%"],
            ["Withholding Tax Deducted", f"Rs {Decimal(matched['tds']):,.2f}"],
            ["FINAL NET PAYABLE TO BENEFICIARY", f"Rs {Decimal(matched['net_payable']):,.2f}"],
            ["Settlement Execution Status", matched["status"]],
        ]
    ))
    return 0


def handle_report_calendar(args: argparse.Namespace) -> int:
    import csv
    data_dir = PROJECT_ROOT / "sample_data"
    licences_file = data_dir / "licences.csv"
    windows_file = data_dir / "licence_windows.csv"

    # Find licences for this title
    lic_ids = []
    lic_map = {}
    if licences_file.exists():
        with open(licences_file, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["title_id"] == args.title_id:
                    lic_ids.append(r["licence_id"])
                    lic_map[r["licence_id"]] = r

    # Find windows
    rows = []
    if windows_file.exists():
        with open(windows_file, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["licence_id"] in lic_ids:
                    lic = lic_map.get(r["licence_id"], {})
                    rows.append({
                        "licence_id": r["licence_id"],
                        "territory_id": lic.get("territory_id", ""),
                        "window_no": r.get("window_no", "1"),
                        "window_start": r.get("window_start", ""),
                        "window_end": r.get("window_end", ""),
                        "exclusivity": lic.get("exclusivity", ""),
                        "status": "ACTIVE",
                    })

    rep = ReportingService.format_rights_calendar(title_id=args.title_id, rows=rows)
    print(f"\n{rep}")
    return 0


def handle_report_settlement(args: argparse.Namespace) -> int:
    service = ReportingService()
    db_records = service.payment_repo.query_settlements(
        month=args.month,
        licensor_id=args.licensor_id,
    )
    if db_records:
        rep = service.format_settlement_statement(args.licensor_id, args.month, db_records)
    else:
        # Fallback to settlements.csv
        import csv
        csv_path = PROJECT_ROOT / "evaluation_outputs" / "settlements.csv"
        records = []
        if csv_path.exists():
            with open(csv_path, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["licensor_id"] == args.licensor_id and r["month"] == args.month:
                        records.append(r)
        rep = service.format_settlement_statement(args.licensor_id, args.month, records)

    print(f"\n{rep}")
    return 0


def handle_report_views(args: argparse.Namespace) -> int:
    import csv
    csv_path = PROJECT_ROOT / "evaluation_outputs" / "view_decisions.csv"
    raw_events_path = PROJECT_ROOT / "sample_data" / "view_events.csv"

    # Preload view_id -> title_id mapping from view_events.csv if available
    v_title_map = {}
    if raw_events_path.exists():
        with open(raw_events_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                v_title_map[r["view_id"]] = r["title_id"]

    records = []
    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not r.get("title_id") and r.get("view_id") in v_title_map:
                    r["title_id"] = v_title_map[r["view_id"]]
                records.append(r)

    rep = ReportingService.format_view_decisions_report(args.from_date, args.to_date, records)
    print(f"\n{rep}")
    return 0


def handle_settlement_run(args: argparse.Namespace) -> int:
    from run_engine import run_pipeline
    data_dir = Path(args.data_dir) if args.data_dir else PROJECT_ROOT / "sample_data"
    out_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "evaluation_outputs"

    run_pipeline(data_dir, out_dir)
    print(f"\n[SUCCESS] Settlement pipeline completed. Evaluation CSVs exported to {out_dir}.")
    return 0


# ---------------------------------------------------------------------------
# CLI Argument Parser Construction
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ott-manage",
        description="OTT Content Licensing, Windowing, and Master Management CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand category")

    # --- Title Subcommands ---
    title_parser = subparsers.add_parser("title", help="Title management operations")
    title_sub = title_parser.add_subparsers(dest="action", required=True)

    # title register
    t_reg = title_sub.add_parser("register", help="Register a new title")
    t_reg.add_argument("--name", dest="title_name", required=True, help="Title name")
    t_reg.add_argument("--runtime", type=int, required=True, help="Runtime duration in seconds")
    t_reg.add_argument("--category", default="FILM", help="Content category (e.g. FILM, SERIES_EPISODE)")
    t_reg.add_argument("--title-id", dest="title_id", default=None, help="Explicit title ID (optional)")
    t_reg.add_argument("--release-date", dest="release_date", default=None, help="Release date (YYYY-MM-DD)")
    t_reg.add_argument("--theatrical-premiere", dest="theatrical_premiere", default=None, help="Theatrical premiere (YYYY-MM-DD)")
    t_reg.add_argument("--tv-premiere", dest="tv_premiere", default=None, help="TV premiere (YYYY-MM-DD)")
    t_reg.set_defaults(handler=handle_title_register)

    # title get
    t_get = title_sub.add_parser("get", help="Get title details by ID")
    t_get.add_argument("--title-id", required=True, help="Title identifier")
    t_get.set_defaults(handler=handle_title_get)

    # title update
    t_upd = title_sub.add_parser("update", help="Update title metadata")
    t_upd.add_argument("--title-id", required=True, help="Title identifier")
    t_upd.add_argument("--name", dest="title_name", default=None, help="New title name")
    t_upd.add_argument("--runtime", type=int, default=None, help="New runtime in seconds")
    t_upd.add_argument("--category", default=None, help="New content category")
    t_upd.add_argument("--release-date", dest="release_date", default=None, help="New release date (YYYY-MM-DD)")
    t_upd.add_argument("--theatrical-premiere", dest="theatrical_premiere", default=None, help="Theatrical premiere")
    t_upd.add_argument("--tv-premiere", dest="tv_premiere", default=None, help="TV premiere")
    t_upd.set_defaults(handler=handle_title_update)

    # title delete
    t_del = title_sub.add_parser("delete", help="Delete a title")
    t_del.add_argument("--title-id", required=True, help="Title identifier")
    t_del.set_defaults(handler=handle_title_delete)

    # title search
    t_src = title_sub.add_parser("search", help="Search titles")
    t_src.add_argument("--query", "-q", default=None, help="Search query on name or ID")
    t_src.add_argument("--category", default=None, help="Filter by category")
    t_src.set_defaults(handler=handle_title_search)

    # title splits-set
    t_spset = title_sub.add_parser("splits-set", help="Set co-licensor splits for a title (Must sum to 100%)")
    t_spset.add_argument("--title-id", required=True, help="Title identifier")
    t_spset.add_argument("--splits", required=True, help="Comma-separated splits: LIC_ID:PCT,LIC_ID:PCT")
    t_spset.set_defaults(handler=handle_title_splits_set)

    # title splits-get
    t_spget = title_sub.add_parser("splits-get", help="Get co-licensor splits for a title")
    t_spget.add_argument("--title-id", required=True, help="Title identifier")
    t_spget.set_defaults(handler=handle_title_splits_get)

    # --- Licensor Subcommands ---
    lic_parser = subparsers.add_parser("licensor", help="Licensor and studio operations")
    lic_sub = lic_parser.add_subparsers(dest="action", required=True)

    # licensor register
    l_reg = lic_sub.add_parser("register", help="Register a new licensor")
    l_reg.add_argument("--name", required=True, help="Legal company name")
    l_reg.add_argument("--country", required=True, help="Country of tax residency")
    l_reg.add_argument("--licensor-id", default=None, help="Explicit licensor ID (optional)")
    l_reg.add_argument("--country-code", default=None, help="ISO-3166 territory code (optional)")
    l_reg.add_argument("--trade-name", default=None, help="DBA / Brand name")
    l_reg.add_argument("--is-indian", dest="is_indian", action="store_true", default=None, help="Mark as Indian resident")
    l_reg.add_argument("--treaty-tds", default=None, help="Concession DTAA withholding rate %")
    l_reg.set_defaults(handler=handle_licensor_register)

    # licensor get
    l_get = lic_sub.add_parser("get", help="Get licensor by ID")
    l_get.add_argument("--licensor-id", required=True, help="Licensor ID")
    l_get.set_defaults(handler=handle_licensor_get)

    # licensor update
    l_upd = lic_sub.add_parser("update", help="Update licensor attributes")
    l_upd.add_argument("--licensor-id", required=True, help="Licensor ID")
    l_upd.add_argument("--name", default=None, help="New legal name")
    l_upd.add_argument("--country", default=None, help="New country")
    l_upd.add_argument("--country-code", default=None, help="New country code")
    l_upd.add_argument("--trade-name", default=None, help="New trade name")
    l_upd.add_argument("--treaty-tds", default=None, help="New treaty TDS %")
    l_upd.set_defaults(handler=handle_licensor_update)

    # licensor delete
    l_del = lic_sub.add_parser("delete", help="Delete a licensor")
    l_del.add_argument("--licensor-id", required=True, help="Licensor ID")
    l_del.set_defaults(handler=handle_licensor_delete)

    # licensor search
    l_src = lic_sub.add_parser("search", help="Search licensors")
    l_src.add_argument("--query", "-q", default=None, help="Search query")
    l_src.add_argument("--country", default=None, help="Filter by country")
    l_src.set_defaults(handler=handle_licensor_search)

    # licensor list
    l_lst = lic_sub.add_parser("list", help="List all licensors")
    l_lst.set_defaults(handler=handle_licensor_list)

    # --- Licence Contract Subcommands ---
    con_parser = subparsers.add_parser("licence", help="Licence contract and windowing operations")
    con_sub = con_parser.add_subparsers(dest="action", required=True)

    # licence create
    c_cre = con_sub.add_parser("create", help="Create a new licence contract with windows")
    c_cre.add_argument("--title-id", required=True, help="Licensed title ID")
    c_cre.add_argument("--licensor-id", required=True, help="Lead licensor ID")
    c_cre.add_argument("--territory", required=True, help="Territory code (e.g. IN, US)")
    c_cre.add_argument("--exclusivity", required=True, choices=["EXCLUSIVE", "NON_EXCLUSIVE"], help="Exclusivity model")
    c_cre.add_argument("--rev-share-type", required=True, choices=["POOL_AND_AD", "POOL_ONLY"], help="Revenue share type")
    c_cre.add_argument("--mg", default="0.00", help="Minimum Guarantee advance amount")
    c_cre.add_argument("--cap", default="0.00", help="Payment cap limit")
    c_cre.add_argument("--windows", required=True, help="Availability windows: START:END,START:END (YYYY-MM-DD)")
    c_cre.add_argument("--licence-id", default=None, help="Explicit licence ID (optional)")
    c_cre.set_defaults(handler=handle_licence_create)

    # licence get
    c_get = con_sub.add_parser("get", help="Get licence contract and window details")
    c_get.add_argument("--licence-id", required=True, help="Licence identifier")
    c_get.set_defaults(handler=handle_licence_get)

    # licence update
    c_upd = con_sub.add_parser("update", help="Update licence contract terms")
    c_upd.add_argument("--licence-id", required=True, help="Licence identifier")
    c_upd.add_argument("--territory", default=None, help="New territory code")
    c_upd.add_argument("--exclusivity", choices=["EXCLUSIVE", "NON_EXCLUSIVE"], default=None, help="New exclusivity")
    c_upd.add_argument("--rev-share-type", choices=["POOL_AND_AD", "POOL_ONLY"], default=None, help="New rev-share type")
    c_upd.add_argument("--mg", default=None, help="New MG amount")
    c_upd.add_argument("--cap", default=None, help="New Cap amount")
    c_upd.add_argument("--status", choices=["ACTIVE", "DRAFT", "EXPIRED", "TERMINATED"], default=None, help="Contract status")
    c_upd.set_defaults(handler=handle_licence_update)

    # licence add-window
    c_aw = con_sub.add_parser("add-window", help="Add an availability window to an existing licence")
    c_aw.add_argument("--licence-id", required=True, help="Licence contract ID")
    c_aw.add_argument("--start", required=True, help="Window start date (YYYY-MM-DD)")
    c_aw.add_argument("--end", required=True, help="Window end date (YYYY-MM-DD)")
    c_aw.add_argument("--window-no", type=int, default=None, help="Window sequence index")
    c_aw.add_argument("--window-type", default="SVOD", help="Window service type")
    c_aw.set_defaults(handler=handle_licence_add_window)

    # licence delete
    c_del = con_sub.add_parser("delete", help="Delete a licence contract")
    c_del.add_argument("--licence-id", required=True, help="Licence ID")
    c_del.set_defaults(handler=handle_licence_delete)

    # licence search
    c_src = con_sub.add_parser("search", help="Search licence contracts")
    c_src.add_argument("--title-id", default=None, help="Filter by title ID")
    c_src.add_argument("--territory", default=None, help="Filter by territory")
    c_src.add_argument("--licensor-id", default=None, help="Filter by licensor ID")
    c_src.add_argument("--exclusivity", choices=["EXCLUSIVE", "NON_EXCLUSIVE"], default=None, help="Filter exclusivity")
    c_src.add_argument("--status", default=None, help="Filter status")
    c_src.add_argument("--query", "-q", default=None, help="Substring search on licence ID / contract number")
    c_src.set_defaults(handler=handle_licence_search)

    # licence audit
    c_aud = con_sub.add_parser("audit", help="View licence audit log entries")
    c_aud.add_argument("--licence-id", default=None, help="Filter audit log by specific licence ID")
    c_aud.add_argument("--limit", type=int, default=50, help="Max records to return")
    c_aud.set_defaults(handler=handle_licence_audit)

    # --- Playback Subcommands ---
    pb_parser = subparsers.add_parser("playback", help="Playback eligibility and telemetry verification")
    pb_sub = pb_parser.add_subparsers(dest="action", required=True)

    # playback check
    pb_chk = pb_sub.add_parser("check", help="Evaluate client playback request entitlement")
    pb_chk.add_argument("--title-id", required=True, help="Content title ID (e.g. TTL-001)")
    pb_chk.add_argument("--territory", required=True, help="Playback territory code (e.g. IN, US, SG, AE)")
    pb_chk.add_argument("--start-utc", required=True, help="Playback UTC timestamp (YYYY-MM-DD HH:MM:SS)")
    pb_chk.add_argument("--subscriber-id", default="SUB-001", help="Subscriber ID")
    pb_chk.add_argument("--tier", default="PREMIUM", help="Subscriber subscription tier")
    pb_chk.add_argument("--watch-seconds", type=int, default=3600, help="Requested watch duration in seconds")
    pb_chk.add_argument("--record", action="store_true", help="Persist heartbeat event to database")
    pb_chk.set_defaults(handler=handle_playback_check)

    # playback history
    pb_hist = pb_sub.add_parser("history", help="View recent playback decision records")
    pb_hist.add_argument("--subscriber-id", default=None, help="Filter by subscriber ID")
    pb_hist.add_argument("--title-id", default=None, help="Filter by title ID")
    pb_hist.add_argument("--limit", type=int, default=50, help="Max history rows")
    pb_hist.set_defaults(handler=handle_playback_history)

    # --- Metering Subcommands ---
    met_parser = subparsers.add_parser("metering", help="Viewership qualification and consumption metering")
    met_sub = met_parser.add_subparsers(dest="action", required=True)

    # metering summary
    met_sum = met_sub.add_parser("summary", help="Aggregated consumption metrics by month/territory/title")
    met_sum.add_argument("--month", default=None, help="Settlement month (YYYY-MM)")
    met_sum.add_argument("--territory", default=None, help="Territory code (e.g. IN, SG, US, AE)")
    met_sum.add_argument("--title-id", default=None, help="Title identifier (e.g. TTL-001)")
    met_sum.set_defaults(handler=handle_metering_summary)

    # metering view-check
    met_vc = met_sub.add_parser("view-check", help="Inspect qualification, deduplication, and metering for a view")
    met_vc.add_argument("--view-id", required=True, help="Unique view ID (e.g. VW-000491)")
    met_vc.set_defaults(handler=handle_metering_view_check)

    # --- Revenue Subcommands ---
    rev_parser = subparsers.add_parser("revenue", help="Subscription and advertisement revenue share calculations")
    rev_sub = rev_parser.add_subparsers(dest="action", required=True)

    # revenue title-shares
    r_ts = rev_sub.add_parser("title-shares", help="View title pool and advertisement revenue shares")
    r_ts.add_argument("--month", default=None, help="Settlement month (YYYY-MM)")
    r_ts.add_argument("--territory", default=None, help="Territory code (e.g. IN, SG, US, AE)")
    r_ts.add_argument("--title-id", default=None, help="Title identifier (e.g. TTL-004)")
    r_ts.set_defaults(handler=handle_revenue_title_shares)

    # revenue summary
    r_sum = rev_sub.add_parser("summary", help="Summary of 60% SVOD and 55% AVOD territory pools")
    r_sum.add_argument("--month", default=None, help="Settlement month (YYYY-MM, default 2026-07)")
    r_sum.add_argument("--territory", default=None, help="Territory code (optional)")
    r_sum.set_defaults(handler=handle_revenue_summary)

    # --- Royalty Subcommands ---
    roy_parser = subparsers.add_parser("royalty", help="Licensor settlement, recoupment, caps, and tax calculations")
    roy_sub = roy_parser.add_subparsers(dest="action", required=True)

    # royalty calculate / list
    roy_calc = roy_sub.add_parser("calculate", help="View monthly licensor royalty settlements")
    roy_calc.add_argument("--month", default=None, help="Settlement month (YYYY-MM)")
    roy_calc.add_argument("--licence-id", default=None, help="Licence contract identifier")
    roy_calc.add_argument("--licensor-id", default=None, help="Licensor identifier")
    roy_calc.set_defaults(handler=handle_royalty_calculate)

    # royalty statement
    roy_stmt = roy_sub.add_parser("statement", help="View detailed settlement statement for a licence")
    roy_stmt.add_argument("--licence-id", required=True, help="Licence contract identifier")
    roy_stmt.add_argument("--month", required=True, help="Settlement month (YYYY-MM)")
    roy_stmt.set_defaults(handler=handle_royalty_statement)

    # --- Report Subcommands ---
    rep_parser = subparsers.add_parser("report", help="Audited business reports and statements")
    rep_sub = rep_parser.add_subparsers(dest="action", required=True)

    # report calendar
    rc_cal = rep_sub.add_parser("calendar", help="Display Rights Calendar for a title")
    rc_cal.add_argument("--title-id", required=True, help="Title identifier (e.g. TTL-001)")
    rc_cal.set_defaults(handler=handle_report_calendar)

    # report settlement
    rc_stmt = rep_sub.add_parser("settlement", help="Display Licensor Settlement Statement")
    rc_stmt.add_argument("--licensor-id", required=True, help="Licensor identifier (e.g. LIC-01)")
    rc_stmt.add_argument("--month", required=True, help="Settlement month (YYYY-MM)")
    rc_stmt.set_defaults(handler=handle_report_settlement)

    # report views
    rc_vw = rep_sub.add_parser("views", help="Display View Decision Report")
    rc_vw.add_argument("--from-date", required=True, help="Start date (YYYY-MM-DD)")
    rc_vw.add_argument("--to-date", required=True, help="End date (YYYY-MM-DD)")
    rc_vw.set_defaults(handler=handle_report_views)

    # --- Settlement Subcommands ---
    set_parser = subparsers.add_parser("settlement", help="Monthly settlement pipeline operations")
    set_sub = set_parser.add_subparsers(dest="action", required=True)

    # settlement run
    set_run = set_sub.add_parser("run", help="Execute complete monthly settlement run and export CSV deliverables")
    set_run.add_argument("--data-dir", default=None, help="Path to input sample data directory")
    set_run.add_argument("--output-dir", default=None, help="Path to evaluation outputs directory")
    set_run.set_defaults(handler=handle_settlement_run)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.handler(args)
    except EntityNotFoundError as exc:
        print(f"\n[NOT FOUND ERROR] {exc.message} (Entity: {exc.entity_type}, ID: {exc.identifier})", file=sys.stderr)
        return 1
    except SplitValidationError as exc:
        print(f"\n[SPLIT VALIDATION ERROR] {exc.message}", file=sys.stderr)
        return 1
    except HoldbackViolationError as exc:
        print(f"\n[HOLDBACK VIOLATION ERROR] {exc.message} (Premiere Type: {exc.premiere_type}, Earliest Allowed: {exc.min_date})", file=sys.stderr)
        return 1
    except ExclusivityConflictError as exc:
        print(f"\n[EXCLUSIVITY CONFLICT ERROR] {exc.message} (Conflicting Licence: {exc.conflicting_licence_id})", file=sys.stderr)
        return 1
    except SettlementTimingError as exc:
        print(f"\n[SETTLEMENT TIMING ERROR] {exc.message} (Month: {exc.month}, Attempted: {exc.run_ts}, Earliest Allowed: {exc.earliest_permitted})", file=sys.stderr)
        return 1
    except DuplicateSettlementError as exc:
        print(f"\n[DUPLICATE SETTLEMENT ERROR] {exc.message} (Month: {exc.month}, Run ID: {exc.run_id})", file=sys.stderr)
        return 1
    except ValidationError as exc:
        print(f"\n[VALIDATION ERROR] {exc.message} (Field: '{exc.field}')", file=sys.stderr)
        return 1
    except ManagementEngineError as exc:
        print(f"\n[ENGINE ERROR] {exc.message} (Code: {exc.code})", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\n[UNEXPECTED ERROR] {type(exc).__name__}: {str(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
