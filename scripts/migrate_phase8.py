"""
Migration script for Phase 8 Settlement schema additions.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "ott_engine.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    def add_col_if_missing(table, col, col_def):
        cursor.execute(f"PRAGMA table_info({table});")
        cols = [r[1] for r in cursor.fetchall()]
        if col not in cols:
            print(f"Adding {col} to {table}...")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def};")

    add_col_if_missing("monthly_settlements", "split_pct", "NUMERIC(6, 2) NOT NULL DEFAULT 100.00")
    add_col_if_missing("monthly_settlements", "mg_paid", "NUMERIC(18, 4) NOT NULL DEFAULT 0.0000")
    add_col_if_missing("monthly_settlements", "mg_balance", "NUMERIC(18, 4) NOT NULL DEFAULT 0.0000")
    add_col_if_missing("monthly_settlements", "cap_retained", "NUMERIC(18, 4) NOT NULL DEFAULT 0.0000")
    add_col_if_missing("monthly_settlements", "payable_before_tds", "NUMERIC(18, 4) NOT NULL DEFAULT 0.0000")
    add_col_if_missing("monthly_settlements", "tds_pct", "NUMERIC(6, 2) NOT NULL DEFAULT 10.00")

    conn.commit()
    conn.close()
    print("Phase 8 database schema migration successfully completed.")

if __name__ == "__main__":
    migrate()
