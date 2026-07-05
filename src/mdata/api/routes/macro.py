"""Macro / sentiment: FRED series + CBOE put-call ratio + short volume."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from ...db import engine

router = APIRouter()


@router.get("/fred")
def fred_series(
    series_id: str = Query(..., description="FRED series id, e.g. WALCL"),
    limit: int = Query(5000, ge=1, le=50000),
) -> dict:
    with engine().connect() as conn:
        meta = conn.execute(
            text("SELECT * FROM ref_fred_series WHERE series_id = :s"),
            {"s": series_id},
        ).mappings().first()
        rows = conn.execute(
            text("""SELECT date, value FROM raw_fred WHERE series_id = :s
                    ORDER BY date LIMIT :limit"""),
            {"s": series_id, "limit": limit},
        ).fetchall()
    return {
        "series_id": series_id,
        "description": dict(meta).get("description") if meta else None,
        "count": len(rows),
        "rows": [{"date": str(r[0]), "value": r[1]} for r in rows],
    }


@router.get("/cpc/{category}")
def cpc(
    category: str,
    limit: int = Query(2000, ge=1, le=20000),
) -> dict:
    """CBOE put-call ratio for a category: total|index|etp|equity|vix|spx|oex"""
    with engine().connect() as conn:
        rows = conn.execute(
            text("""SELECT * FROM raw_cpc WHERE category = :c ORDER BY date LIMIT :limit"""),
            {"c": category, "limit": limit},
        ).mappings().all()
    return {"category": category, "count": len(rows), "rows": [dict(r) for r in rows]}


@router.get("/shortvolume")
def short_volume(
    date: str = Query(..., description="YYYY-MM-DD"),
    limit: int = Query(5000, ge=1, le=50000),
) -> dict:
    with engine().connect() as conn:
        rows = conn.execute(
            text("""SELECT * FROM raw_short_finra WHERE date = :d
                    ORDER BY total_volume DESC NULLS LAST LIMIT :limit"""),
            {"d": date, "limit": limit},
        ).mappings().all()
    return {"date": date, "count": len(rows), "rows": [dict(r) for r in rows]}
