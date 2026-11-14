"""
Migration script for Phase 6 View Tracking and Metering schema additions.
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

    add_col_if_missing("view_events", "ad_impressions", "INTEGER NOT NULL DEFAULT 0")
    add_col_if_missing("view_events", "ingested_utc", "DATETIME")

    add_col_if_missing("qualifying_view_records", "threshold_seconds", "INTEGER NOT NULL DEFAULT 120")
    add_col_if_missing("qualifying_view_records", "is_counted", "BOOLEAN NOT NULL DEFAULT 0")
    add_col_if_missing("qualifying_view_records", "view_hours", "NUMERIC(10, 4) NOT NULL DEFAULT 0.0000")
    add_col_if_missing("qualifying_view_records", "ad_impressions", "INTEGER NOT NULL DEFAULT 0")
    add_col_if_missing("qualifying_view_records", "tag", "VARCHAR(32) DEFAULT ''")
    add_col_if_missing("qualifying_view_records", "licence_id", "VARCHAR(36)")
    add_col_if_missing("qualifying_view_records", "playback_decision", "VARCHAR(16) NOT NULL DEFAULT 'ALLOWED'")
    add_col_if_missing("qualifying_view_records", "decision_reason", "VARCHAR(64) DEFAULT ''")
    add_col_if_missing("qualifying_view_records", "local_start_time", "DATETIME")

    conn.commit()
    conn.close()
    print("Phase 6 database schema migration successfully completed.")

if __name__ == "__main__":
    migrate()
