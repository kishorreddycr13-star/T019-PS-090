"""
Database connection manager and session factory.
Configures SQLite foreign keys and WAL mode, and enables PostgreSQL pooling readiness.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, Engine
from sqlalchemy.orm import sessionmaker, Session

from config import settings
from database.base import Base

logger = logging.getLogger("ott_engine.database")


def _configure_sqlite(dbapi_connection, connection_record):
    """Enforces SQLite foreign key constraints and enables Write-Ahead Logging (WAL)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    cursor.close()


def create_db_engine(db_url: str = settings.database_url, echo: bool = settings.echo_sql) -> Engine:
    """Creates a configured SQLAlchemy Engine instance."""
    if db_url.startswith("sqlite"):
        engine = create_engine(
            db_url,
            echo=echo,
            connect_args={"check_same_thread": False}
        )
        event.listen(engine, "connect", _configure_sqlite)
    else:
        # PostgreSQL / Production configuration
        engine = create_engine(
            db_url,
            echo=echo,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_timeout=settings.pool_timeout_seconds,
            pool_pre_ping=True
        )
    return engine


engine = create_db_engine()
SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Provides a transactional database session context."""
    session: Session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Database transaction rolled back due to error: %s", exc)
        raise
    finally:
        session.close()


def init_database(target_engine: Engine = engine) -> None:
    """Creates all tables registered with declarative Base."""
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=target_engine)
    logger.info("Database schema initialized successfully.")


def drop_database(target_engine: Engine = engine) -> None:
    """Drops all tables. Intended for test environments only."""
    logger.warning("Dropping all database tables...")
    Base.metadata.drop_all(bind=target_engine)
    logger.info("All tables dropped.")
