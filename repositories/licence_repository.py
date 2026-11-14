"""
Licence Repository Module.
Handles persistence, search queries, window management, and exclusivity conflict queries for Licence Contracts.
"""
from __future__ import annotations

import uuid
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import List, Optional, Sequence, Dict, Any
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session, selectinload

from models.contract import LicenceContract
from models.window import LicenceWindow
from repositories.base_repository import BaseRepository


class LicenceRepository(BaseRepository[LicenceContract]):
    """Data access repository for LicenceContract and LicenceWindow entities."""

    def __init__(self) -> None:
        super().__init__(LicenceContract)

    def get_by_id_with_details(
        self, session: Session, licence_id: str
    ) -> Optional[LicenceContract]:
        """Retrieves licence contract with eager-loaded windows, title, licensor, and splits."""
        stmt = (
            select(LicenceContract)
            .where(LicenceContract.contract_id == licence_id)
            .options(
                selectinload(LicenceContract.windows),
                selectinload(LicenceContract.title),
                selectinload(LicenceContract.primary_licensor),
                selectinload(LicenceContract.territory),
            )
        )
        return session.scalar(stmt)

    def search(
        self,
        session: Session,
        title_id: Optional[str] = None,
        territory_id: Optional[str] = None,
        licensor_id: Optional[str] = None,
        exclusivity: Optional[str] = None,
        status: Optional[str] = None,
        query: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[LicenceContract]:
        """Searches licence contracts with multi-criteria filtering."""
        stmt = (
            select(LicenceContract)
            .options(
                selectinload(LicenceContract.windows),
                selectinload(LicenceContract.title),
                selectinload(LicenceContract.primary_licensor),
            )
        )

        if title_id and title_id.strip():
            stmt = stmt.where(LicenceContract.title_id == title_id.strip())

        if territory_id and territory_id.strip():
            stmt = stmt.where(LicenceContract.territory_id == territory_id.strip().upper())

        if licensor_id and licensor_id.strip():
            stmt = stmt.where(LicenceContract.licensor_id == licensor_id.strip())

        if exclusivity and exclusivity.strip():
            stmt = stmt.where(LicenceContract.exclusivity == exclusivity.strip().upper())

        if status and status.strip():
            stmt = stmt.where(LicenceContract.status == status.strip().upper())

        if query and query.strip():
            q_term = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    LicenceContract.contract_id.ilike(q_term),
                    LicenceContract.contract_number.ilike(q_term),
                )
            )

        stmt = stmt.order_by(LicenceContract.contract_id).offset(skip).limit(limit)
        return list(session.scalars(stmt).all())

    def get_accepted_overlapping_licences(
        self,
        session: Session,
        title_id: str,
        territory_id: str,
        exclude_licence_id: Optional[str] = None,
    ) -> List[LicenceContract]:
        """
        Retrieves all active or accepted licences for the same title and territory
        to evaluate exclusivity collision rules.
        """
        stmt = (
            select(LicenceContract)
            .where(
                LicenceContract.title_id == title_id,
                LicenceContract.territory_id == territory_id,
                LicenceContract.status.in_(["ACTIVE", "ACCEPTED"]),
            )
            .options(selectinload(LicenceContract.windows))
        )
        if exclude_licence_id:
            stmt = stmt.where(LicenceContract.contract_id != exclude_licence_id)

        return list(session.scalars(stmt).all())

    def add_window(
        self,
        session: Session,
        contract_id: str,
        window_start: date,
        window_end: date,
        window_no: int = 1,
        window_type: str = "SVOD",
    ) -> LicenceWindow:
        """Appends a new availability window to a licence contract."""
        contract = self.get_by_id(session, contract_id)
        if not contract:
            raise ValueError(f"Licence contract '{contract_id}' does not exist.")

        # Default start and end UTC timestamps
        start_utc = datetime(window_start.year, window_start.month, window_start.day, 0, 0, 0, tzinfo=timezone.utc)
        end_utc = datetime(window_end.year, window_end.month, window_end.day, 23, 59, 59, tzinfo=timezone.utc)

        window = LicenceWindow(
            window_id=str(uuid.uuid4()),
            contract_id=contract_id,
            title_id=contract.title_id,
            territory_code=contract.territory_id or "IN",
            window_no=window_no,
            window_type=window_type,
            window_start=window_start,
            window_end=window_end,
            start_time_utc=start_utc,
            end_time_utc=end_utc,
            exclusivity=contract.exclusivity,
            status="ACTIVE",
        )
        session.add(window)
        session.flush()
        return window

    def delete_window(self, session: Session, window_id: str) -> bool:
        """Removes a single window by ID."""
        w = session.get(LicenceWindow, window_id)
        if w:
            session.delete(w)
            session.flush()
            return True
        return False
