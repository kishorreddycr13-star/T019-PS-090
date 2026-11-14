"""
Royalty Adjustment and Payment Calculation Service Module.
Orchestrates BR-07 (Minimum Guarantee & Recoupment), BR-08 (Payment Caps),
BR-09 (Withholding Tax & Treaty Rates), and BR-10 (Co-Licensor Splits with Paisa Residue).
"""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from services.mg_service import MGService
from services.recoupment_service import RecoupmentService
from services.cap_service import CapService
from services.tax_service import TaxService
from services.licensor_split_service import LicensorSplitService
from repositories.payment_repository import PaymentRepository
from models.settlement import MonthlySettlement


class RoyaltyService:
    """Central orchestration service for licensor royalty adjustments and net payment computations."""

    def __init__(
        self,
        licences: Optional[Dict[str, Dict[str, Any]]] = None,
        licensors: Optional[Dict[str, Dict[str, Any]]] = None,
        title_splits: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        windows: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        data_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "sample_data"
        self.licences = licences or self._load_licences()
        self.licensors = licensors or self._load_licensors()
        self.title_splits = title_splits or self._load_title_splits()
        self.windows = windows or self._load_windows()

        self.mg_service = MGService(windows_map=self.windows)
        self.recoupment_service = RecoupmentService()
        self.cap_service = CapService()
        self.tax_service = TaxService()
        self.split_service = LicensorSplitService()
        self.payment_repo = PaymentRepository(data_dir=self.data_dir)

        # Audit history of generated settlements
        self.settlement_records: List[Dict[str, Any]] = []

    def _load_licences(self) -> Dict[str, Dict[str, Any]]:
        csv_file = self.data_dir / "licences.csv"
        if csv_file.exists():
            with open(csv_file, "r", encoding="utf-8") as f:
                return {r["licence_id"]: r for r in csv.DictReader(f)}
        return {}

    def _load_licensors(self) -> Dict[str, Dict[str, Any]]:
        csv_file = self.data_dir / "licensors.csv"
        if csv_file.exists():
            with open(csv_file, "r", encoding="utf-8") as f:
                return {r["licensor_id"]: r for r in csv.DictReader(f)}
        return {}

    def _load_title_splits(self) -> Dict[str, List[Dict[str, Any]]]:
        csv_file = self.data_dir / "title_splits.csv"
        splits: Dict[str, List[Dict[str, Any]]] = {}
        if csv_file.exists():
            with open(csv_file, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    splits.setdefault(r["title_id"], []).append(r)
        return splits

    def _load_windows(self) -> Dict[str, List[Dict[str, Any]]]:
        csv_file = self.data_dir / "licence_windows.csv"
        windows: Dict[str, List[Dict[str, Any]]] = {}
        if csv_file.exists():
            with open(csv_file, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    windows.setdefault(r["licence_id"], []).append(r)
        return windows

    def reset_state(self) -> None:
        """Clears persistent balances and cumulative payments."""
        self.mg_service.reset()
        self.cap_service.reset()
        self.settlement_records.clear()

    def calculate_monthly_settlements(
        self,
        month: str,
        accepted_licences: Sequence[str],
        title_shares: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Executes a monthly settlement run for accepted licences against title share revenue allocations.
        """
        # Build quick lookup for title shares in this month: (terr_id, title_id) -> dict
        title_lookup: Dict[tuple, Dict[str, Decimal]] = {}
        for ts in title_shares:
            if ts.get("month") == month:
                key = (ts.get("territory_id"), ts.get("title_id"))
                title_lookup[key] = {
                    "pool_share": Decimal(str(ts.get("pool_share", "0.00"))),
                    "ad_share": Decimal(str(ts.get("ad_share", "0.00"))),
                    "title_share": Decimal(str(ts.get("title_share", "0.00"))),
                }

        month_settlements: List[Dict[str, Any]] = []

        for licence_id in accepted_licences:
            lic = self.licences.get(licence_id)
            if not lic:
                continue

            title_id = lic["title_id"]
            terr_id = lic["territory_id"]
            rev_type = lic.get("revenue_share_type", "POOL_AND_AD")
            contract_mg = Decimal(str(lic.get("mg_amount", "0.00")))
            contract_cap = Decimal(str(lic.get("cap_amount", "0.00")))

            shares = title_lookup.get(
                (terr_id, title_id),
                {"pool_share": Decimal("0.00"), "ad_share": Decimal("0.00")},
            )

            # POOL_ONLY licences exclude ad share
            if rev_type == "POOL_ONLY":
                licence_gross = shares["pool_share"]
            else:
                licence_gross = shares["pool_share"] + shares["ad_share"]

            # Co-licensor splits (BR-10 / EC-07)
            if title_id in self.title_splits:
                splits = self.title_splits[title_id]
            else:
                splits = [{"licensor_id": lic["licensor_id"], "split_pct": "100.00"}]

            split_allocations = self.split_service.allocate_splits(
                total_amount=licence_gross,
                splits=splits,
                title_id=title_id,
            )

            # Month 1 MG advance condition (BR-07 / EC-04)
            is_month_1 = self.mg_service.is_month_one(licence_id, month) and (contract_mg > Decimal("0.00"))
            is_new_mg_payout = is_month_1 and (licence_id not in self.mg_service.mg_paid_licences)

            for sp in splits:
                licensor_id = sp["licensor_id"]
                split_pct = Decimal(str(sp["split_pct"]))
                gross_share = split_allocations[licensor_id]

                # 1. MG Payout & Recoupment
                mg_paid, _ = self.mg_service.evaluate_mg_payout(
                    licence_id=licence_id,
                    month=month,
                    contract_mg=contract_mg,
                    split_pct=split_pct,
                )
                if is_new_mg_payout:
                    self.mg_service.record_mg_advance_initialized(licence_id, contract_mg)

                current_mg_bal = self.mg_service.get_outstanding_balance(licence_id)
                recoup_res = self.recoupment_service.calculate_recoupment(
                    gross_share=gross_share,
                    outstanding_mg=current_mg_bal,
                )
                recouped = recoup_res.recouped_amount
                new_mg_bal = recoup_res.outstanding_mg_after

                # 2. Determine Candidate Payable Before Cap
                if contract_mg > Decimal("0.00"):
                    if is_new_mg_payout:
                        # Month 1: MG is paid + any excess gross above total MG
                        excess = max(Decimal("0.00"), gross_share - contract_mg)
                        candidate_payable = mg_paid + excess
                    else:
                        candidate_payable = max(Decimal("0.00"), gross_share - current_mg_bal)
                else:
                    candidate_payable = gross_share

                # 3. Apply Payment Cap (BR-08 / EC-05)
                cap_res = self.cap_service.apply_payment_cap(
                    licence_id=licence_id,
                    payable_amount=candidate_payable,
                    contract_cap=contract_cap,
                )
                payable_before_tds = cap_res.payable_after_cap
                cap_retained = cap_res.cap_retained
                status = cap_res.status

                # Update MG balance state for next licensor/month
                self.mg_service.update_balance_after_recoupment(licence_id, recouped)

                # 4. Apply Withholding Tax (BR-09)
                licensor_info = self.licensors.get(licensor_id, {"is_indian": "true"})
                is_indian = str(licensor_info.get("is_indian", "true")).lower() == "true"
                treaty_rate_str = licensor_info.get("treaty_tds_pct", "")

                tax_res = self.tax_service.calculate_tax(
                    licensor_id=licensor_id,
                    payable_before_tds=payable_before_tds,
                    is_indian=is_indian,
                    treaty_tds_pct=treaty_rate_str,
                )

                settlement_row = {
                    "month": month,
                    "licence_id": licence_id,
                    "licensor_id": licensor_id,
                    "split_pct": f"{split_pct:.2f}",
                    "gross_share": f"{gross_share:.2f}",
                    "mg_paid": f"{mg_paid:.2f}",
                    "recouped": f"{recouped:.2f}",
                    "mg_balance": f"{new_mg_bal:.2f}",
                    "cap_retained": f"{cap_retained:.2f}",
                    "payable_before_tds": f"{payable_before_tds:.2f}",
                    "tds_pct": f"{tax_res.tds_pct:.2f}",
                    "tds": f"{tax_res.tds_amount:.2f}",
                    "net_payable": f"{tax_res.net_payable:.2f}",
                    "status": status,
                }
                month_settlements.append(settlement_row)
                self.settlement_records.append(settlement_row)

        return month_settlements

    def persist_settlements(self, settlements: List[Dict[str, Any]]) -> None:
        """Converts dict settlement rows to MonthlySettlement entities and saves them to DB."""
        entities = [
            MonthlySettlement(
                settlement_run_number=f"RUN-{r['month']}",
                period_key=r["month"],
                contract_id=r["licence_id"],
                licensor_id=r["licensor_id"],
                gross_royalty_amount=Decimal(r["gross_share"]),
                split_pct=Decimal(r["split_pct"]),
                mg_paid=Decimal(r["mg_paid"]),
                mg_recouped_amount=Decimal(r["recouped"]),
                mg_balance=Decimal(r["mg_balance"]),
                cap_retained=Decimal(r["cap_retained"]),
                payable_before_tds=Decimal(r["payable_before_tds"]),
                tds_pct=Decimal(r["tds_pct"]),
                withholding_tax_amount=Decimal(r["tds"]),
                net_payable_amount=Decimal(r["net_payable"]),
                status=r["status"],
            )
            for r in settlements
        ]
        self.payment_repo.save_settlements(entities)

    @staticmethod
    def export_settlements_csv(
        settlements: List[Dict[str, Any]],
        output_path: Union[str, Path],
    ) -> None:
        """
        Exports settlements to CSV in the required evaluation format:
        month,licence_id,licensor_id,split_pct,gross_share,mg_paid,recouped,mg_balance,cap_retained,payable_before_tds,tds_pct,tds,net_payable,status
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "month",
            "licence_id",
            "licensor_id",
            "split_pct",
            "gross_share",
            "mg_paid",
            "recouped",
            "mg_balance",
            "cap_retained",
            "payable_before_tds",
            "tds_pct",
            "tds",
            "net_payable",
            "status",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in settlements:
                writer.writerow({fn: r.get(fn, "") for fn in fieldnames})
