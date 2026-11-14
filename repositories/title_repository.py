"""
Title Repository Module.
Handles persistence, search queries, and co-licensing split management for audiovisual titles.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import List, Optional, Sequence, Dict, Any
from sqlalchemy import select, or_
from sqlalchemy.orm import Session, selectinload

from models.title import Title, TitleSplit
from repositories.base_repository import BaseRepository


class TitleRepository(BaseRepository[Title]):
    """Data access repository for Title and TitleSplit entities."""

    def __init__(self) -> None:
        super().__init__(Title)

    def get_by_id_with_splits(self, session: Session, title_id: str) -> Optional[Title]:
        """Retrieves title with its co-licensor splits eagerly loaded."""
        stmt = (
            select(Title)
            .where(Title.title_id == title_id)
            .options(selectinload(Title.splits).selectinload(TitleSplit.licensor))
        )
        return session.scalar(stmt)

    def search(
        self,
        session: Session,
        query: Optional[str] = None,
        content_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Title]:
        """Searches titles by ID, name substring, and content category."""
        stmt = select(Title).options(selectinload(Title.splits))

        if query and query.strip():
            q_term = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    Title.title_id.ilike(q_term),
                    Title.title_name.ilike(q_term),
                )
            )

        if content_type and content_type.strip():
            stmt = stmt.where(Title.content_type == content_type.strip().upper())

        stmt = stmt.order_by(Title.title_id).offset(skip).limit(limit)
        return list(session.scalars(stmt).all())

    def set_title_splits(
        self, session: Session, title_id: str, splits_data: Sequence[Dict[str, Any]]
    ) -> List[TitleSplit]:
        """Replaces all existing licensor splits for a title atomically."""
        title = self.get_by_id(session, title_id)
        if not title:
            return []

        # Remove existing splits
        for existing in list(title.splits):
            session.delete(existing)
        session.flush()

        # Add new splits
        new_splits: List[TitleSplit] = []
        for sp in splits_data:
            pct = Decimal(str(sp.get("split_pct") or sp.get("split_percentage")))
            split_obj = TitleSplit(
                split_id=str(uuid.uuid4()),
                title_id=title_id,
                licensor_id=sp["licensor_id"].strip(),
                split_pct=pct,
            )
            session.add(split_obj)
            new_splits.append(split_obj)

        session.flush()
        return new_splits

    def get_title_splits(self, session: Session, title_id: str) -> List[TitleSplit]:
        """Retrieves current licensor splits for a given title."""
        stmt = (
            select(TitleSplit)
            .where(TitleSplit.title_id == title_id)
            .options(selectinload(TitleSplit.licensor))
            .order_by(TitleSplit.split_pct.desc())
        )
        return list(session.scalars(stmt).all())
