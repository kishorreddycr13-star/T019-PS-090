"""
Base Repository Module.
Provides session context and common persistence patterns for SQLAlchemy 2.0 entities.
"""
from __future__ import annotations

from typing import Type, TypeVar, Generic, Optional, List, Any
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from database.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Generic repository providing core CRUD operations."""

    def __init__(self, model_class: Type[T]) -> None:
        self.model_class = model_class

    def get_by_id(self, session: Session, entity_id: Any) -> Optional[T]:
        """Retrieves a single entity by its primary key."""
        return session.get(self.model_class, entity_id)

    def list_all(self, session: Session, skip: int = 0, limit: int = 100) -> List[T]:
        """Lists entities with pagination."""
        stmt = select(self.model_class).offset(skip).limit(limit)
        return list(session.scalars(stmt).all())

    get_all = list_all

    def save(self, session: Session, entity: T) -> T:
        """Adds and persists an entity within the current session."""
        session.add(entity)
        session.flush()
        return entity

    def delete(self, session: Session, entity_id: Any) -> bool:
        """Deletes an entity by primary key if present."""
        entity = self.get_by_id(session, entity_id)
        if entity:
            session.delete(entity)
            session.flush()
            return True
        return False
