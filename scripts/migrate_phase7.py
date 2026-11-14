"""
Phase 7 Migration Script.
Creates title_shares table in the relational database.
"""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import engine
from database.base import Base
import models

def migrate():
    print("Migrating database for Phase 7 (Title Share Records)...")
    models.TitleShareRecord.__table__.create(engine, checkfirst=True)
    print("Successfully created/verified 'title_shares' table.")

if __name__ == "__main__":
    migrate()
