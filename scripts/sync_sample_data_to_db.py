"""
Sync Official Sample Data to Relational SQLite/PostgreSQL Database.
Loads territories.csv, licensors.csv, titles.csv, licences.csv, windows, and splits
into the relational database to satisfy foreign keys and enable full relational querying.
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_db_session
from models.territory import Territory
from models.licensor import Licensor
from models.title import Title
from models.contract import LicenceContract
from models.window import LicenceWindow
from models.licensor import LicensorSplit


def sync_sample_data(data_dir: Path) -> None:
    print(f"Syncing sample data from {data_dir} to database...")

    with get_db_session() as session:
        # 1. Territories
        terr_file = data_dir / "territories.csv"
        if terr_file.exists():
            with open(terr_file, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    tid = r["territory_id"]
                    t = session.get(Territory, tid)
                    if not t:
                        t = Territory(
                            country_code=tid,
                            country_name=r.get("territory_name", tid),
                            default_currency="INR" if tid == "IN" else ("USD" if tid == "US" else ("SGD" if tid == "SG" else "AED")),
                            primary_iana_timezone="Asia/Kolkata" if tid == "IN" else ("America/New_York" if tid == "US" else ("Asia/Singapore" if tid == "SG" else "Asia/Dubai")),
                            is_sanctioned=False,
                            is_active=True,
                        )
                        session.add(t)
            session.flush()

        # 2. Licensors
        lic_file = data_dir / "licensors.csv"
        if lic_file.exists():
            with open(lic_file, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    lid = r["licensor_id"]
                    lic = session.get(Licensor, lid)
                    is_ind = r.get("is_indian", "").lower() == "true"
                    c_code = "IN" if is_ind else "US"
                    treaty_str = r.get("treaty_tds_pct", "").strip()
                    treaty_tds = Decimal(treaty_str) if treaty_str else None

                    if not lic:
                        lic = Licensor(
                            licensor_id=lid,
                            legal_name=r.get("licensor_name", lid),
                            country=r.get("country", "India" if is_ind else "United States"),
                            country_code=c_code,
                            is_indian=is_ind,
                            treaty_tds_pct=treaty_tds,
                            is_active=True,
                        )
                        session.add(lic)
                    else:
                        lic.is_indian = is_ind
                        lic.treaty_tds_pct = treaty_tds
            session.flush()

        # 3. Titles
        titles_file = data_dir / "titles.csv"
        if titles_file.exists():
            with open(titles_file, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    tid = r["title_id"]
                    t = session.get(Title, tid)
                    t_prem = r.get("theatrical_premiere", "").strip()
                    tv_prem = r.get("tv_premiere", "").strip()
                    theat_d = date.fromisoformat(t_prem) if t_prem else None
                    tv_d = date.fromisoformat(tv_prem) if tv_prem else None

                    if not t:
                        t = Title(
                            title_id=tid,
                            title_name=r.get("title_name", tid),
                            content_type=r.get("content_type", "FILM"),
                            duration_seconds=int(r.get("runtime_seconds", 3600)),
                            theatrical_premiere=theat_d,
                            tv_premiere=tv_d,
                            is_active=True,
                        )
                        session.add(t)
            session.flush()

        # 4. Licences
        licences_file = data_dir / "licences.csv"
        if licences_file.exists():
            with open(licences_file, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    cid = r["licence_id"]
                    contract = session.get(LicenceContract, cid)
                    if not contract:
                        contract = LicenceContract(
                            contract_id=cid,
                            contract_number=f"CN-{cid}",
                            title_id=r["title_id"],
                            licensor_id=r["licensor_id"],
                            territory_id=r["territory_id"],
                            exclusivity=r.get("exclusivity", "NON_EXCLUSIVE"),
                            revenue_share_type=r.get("revenue_share_type", "POOL_AND_AD"),
                            mg_amount=Decimal(r.get("mg_amount", "0.00")),
                            cap_amount=Decimal(r.get("cap_amount", "0.00")),
                            effective_date=date(2026, 1, 1),
                            expiration_date=date(2027, 12, 31),
                            contract_currency="INR",
                            status="ACTIVE",
                        )
                        session.add(contract)
            session.flush()

        # 5. Windows
        win_file = data_dir / "licence_windows.csv"
        if win_file.exists():
            with open(win_file, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    cid = r["licence_id"]
                    wno = int(r.get("window_no", 1))
                    w_id = f"WIN-{cid}-{wno}"
                    win = session.get(LicenceWindow, w_id)
                    lic = session.get(LicenceContract, cid)
                    if not win and lic:
                        s_d = date.fromisoformat(r["window_start"])
                        e_d = date.fromisoformat(r["window_end"])
                        win = LicenceWindow(
                            window_id=w_id,
                            contract_id=cid,
                            title_id=lic.title_id,
                            territory_code=lic.territory_id,
                            window_no=wno,
                            window_type="SVOD",
                            window_start=s_d,
                            window_end=e_d,
                            start_time_utc=datetime(s_d.year, s_d.month, s_d.day, 0, 0, 0),
                            end_time_utc=datetime(e_d.year, e_d.month, e_d.day, 23, 59, 59),
                            status="ACTIVE",
                        )
                        session.add(win)
            session.flush()

        session.commit()
        print("[SUCCESS] All sample data master entities synced to database.")


if __name__ == "__main__":
    d_dir = Path(__file__).resolve().parent.parent / "sample_data"
    sync_sample_data(d_dir)
