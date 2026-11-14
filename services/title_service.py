"""
Title Service Module.
Coordinates title registration, metadata updates, queries, and co-licensor splits with 100% sum validation.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Any

from database.connection import get_db_session
from models.title import Title, TitleSplit
from repositories.title_repository import TitleRepository
from repositories.licensor_repository import LicensorRepository
from validators import (
    validate_title_input,
    validate_title_splits,
    EntityNotFoundError,
    ValidationError,
)


class TitleService:
    """Business service for audiovisual title management and co-licensing split governance."""

    def __init__(
        self,
        title_repo: Optional[TitleRepository] = None,
        licensor_repo: Optional[LicensorRepository] = None,
    ) -> None:
        self.title_repo = title_repo or TitleRepository()
        self.licensor_repo = licensor_repo or LicensorRepository()

    def register_title(
        self,
        title_name: str,
        runtime_seconds: int,
        content_type: str = "FILM",
        title_id: Optional[str] = None,
        release_date: Optional[date] = None,
        theatrical_premiere: Optional[date] = None,
        tv_premiere: Optional[date] = None,
        isan_code: Optional[str] = None,
        original_language: str = "en",
        age_rating: Optional[str] = None,
    ) -> Title:
        """
        Registers a new audiovisual title (Functional Req 1, 2, 11).
        Stores title ID, name, runtime, release date, content category, and premiere dates.
        """
        tid = title_id.strip() if title_id and title_id.strip() else f"TTL-{uuid.uuid4().hex[:6].upper()}"
        cat_clean = content_type.strip().upper()

        # Validate business constraints
        validate_title_input(
            title_id=tid,
            title_name=title_name,
            runtime_seconds=runtime_seconds,
            content_type=cat_clean,
            release_date=release_date,
            theatrical_premiere=theatrical_premiere,
            tv_premiere=tv_premiere,
        )

        with get_db_session() as session:
            # Check for existing title ID
            existing = self.title_repo.get_by_id(session, tid)
            if existing:
                raise ValidationError(f"Title with ID '{tid}' already exists.", field="title_id")

            title = Title(
                title_id=tid,
                title_name=title_name.strip(),
                content_type=cat_clean,
                duration_seconds=runtime_seconds,
                release_date=release_date,
                theatrical_premiere=theatrical_premiere,
                tv_premiere=tv_premiere,
                isan_code=isan_code.strip() if isan_code and isan_code.strip() else None,
                original_language=original_language.strip(),
                age_rating=age_rating.strip() if age_rating and age_rating.strip() else None,
                is_active=True,
            )
            self.title_repo.save(session, title)
            # Eagerly refresh representation
            session.refresh(title)
            return title

    def get_title(self, title_id: str) -> Title:
        """Retrieves title by ID with its splits eagerly loaded."""
        with get_db_session() as session:
            title = self.title_repo.get_by_id_with_splits(session, title_id.strip())
            if not title:
                raise EntityNotFoundError("Title", title_id)
            return title

    def update_title(
        self,
        title_id: str,
        title_name: Optional[str] = None,
        runtime_seconds: Optional[int] = None,
        content_type: Optional[str] = None,
        release_date: Optional[date] = None,
        theatrical_premiere: Optional[date] = None,
        tv_premiere: Optional[date] = None,
        is_active: Optional[bool] = None,
    ) -> Title:
        """Updates metadata for an existing title."""
        with get_db_session() as session:
            title = self.title_repo.get_by_id(session, title_id.strip())
            if not title:
                raise EntityNotFoundError("Title", title_id)

            if title_name is not None:
                if not title_name.strip():
                    raise ValidationError("Title name cannot be blank.", field="title_name")
                title.title_name = title_name.strip()

            if runtime_seconds is not None:
                if runtime_seconds <= 0:
                    raise ValidationError("Runtime must be positive.", field="runtime_seconds")
                title.duration_seconds = runtime_seconds

            if content_type is not None:
                cat_clean = content_type.strip().upper()
                validate_title_input(
                    title_id=title.title_id,
                    title_name=title.title_name,
                    runtime_seconds=title.duration_seconds,
                    content_type=cat_clean,
                )
                title.content_type = cat_clean

            if release_date is not None:
                title.release_date = release_date
            if theatrical_premiere is not None:
                title.theatrical_premiere = theatrical_premiere
            if tv_premiere is not None:
                title.tv_premiere = tv_premiere
            if is_active is not None:
                title.is_active = is_active

            self.title_repo.save(session, title)
            session.refresh(title)
            return title

    def delete_title(self, title_id: str) -> bool:
        """Deletes a title and its associated splits."""
        with get_db_session() as session:
            title = self.title_repo.get_by_id(session, title_id.strip())
            if not title:
                raise EntityNotFoundError("Title", title_id)
            return self.title_repo.delete(session, title.title_id)

    def search_titles(
        self,
        query: Optional[str] = None,
        content_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Title]:
        """Searches titles by name/ID query and category filter."""
        with get_db_session() as session:
            return self.title_repo.search(
                session, query=query, content_type=content_type, skip=skip, limit=limit
            )

    def register_title_splits(
        self,
        title_id: str,
        splits: Sequence[Dict[str, Any]],
    ) -> List[TitleSplit]:
        """
        Registers co-licensor split percentages for a title (Functional Req 4, 5, 6).
        Ensures all splits total exactly 100.00% and licensors exist.
        """
        tid = title_id.strip()

        # 1. Enforce 100% sum rule and individual constraints
        validate_title_splits(splits, tid)

        with get_db_session() as session:
            # 2. Check title exists
            title = self.title_repo.get_by_id(session, tid)
            if not title:
                raise EntityNotFoundError("Title", tid)

            # 3. Check every licensor exists
            for sp in splits:
                lid = sp["licensor_id"].strip()
                licensor = self.licensor_repo.get_by_id(session, lid)
                if not licensor:
                    raise EntityNotFoundError("Licensor", lid)

            # 4. Save splits atomically
            new_splits = self.title_repo.set_title_splits(session, tid, splits)
            return new_splits

    def get_title_splits(self, title_id: str) -> List[TitleSplit]:
        """Retrieves active licensor splits for a title."""
        with get_db_session() as session:
            title = self.title_repo.get_by_id(session, title_id.strip())
            if not title:
                raise EntityNotFoundError("Title", title_id)
            return self.title_repo.get_title_splits(session, title.title_id)
