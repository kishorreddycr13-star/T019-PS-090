"""
Database Initialization Script.
Creates all 20 relational tables and indices for the OTT Rights and Royalty Engine.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from database.connection import engine, init_database
from database.base import Base
import models  # Ensures all 20 models are registered with Base.metadata


def main() -> None:
    print("=" * 70)
    print("OTT Rights & Royalty Engine (PS-090) - Database Initializer")
    print(f"Target Dialect: {engine.dialect.name}")
    print(f"Database URL:   {engine.url}")
    print("=" * 70)

    # Initialize all tables
    init_database(engine)

    # Inspect created tables
    from sqlalchemy import inspect
    inspector = inspect(engine)
    table_names = sorted(inspector.get_table_names())

    print(f"\nSuccessfully verified {len(table_names)} database tables:")
    for idx, name in enumerate(table_names, start=1):
        cols = inspector.get_columns(name)
        fks = inspector.get_foreign_keys(name)
        pks = inspector.get_pk_constraint(name)
        pk_cols = pks.get("constrained_columns", [])
        print(f"  {idx:2d}. {name:<32} (Cols: {len(cols):2d}, PK: {','.join(pk_cols)}, FKs: {len(fks):2d})")

    print("\n[OK] Database schema initialized successfully.")


if __name__ == "__main__":
    main()
