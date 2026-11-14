"""
Title and Title Split Models.
Covers Table 1: Titles and Co-Licensing Title Splits.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    Date,
    Numeric,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from database.base import Base, TimestampMixin


class Title(Base, TimestampMixin):
    """
    Table 1: Content Titles.
    Stores metadata: Title ID, Title Name, Runtime, Release Date, Content Category,
    and Theatrical/TV Premiere information.
    """
    __tablename__ = "titles"
    __table_args__ = (
        CheckConstraint("duration_seconds > 0", name="ck_title_duration_positive"),
        Index("idx_title_content_type", "content_type"),
    )

    title_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: f"TTL-{str(uuid.uuid4())[:8].upper()}"
    )
    title_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Primary title name"
    )
    content_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="FILM",
        comment="Content format / category: FILM, SERIES_EPISODE, DOCUMENTARY, MUSIC_VIDEO"
    )
    duration_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5400,
        comment="Runtime in seconds"
    )
    release_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Official public commercial release date"
    )
    theatrical_premiere: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Theatrical premiere date for 45-day holdback calculation"
    )
    tv_premiere: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="TV premiere date for 7-day holdback calculation"
    )
    isan_code: Mapped[Optional[str]] = mapped_column(
        String(48),
        unique=True,
        nullable=True,
        comment="International Standard Audiovisual Number (ISAN/EIDR)"
    )
    production_year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).year,
        comment="Production / completion year"
    )
    original_language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
        comment="Primary audio language code"
    )
    age_rating: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="Content advisory rating (e.g. PG-13, TV-MA, U/A 16+)"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )

    # Hybrid alias for backward compatibility
    @property
    def original_title(self) -> str:
        return self.title_name

    @original_title.setter
    def original_title(self, val: str) -> None:
        self.title_name = val

    @property
    def runtime_seconds(self) -> int:
        return self.duration_seconds

    @runtime_seconds.setter
    def runtime_seconds(self, val: int) -> None:
        self.duration_seconds = val

    # Relationships
    splits: Mapped[List["TitleSplit"]] = relationship(
        "TitleSplit",
        back_populates="title",
        cascade="all, delete-orphan"
    )
    windows: Mapped[List["LicenceWindow"]] = relationship(
        "LicenceWindow",
        back_populates="title",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Title(id='{self.title_id}', name='{self.title_name}', category='{self.content_type}')>"


class TitleSplit(Base, TimestampMixin):
    """
    Co-Licensor Splits for Titles.
    Stores multi-party licensor ownership splits for a single title.
    Enforces check constraints (0 < split_pct <= 100.00).
    """
    __tablename__ = "title_splits"
    __table_args__ = (
        CheckConstraint(
            "split_pct > 0 AND split_pct <= 100.00",
            name="ck_title_split_pct_range"
        ),
        UniqueConstraint("title_id", "licensor_id", name="uq_title_licensor_split"),
        Index("idx_title_split_title", "title_id"),
    )

    split_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    title_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("titles.title_id", ondelete="CASCADE"),
        nullable=False
    )
    licensor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("licensors.licensor_id", ondelete="CASCADE"),
        nullable=False
    )
    split_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Ownership percentage (e.g. 33.34 for 33.34%)"
    )

    # Relationships
    title: Mapped["Title"] = relationship("Title", back_populates="splits")
    licensor: Mapped["Licensor"] = relationship("Licensor")

    @property
    def split_percentage(self) -> Decimal:
        return self.split_pct

    @split_percentage.setter
    def split_percentage(self, val: Decimal | float | int) -> None:
        self.split_pct = Decimal(str(val))

    @validates("split_pct")
    def validate_split_pct(self, key: str, value: Decimal | float | int) -> Decimal:
        dec_val = Decimal(str(value))
        if dec_val <= Decimal("0.00") or dec_val > Decimal("100.00"):
            raise ValueError(f"Invalid split_pct {dec_val}%. Must be strictly between 0.01% and 100.00%.")
        return dec_val

    def __repr__(self) -> str:
        return f"<TitleSplit(title='{self.title_id}', licensor='{self.licensor_id}', pct={self.split_pct}%)>"
