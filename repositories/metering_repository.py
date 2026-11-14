"""
Metering Repository Module.
Performs aggregations of consumption metrics grouped by Month, Territory, and Title.
Implements BR-10 aggregation requirements.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from database.connection import get_db_session
from models.viewership import QualifyingViewRecord, ViewEvent
from models.subscriber import SubscriberTier


class MeteringRepository:
    """Repository computing monthly title-wise and territory-wise consumption aggregations."""

    def __init__(self, session: Optional[Session] = None) -> None:
        self._session = session

    def aggregate_metrics_from_db(
        self,
        period_key: Optional[str] = None,
        territory_code: Optional[str] = None,
        title_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Queries qualifying view records from database, grouping by (period_key, territory_code, title_id).
        Returns aggregated counts, view hours, and ad impressions.
        """
        def _execute(session):
            stmt = select(
                QualifyingViewRecord.period_key,
                QualifyingViewRecord.territory_code,
                QualifyingViewRecord.title_id,
                func.count(QualifyingViewRecord.record_id).label("total_views"),
                func.sum(
                    case_expr := func.case(
                        (and_(QualifyingViewRecord.is_qualified == True, QualifyingViewRecord.playback_decision == "ALLOWED"), 1),  # noqa: E712
                        else_=0
                    )
                ).label("qualifying_views"),
                func.sum(
                    func.case(
                        (and_(QualifyingViewRecord.is_counted == True, QualifyingViewRecord.tier_id.like("%PREM%")), 1),
                        else_=0
                    )
                ).label("qualifying_premium_views"),
                func.sum(
                    func.case(
                        (and_(QualifyingViewRecord.is_counted == True, QualifyingViewRecord.tier_id.like("%FREE%")), 1),
                        else_=0
                    )
                ).label("qualifying_free_views"),
                func.sum(
                    func.case(
                        (and_(QualifyingViewRecord.is_counted == True, QualifyingViewRecord.tier_id.like("%PREM%")), QualifyingViewRecord.view_hours),
                        else_=Decimal("0.0000")
                    )
                ).label("premium_view_hours"),
                func.sum(
                    func.case(
                        (and_(QualifyingViewRecord.is_counted == True, QualifyingViewRecord.tier_id.like("%FREE%")), QualifyingViewRecord.ad_impressions),
                        else_=0
                    )
                ).label("free_ad_impressions"),
            ).group_by(
                QualifyingViewRecord.period_key,
                QualifyingViewRecord.territory_code,
                QualifyingViewRecord.title_id,
            )

            filters = []
            if period_key:
                filters.append(QualifyingViewRecord.period_key == period_key.strip())
            if territory_code:
                filters.append(QualifyingViewRecord.territory_code == territory_code.strip())
            if title_id:
                filters.append(QualifyingViewRecord.title_id == title_id.strip())
            if filters:
                stmt = stmt.filter(and_(*filters))

            stmt = stmt.order_by(
                QualifyingViewRecord.period_key.asc(),
                QualifyingViewRecord.territory_code.asc(),
                QualifyingViewRecord.title_id.asc(),
            )

            results = []
            for row in session.execute(stmt):
                raw_vh = row.premium_view_hours if row.premium_view_hours is not None else Decimal("0.0000")
                vh = Decimal(str(raw_vh)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                results.append({
                    "month": row.period_key,
                    "territory_id": row.territory_code,
                    "title_id": row.title_id,
                    "total_views": int(row.total_views or 0),
                    "qualifying_views": int(row.qualifying_views or 0),
                    "qualifying_premium_views": int(row.qualifying_premium_views or 0),
                    "qualifying_free_views": int(row.qualifying_free_views or 0),
                    "premium_view_hours": vh,
                    "free_ad_impressions": int(row.free_ad_impressions or 0),
                })
            return results

        if self._session:
            return _execute(self._session)
        with get_db_session() as session:
            return _execute(session)

    @staticmethod
    def aggregate_metrics_from_records(
        records: List[Dict[str, Any]],
        month: Optional[str] = None,
        territory_id: Optional[str] = None,
        title_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Pure in-memory aggregator used during pipeline evaluation or batch processing.
        Groups by (month, territory_id, title_id).
        """
        groups: Dict[tuple, Dict[str, Any]] = {}

        for r in records:
            # settlement_month or local month
            m = r.get("settlement_month") or r.get("month") or ""
            t = r.get("_territory_id") or r.get("territory_id") or ""
            ttl = r.get("_title_id") or r.get("title_id") or ""
            tier = (r.get("_tier") or r.get("tier") or "PREMIUM").upper()

            if month and m != month.strip():
                continue
            if territory_id and t != territory_id.strip():
                continue
            if title_id and ttl != title_id.strip():
                continue

            key = (m, t, ttl)
            if key not in groups:
                groups[key] = {
                    "month": m,
                    "territory_id": t,
                    "title_id": ttl,
                    "total_views": 0,
                    "qualifying_views": 0,
                    "qualifying_premium_views": 0,
                    "qualifying_free_views": 0,
                    "premium_view_hours": Decimal("0.0000"),
                    "free_ad_impressions": 0,
                }

            g = groups[key]
            g["total_views"] += 1

            is_qualifying = (
                r.get("qualifying") == "true" or
                r.get("is_qualifying") is True
            )
            is_counted = (
                r.get("counted") == "true" or
                r.get("is_counted") is True
            )
            decision = r.get("decision") or r.get("playback_decision") or "ALLOWED"

            if is_qualifying and decision == "ALLOWED":
                g["qualifying_views"] += 1

            if is_counted and decision == "ALLOWED":
                if "PREM" in tier:
                    g["qualifying_premium_views"] += 1
                    vh_val = r.get("view_hours", "0.0000")
                    g["premium_view_hours"] += Decimal(str(vh_val))
                elif "FREE" in tier or "AD" in tier:
                    g["qualifying_free_views"] += 1
                    ad_val = int(r.get("_ad_impressions") or r.get("ad_impressions") or 0)
                    g["free_ad_impressions"] += ad_val

        # Sort and quantize view hours
        results = []
        for key in sorted(groups.keys()):
            entry = groups[key]
            entry["premium_view_hours"] = entry["premium_view_hours"].quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            results.append(entry)

        return results
