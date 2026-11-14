"""
View Repository Module.
Data access layer for ViewEvent and QualifyingViewRecord relational entities.
"""
from __future__ import annotations

from typing import List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from database.connection import get_db_session
from models.viewership import ViewEvent, QualifyingViewRecord


class ViewRepository:
    """Repository handling persistence and queries for view events and qualification decisions."""

    def __init__(self, session: Optional[Session] = None) -> None:
        self._session = session

    def _get_session(self):
        if self._session:
            return self._session
        return get_db_session()

    def create_view_event(self, event: ViewEvent) -> ViewEvent:
        """Persists a new raw telemetry view event."""
        if self._session:
            self._session.add(event)
            self._session.flush()
            return event

        with get_db_session() as session:
            session.add(event)
            session.commit()
            session.refresh(event)
            return event

    def create_qualifying_record(self, record: QualifyingViewRecord) -> QualifyingViewRecord:
        """Persists a scrubbed qualifying view record."""
        if self._session:
            self._session.add(record)
            self._session.flush()
            return record

        with get_db_session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def save_batch(
        self,
        events: List[ViewEvent],
        records: List[QualifyingViewRecord],
    ) -> None:
        """Bulk persists events and qualifying records efficiently."""
        if self._session:
            for ev in events:
                self._session.add(ev)
            for rec in records:
                self._session.add(rec)
            self._session.flush()
            return

        with get_db_session() as session:
            for ev in events:
                session.add(ev)
            for rec in records:
                session.add(rec)
            session.commit()

    def get_view_event(self, event_id: str) -> Optional[ViewEvent]:
        """Finds a view event by its primary identifier."""
        if self._session:
            return self._session.get(ViewEvent, event_id)
        with get_db_session() as session:
            return session.get(ViewEvent, event_id)

    def get_qualifying_record_by_view_id(self, view_id: str) -> Optional[QualifyingViewRecord]:
        """Finds a qualifying record for a specific view event."""
        stmt = select(QualifyingViewRecord).filter(QualifyingViewRecord.view_event_id == view_id)
        if self._session:
            return self._session.execute(stmt).scalar_one_or_none()
        with get_db_session() as session:
            return session.execute(stmt).scalar_one_or_none()

    def list_view_events(
        self,
        limit: int = 100,
        title_id: Optional[str] = None,
        subscriber_id: Optional[str] = None,
        territory_code: Optional[str] = None,
    ) -> List[ViewEvent]:
        """Lists raw view events matching filter criteria."""
        stmt = select(ViewEvent)
        filters = []
        if title_id:
            filters.append(ViewEvent.title_id == title_id.strip())
        if subscriber_id:
            filters.append(ViewEvent.user_id == subscriber_id.strip())
        if territory_code:
            filters.append(ViewEvent.territory_code == territory_code.strip())
        if filters:
            stmt = stmt.filter(and_(*filters))
        stmt = stmt.order_by(ViewEvent.playback_start_utc.asc()).limit(limit)

        if self._session:
            return list(self._session.execute(stmt).scalars().all())
        with get_db_session() as session:
            return list(session.execute(stmt).scalars().all())

    def list_qualifying_records(
        self,
        period_key: Optional[str] = None,
        territory_code: Optional[str] = None,
        title_id: Optional[str] = None,
        counted_only: bool = False,
    ) -> List[QualifyingViewRecord]:
        """Lists qualifying records filtered by period, territory, and counted flag."""
        stmt = select(QualifyingViewRecord)
        filters = []
        if period_key:
            filters.append(QualifyingViewRecord.period_key == period_key.strip())
        if territory_code:
            filters.append(QualifyingViewRecord.territory_code == territory_code.strip())
        if title_id:
            filters.append(QualifyingViewRecord.title_id == title_id.strip())
        if counted_only:
            filters.append(QualifyingViewRecord.is_counted == True)  # noqa: E712
        if filters:
            stmt = stmt.filter(and_(*filters))

        if self._session:
            return list(self._session.execute(stmt).scalars().all())
        with get_db_session() as session:
            return list(session.execute(stmt).scalars().all())

    def count_view_events(self) -> int:
        """Returns total count of view events."""
        stmt = select(func.count()).select_from(ViewEvent)
        if self._session:
            return self._session.execute(stmt).scalar() or 0
        with get_db_session() as session:
            return session.execute(stmt).scalar() or 0

    def count_qualifying_records(self) -> int:
        """Returns total count of qualifying records."""
        stmt = select(func.count()).select_from(QualifyingViewRecord)
        if self._session:
            return self._session.execute(stmt).scalar() or 0
        with get_db_session() as session:
            return session.execute(stmt).scalar() or 0
