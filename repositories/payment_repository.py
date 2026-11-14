"""
Payment and Settlement Repository Module.
Handles persistence and querying of MonthlySettlement records (Table 18).
"""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from database.connection import get_db_session
from models.settlement import MonthlySettlement


class PaymentRepository:
    """Repository handling monthly settlement records and payment audit history."""

    def __init__(
        self,
        session: Optional[Session] = None,
        data_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self._session = session
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "sample_data"

    def save_settlements(self, records: List[MonthlySettlement]) -> None:
        """Persists or merges a collection of MonthlySettlement entities."""
        if not records:
            return

        def _save(session):
            for rec in records:
                session.merge(rec)
            session.flush()

        if self._session:
            _save(self._session)
        else:
            with get_db_session() as session:
                _save(session)
                session.commit()

    def query_settlements(
        self,
        month: Optional[str] = None,
        licence_id: Optional[str] = None,
        licensor_id: Optional[str] = None,
    ) -> List[MonthlySettlement]:
        """Queries persisted MonthlySettlement records with optional filtering."""
        stmt = select(MonthlySettlement)
        filters = []
        if month:
            filters.append(MonthlySettlement.period_key == month.strip())
        if licence_id:
            filters.append(MonthlySettlement.contract_id == licence_id.strip())
        if licensor_id:
            filters.append(MonthlySettlement.licensor_id == licensor_id.strip())

        if filters:
            stmt = stmt.filter(and_(*filters))

        stmt = stmt.order_by(
            MonthlySettlement.period_key.asc(),
            MonthlySettlement.contract_id.asc(),
            MonthlySettlement.licensor_id.asc(),
        )

        if self._session:
            return list(self._session.execute(stmt).scalars().all())
        with get_db_session() as session:
            return list(session.execute(stmt).scalars().all())
