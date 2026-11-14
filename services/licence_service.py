"""
Licence Service Module.
Coordinates licence contract creation, window scheduling, holdback enforcement (theatrical/TV),
and territorial exclusivity collision prevention.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Union
from sqlalchemy import select

from database.connection import get_db_session
from models.contract import LicenceContract
from models.window import LicenceWindow
from models.audit import AuditLog
from repositories.licence_repository import LicenceRepository
from repositories.title_repository import TitleRepository
from repositories.licensor_repository import LicensorRepository
from validators import (
    validate_licence_terms,
    validate_licence_windows,
    EntityNotFoundError,
    ValidationError,
    ExclusivityConflictError,
)


def _to_date(val: Union[str, date]) -> date:
    """Helper to convert string or date to date object."""
    if isinstance(val, str):
        return date.fromisoformat(val.strip())
    if isinstance(val, date):
        return val
    raise ValidationError(f"Invalid date format: {val}")


def _ranges_overlap(start1: date, end1: date, start2: date, end2: date) -> bool:
    """Returns True if two inclusive date ranges overlap."""
    return max(start1, start2) <= min(end1, end2)


class LicenceService:
    """Business service governing content rights contracts, windowing, and exclusivity rules."""

    def __init__(
        self,
        licence_repo: Optional[LicenceRepository] = None,
        title_repo: Optional[TitleRepository] = None,
        licensor_repo: Optional[LicensorRepository] = None,
    ) -> None:
        self.licence_repo = licence_repo or LicenceRepository()
        self.title_repo = title_repo or TitleRepository()
        self.licensor_repo = licensor_repo or LicensorRepository()

    def create_licence(
        self,
        title_id: str,
        licensor_id: str,
        territory_id: str,
        exclusivity: str,
        revenue_share_type: str,
        mg_amount: Union[Decimal, float, int] = Decimal("0.00"),
        cap_amount: Union[Decimal, float, int] = Decimal("0.00"),
        windows: Optional[Sequence[Dict[str, Any]]] = None,
        licence_id: Optional[str] = None,
        contract_number: Optional[str] = None,
        deal_type: str = "SVOD_PRO_RATA",
        rev_share_percentage: Union[Decimal, float, int] = Decimal("70.00"),
        currency: str = "USD",
        status: str = "ACTIVE",
    ) -> LicenceContract:
        """
        Creates a licence contract with commercial terms and availability windows (Functional Req 7-11).
        Enforces:
        - Input parameter validations.
        - Existing title & licensor checks.
        - Holdback constraints (45d theatrical, 7d TV).
        - Territorial exclusivity collision detection.
        """
        lid = licence_id.strip() if licence_id and licence_id.strip() else f"LIC-CON-{uuid.uuid4().hex[:6].upper()}"
        tid = title_id.strip()
        lic_id = licensor_id.strip()
        terr_id = territory_id.strip().upper()
        excl = exclusivity.strip().upper()
        rev_type = revenue_share_type.strip().upper()
        mg_dec = Decimal(str(mg_amount))
        cap_dec = Decimal(str(cap_amount))
        rev_share_dec = Decimal(str(rev_share_percentage))

        # 1. Validate basic licence terms
        validate_licence_terms(
            licence_id=lid,
            title_id=tid,
            licensor_id=lic_id,
            territory_id=terr_id,
            exclusivity=excl,
            revenue_share_type=rev_type,
            mg_amount=mg_dec,
            cap_amount=cap_dec,
        )

        windows_list = list(windows) if windows else []
        if not windows_list:
            raise ValidationError("At least one window is required for a licence.", field="windows")

        # Normalize windows
        normalized_windows = []
        for idx, w in enumerate(windows_list, start=1):
            s_dt = _to_date(w["window_start"])
            e_dt = _to_date(w["window_end"])
            w_no = int(w.get("window_no", idx))
            w_type = str(w.get("window_type", "SVOD")).strip().upper()
            normalized_windows.append({
                "window_no": w_no,
                "window_type": w_type,
                "window_start": s_dt,
                "window_end": e_dt,
            })

        with get_db_session() as session:
            # 2. Check for duplicate licence ID
            existing_lic = self.licence_repo.get_by_id(session, lid)
            if existing_lic:
                raise ValidationError(f"Licence with ID '{lid}' already exists.", field="licence_id")

            # 3. Check Title existence
            title = self.title_repo.get_by_id(session, tid)
            if not title:
                raise EntityNotFoundError("Title", tid)

            # 4. Check Licensor existence
            licensor = self.licensor_repo.get_by_id(session, lic_id)
            if not licensor:
                raise EntityNotFoundError("Licensor", lic_id)

            # 5. Holdback validation against title's premiere dates (Functional Req 11, BR-02)
            validate_licence_windows(
                normalized_windows,
                theatrical_premiere=title.theatrical_premiere,
                tv_premiere=title.tv_premiere,
            )

            # 6. Exclusivity collision check (BR-01)
            overlapping_candidates = self.licence_repo.get_accepted_overlapping_licences(
                session, title_id=tid, territory_id=terr_id
            )
            for ex_lic in overlapping_candidates:
                # If either candidate licence or existing licence is EXCLUSIVE, check window overlaps
                if excl == "EXCLUSIVE" or ex_lic.exclusivity == "EXCLUSIVE":
                    for nw in normalized_windows:
                        nw_s = nw["window_start"]
                        nw_e = nw["window_end"]
                        for ew in ex_lic.windows:
                            ew_s = ew.window_start
                            ew_e = ew.window_end
                            if _ranges_overlap(nw_s, nw_e, ew_s, ew_e):
                                raise ExclusivityConflictError(
                                    f"Licence window ({nw_s} to {nw_e}) conflicts with existing "
                                    f"licence '{ex_lic.contract_id}' ({ew_s} to {ew_e}, {ex_lic.exclusivity}) "
                                    f"for title '{tid}' in territory '{terr_id}'.",
                                    conflicting_licence_id=ex_lic.contract_id,
                                )

            # Determine contract effective and expiration dates from windows
            min_start = min(w["window_start"] for w in normalized_windows)
            max_end = max(w["window_end"] for w in normalized_windows)

            c_num = contract_number.strip() if contract_number and contract_number.strip() else f"LIC-NUM-{lid}"

            contract = LicenceContract(
                contract_id=lid,
                contract_number=c_num,
                licensor_id=lic_id,
                title_id=tid,
                deal_type=deal_type,
                rev_share_percentage=rev_share_dec,
                technical_fee_percentage=Decimal("0.00"),
                effective_date=min_start,
                expiration_date=max_end,
                settlement_frequency="MONTHLY",
                contract_currency=currency.strip().upper(),
                territory_id=terr_id,
                exclusivity=excl,
                revenue_share_type=rev_type,
                mg_amount=mg_dec,
                cap_amount=cap_dec,
                status=status.strip().upper(),
            )
            self.licence_repo.save(session, contract)

            # Add windows
            for w in normalized_windows:
                start_dt = w["window_start"]
                end_dt = w["window_end"]
                start_utc = datetime(start_dt.year, start_dt.month, start_dt.day, 0, 0, 0, tzinfo=timezone.utc)
                end_utc = datetime(end_dt.year, end_dt.month, end_dt.day, 23, 59, 59, tzinfo=timezone.utc)

                win_obj = LicenceWindow(
                    window_id=str(uuid.uuid4()),
                    contract_id=lid,
                    title_id=tid,
                    territory_code=terr_id,
                    window_no=w["window_no"],
                    window_type=w["window_type"],
                    window_start=start_dt,
                    window_end=end_dt,
                    start_time_utc=start_utc,
                    end_time_utc=end_utc,
                    exclusivity=excl,
                    status="ACTIVE",
                )
                session.add(win_obj)

            session.flush()

            # Record audit log for accepted contract creation
            payload = {
                "contract_id": lid,
                "title_id": tid,
                "licensor_id": lic_id,
                "territory_id": terr_id,
                "exclusivity": excl,
                "revenue_share_type": rev_type,
                "mg_amount": str(mg_dec),
                "cap_amount": str(cap_dec),
                "status": contract.status,
                "windows": [
                    {"no": w["window_no"], "start": str(w["window_start"]), "end": str(w["window_end"])}
                    for w in normalized_windows
                ],
            }
            payload_str = json.dumps(payload, default=str)
            hash_digest = hashlib.sha256(f"{lid}:CONTRACT_CREATED:{payload_str}".encode("utf-8")).hexdigest()
            session.add(
                AuditLog(
                    table_name="licence_contracts",
                    record_id=lid,
                    action="CONTRACT_CREATED",
                    performed_by="LICENCE_SERVICE",
                    new_values_json=payload_str,
                    cryptographic_hash=hash_digest,
                )
            )
            session.flush()

            # Fetch with full relations
            saved_contract = self.licence_repo.get_by_id_with_details(session, lid)
            return saved_contract

    def get_licence(self, licence_id: str) -> LicenceContract:
        """Retrieves licence contract with windows, title, licensor, and territory eagerly loaded."""
        with get_db_session() as session:
            lic = self.licence_repo.get_by_id_with_details(session, licence_id.strip())
            if not lic:
                raise EntityNotFoundError("Licence", licence_id)
            return lic

    def update_licence(
        self,
        licence_id: str,
        territory_id: Optional[str] = None,
        exclusivity: Optional[str] = None,
        revenue_share_type: Optional[str] = None,
        mg_amount: Optional[Union[Decimal, float, int]] = None,
        cap_amount: Optional[Union[Decimal, float, int]] = None,
        status: Optional[str] = None,
        rev_share_percentage: Optional[Union[Decimal, float, int]] = None,
    ) -> LicenceContract:
        """Updates terms or status of an existing licence contract (Functional Req 12)."""
        lid = licence_id.strip()
        with get_db_session() as session:
            lic = self.licence_repo.get_by_id_with_details(session, lid)
            if not lic:
                raise EntityNotFoundError("Licence", lid)

            new_terr = territory_id.strip().upper() if territory_id else lic.territory_id
            new_excl = exclusivity.strip().upper() if exclusivity else lic.exclusivity
            new_rev_type = revenue_share_type.strip().upper() if revenue_share_type else lic.revenue_share_type
            new_mg = Decimal(str(mg_amount)) if mg_amount is not None else lic.mg_amount
            new_cap = Decimal(str(cap_amount)) if cap_amount is not None else lic.cap_amount

            # Validate updated terms
            validate_licence_terms(
                licence_id=lid,
                title_id=lic.title_id,
                licensor_id=lic.licensor_id,
                territory_id=new_terr,
                exclusivity=new_excl,
                revenue_share_type=new_rev_type,
                mg_amount=new_mg,
                cap_amount=new_cap,
            )

            # If exclusivity or territory changed, re-check collision against other licences
            if new_terr != lic.territory_id or new_excl != lic.exclusivity:
                overlapping_candidates = self.licence_repo.get_accepted_overlapping_licences(
                    session, title_id=lic.title_id, territory_id=new_terr, exclude_licence_id=lid
                )
                for ex_lic in overlapping_candidates:
                    if new_excl == "EXCLUSIVE" or ex_lic.exclusivity == "EXCLUSIVE":
                        for cw in lic.windows:
                            for ew in ex_lic.windows:
                                if _ranges_overlap(cw.window_start, cw.window_end, ew.window_start, ew.window_end):
                                    raise ExclusivityConflictError(
                                        f"Updated exclusivity/territory creates conflict with licence '{ex_lic.contract_id}'.",
                                        conflicting_licence_id=ex_lic.contract_id,
                                    )

            lic.territory_id = new_terr
            lic.exclusivity = new_excl
            lic.revenue_share_type = new_rev_type
            lic.mg_amount = new_mg
            lic.cap_amount = new_cap

            if status is not None:
                lic.status = status.strip().upper()

            if rev_share_percentage is not None:
                lic.rev_share_percentage = Decimal(str(rev_share_percentage))

            # Also update windows exclusivity if exclusivity changed
            if exclusivity is not None:
                for w in lic.windows:
                    w.exclusivity = new_excl

            self.licence_repo.save(session, lic)
            session.refresh(lic)
            return self.licence_repo.get_by_id_with_details(session, lid)

    def add_window(
        self,
        licence_id: str,
        window_start: Union[str, date],
        window_end: Union[str, date],
        window_no: Optional[int] = None,
        window_type: str = "SVOD",
    ) -> LicenceWindow:
        """
        Adds a new availability window to an existing licence (Functional Req 9, 10).
        Enforces holdback and exclusivity checks.
        """
        lid = licence_id.strip()
        s_dt = _to_date(window_start)
        e_dt = _to_date(window_end)
        w_type = window_type.strip().upper()

        with get_db_session() as session:
            lic = self.licence_repo.get_by_id_with_details(session, lid)
            if not lic:
                raise EntityNotFoundError("Licence", lid)

            # Holdback check against title
            title = self.title_repo.get_by_id(session, lic.title_id)
            validate_licence_windows(
                [{"window_start": s_dt, "window_end": e_dt}],
                theatrical_premiere=title.theatrical_premiere if title else None,
                tv_premiere=title.tv_premiere if title else None,
            )

            # Exclusivity collision check
            overlapping_candidates = self.licence_repo.get_accepted_overlapping_licences(
                session, title_id=lic.title_id, territory_id=lic.territory_id, exclude_licence_id=lid
            )
            for ex_lic in overlapping_candidates:
                if lic.exclusivity == "EXCLUSIVE" or ex_lic.exclusivity == "EXCLUSIVE":
                    for ew in ex_lic.windows:
                        if _ranges_overlap(s_dt, e_dt, ew.window_start, ew.window_end):
                            raise ExclusivityConflictError(
                                f"New window ({s_dt} to {e_dt}) conflicts with licence '{ex_lic.contract_id}' "
                                f"({ew.window_start} to {ew.window_end}, {ex_lic.exclusivity}).",
                                conflicting_licence_id=ex_lic.contract_id,
                            )

            next_no = window_no or (len(lic.windows) + 1)
            start_utc = datetime(s_dt.year, s_dt.month, s_dt.day, 0, 0, 0, tzinfo=timezone.utc)
            end_utc = datetime(e_dt.year, e_dt.month, e_dt.day, 23, 59, 59, tzinfo=timezone.utc)

            win = LicenceWindow(
                window_id=str(uuid.uuid4()),
                contract_id=lid,
                title_id=lic.title_id,
                territory_code=lic.territory_id,
                window_no=next_no,
                window_type=w_type,
                window_start=s_dt,
                window_end=e_dt,
                start_time_utc=start_utc,
                end_time_utc=end_utc,
                exclusivity=lic.exclusivity,
                status="ACTIVE",
            )
            session.add(win)

            # Expand contract expiration_date if new window ends later
            if e_dt > lic.expiration_date:
                lic.expiration_date = e_dt
            if s_dt < lic.effective_date:
                lic.effective_date = s_dt

            session.flush()
            return win

    def delete_window(self, licence_id: str, window_id: str) -> bool:
        """Removes a window from a licence. Enforces minimum 1 window requirement."""
        lid = licence_id.strip()
        wid = window_id.strip()
        with get_db_session() as session:
            lic = self.licence_repo.get_by_id_with_details(session, lid)
            if not lic:
                raise EntityNotFoundError("Licence", lid)

            if len(lic.windows) <= 1:
                raise ValidationError("Cannot remove the only window from a licence contract.", field="windows")

            return self.licence_repo.delete_window(session, wid)

    def delete_licence(self, licence_id: str) -> bool:
        """Deletes a licence contract and its associated windows."""
        lid = licence_id.strip()
        with get_db_session() as session:
            lic = self.licence_repo.get_by_id(session, lid)
            if not lic:
                raise EntityNotFoundError("Licence", lid)
            return self.licence_repo.delete(session, lid)

    def search_licences(
        self,
        title_id: Optional[str] = None,
        territory_id: Optional[str] = None,
        licensor_id: Optional[str] = None,
        exclusivity: Optional[str] = None,
        status: Optional[str] = None,
        query: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[LicenceContract]:
        """Searches licence contracts by multiple criteria (Functional Req 12)."""
        with get_db_session() as session:
            return self.licence_repo.search(
                session,
                title_id=title_id,
                territory_id=territory_id,
                licensor_id=licensor_id,
                exclusivity=exclusivity,
                status=status,
                query=query,
                skip=skip,
                limit=limit,
            )

    def get_audit_logs(
        self, licence_id: Optional[str] = None, limit: int = 100
    ) -> List[AuditLog]:
        """Retrieves audit trail entries for licence contracts."""
        with get_db_session() as session:
            stmt = select(AuditLog).where(AuditLog.table_name == "licence_contracts")
            if licence_id:
                stmt = stmt.where(AuditLog.record_id == licence_id.strip())
            stmt = stmt.order_by(AuditLog.created_at_utc.desc()).limit(limit)
            return list(session.scalars(stmt).all())
