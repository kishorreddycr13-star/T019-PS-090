"""
Configuration module for OTT Content Licensing, Windowing, and Royalty Engine (PS-090).
Provides environment-aware database configuration, switching seamlessly between SQLite and PostgreSQL.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = BASE_DIR / "ott_engine.db"


@dataclass(frozen=True)
class DatabaseSettings:
    """Database connection and pooling parameters."""
    
    # Priority: DB_URL or DATABASE_URL env var -> SQLite default
    database_url: str = os.getenv(
        "DATABASE_URL", 
        f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"
    )
    echo_sql: bool = os.getenv("SQL_ECHO", "False").lower() in ("true", "1", "t")
    pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))
    max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    pool_timeout_seconds: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


settings = DatabaseSettings()
