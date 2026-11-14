"""
Licensor Repository Module.
Handles persistence and queries for studios, distributors, and content rights holders.
"""
from __future__ import annotations

from typing import List, Optional
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from models.licensor import Licensor
from repositories.base_repository import BaseRepository


class LicensorRepository(BaseRepository[Licensor]):
    """Data access repository for Licensor entities."""

    def __init__(self) -> None:
        super().__init__(Licensor)

    def search(
        self,
        session: Session,
        query: Optional[str] = None,
        country: Optional[str] = None,
        is_indian: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Licensor]:
        """Searches licensors by ID, name substring, country of domicile, and domestic residency flag."""
        stmt = select(Licensor)

        if query and query.strip():
            q_term = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    Licensor.licensor_id.ilike(q_term),
                    Licensor.legal_name.ilike(q_term),
                    Licensor.trade_name.ilike(q_term),
                )
            )

        if country and country.strip():
            c_term = f"%{country.strip()}%"
            stmt = stmt.where(
                or_(
                    Licensor.country.ilike(c_term),
                    Licensor.country_code.ilike(c_term),
                )
            )

        if is_indian is not None:
            stmt = stmt.where(Licensor.is_indian == is_indian)

        stmt = stmt.order_by(Licensor.licensor_id).offset(skip).limit(limit)
        return list(session.scalars(stmt).all())
