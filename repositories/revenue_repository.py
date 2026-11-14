"""
Revenue Repository Module.
Handles retrieval of subscription revenue, advertisement revenue, and persistence
of calculated TitleShareRecords across database and CSV data sources.
"""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from database.connection import get_db_session
from models.revenue import TitleShareRecord
from models.subscriber import MonthlySubscriptionRevenue
from models.advertising import AdvertisementRevenue


class RevenueRepository:
    """Repository managing financial inputs and generated title revenue shares."""

    def __init__(
        self,
        session: Optional[Session] = None,
        data_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self._session = session
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "sample_data"

    def get_subscription_revenues(self) -> Dict[Tuple[str, str], Decimal]:
        """
        Loads monthly gross subscription revenue mapped by (month, territory_id).
        Tries CSV first if available, then relational database.
        """
        revenues: Dict[Tuple[str, str], Decimal] = {}
        csv_file = self.data_dir / "subscription_revenue.csv"

        if csv_file.exists():
            with open(csv_file, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    revenues[(r["month"], r["territory_id"])] = Decimal(r["premium_revenue"])
            return revenues

        def _fetch_from_db(session):
            stmt = select(
                MonthlySubscriptionRevenue.period_key,
                MonthlySubscriptionRevenue.territory_code,
                func.sum(MonthlySubscriptionRevenue.gross_billing_amount).label("total_gross")
            ).group_by(
                MonthlySubscriptionRevenue.period_key,
                MonthlySubscriptionRevenue.territory_code
            )
            for row in session.execute(stmt):
                revenues[(row.period_key, row.territory_code)] = Decimal(str(row.total_gross))
            return revenues

        if self._session:
            return _fetch_from_db(self._session)
        with get_db_session() as session:
            return _fetch_from_db(session)

    def get_ad_revenues(self) -> Dict[Tuple[str, str], Decimal]:
        """
        Loads monthly gross advertisement revenue mapped by (month, territory_id).
        Tries CSV first if available, then relational database.
        """
        revenues: Dict[Tuple[str, str], Decimal] = {}
        csv_file = self.data_dir / "ad_revenue.csv"

        if csv_file.exists():
            with open(csv_file, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    revenues[(r["month"], r["territory_id"])] = Decimal(r["ad_revenue"])
            return revenues

        def _fetch_from_db(session):
            stmt = select(
                AdvertisementRevenue.period_key,
                AdvertisementRevenue.territory_code,
                func.sum(AdvertisementRevenue.gross_ad_revenue).label("total_gross")
            ).group_by(
                AdvertisementRevenue.period_key,
                AdvertisementRevenue.territory_code
            )
            for row in session.execute(stmt):
                revenues[(row.period_key, row.territory_code)] = Decimal(str(row.total_gross))
            return revenues

        if self._session:
            return _fetch_from_db(self._session)
        with get_db_session() as session:
            return _fetch_from_db(session)

    def save_title_shares(self, records: List[TitleShareRecord]) -> None:
        """Persists a list of calculated TitleShareRecords to database."""
        if not records:
            return

        def _save(session):
            for rec in records:
                # Merge or add
                session.merge(rec)
            session.flush()

        if self._session:
            _save(self._session)
        else:
            with get_db_session() as session:
                _save(session)
                session.commit()

    def query_title_shares(
        self,
        month: Optional[str] = None,
        territory_code: Optional[str] = None,
        title_id: Optional[str] = None,
    ) -> List[TitleShareRecord]:
        """Queries persisted TitleShareRecords with optional filters."""
        stmt = select(TitleShareRecord)
        filters = []
        if month:
            filters.append(TitleShareRecord.period_key == month.strip())
        if territory_code:
            filters.append(TitleShareRecord.territory_code == territory_code.strip())
        if title_id:
            filters.append(TitleShareRecord.title_id == title_id.strip())
        if filters:
            stmt = stmt.filter(and_(*filters))
        stmt = stmt.order_by(
            TitleShareRecord.period_key.asc(),
            TitleShareRecord.territory_code.asc(),
            TitleShareRecord.title_id.asc(),
        )

        if self._session:
            return list(self._session.execute(stmt).scalars().all())
        with get_db_session() as session:
            return list(session.execute(stmt).scalars().all())
