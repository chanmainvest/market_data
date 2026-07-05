"""Bond screener results: GET /api/bonds?source=bi|finra&date=YYYY-MM-DD"""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from ...db import engine

router = APIRouter()


@router.get("/bonds")
def bonds(
    source: str = Query("bi", help="bi | finra"),
    date: str | None = Query(None, help="YYYY-MM-DD (defaults to latest available)"),
    limit: int = Query(500, ge=1, le=5000),
) -> dict:
    table = "raw_bonds_bi" if source == "bi" else "raw_bonds_finra"
    with engine().connect() as conn:
        if date is None:
            date_row = conn.execute(
                text(f"SELECT max(date) FROM {table}")
            ).scalar()
            date = str(date_row) if date_row else None
        if date is None:
            return {"source": source, "date": None, "count": 0, "items": []}
        rows = conn.execute(
            text(f"""SELECT date, payload FROM {table} WHERE date = :d LIMIT :limit"""),
            {"d": date, "limit": limit},
        ).mappings().all()
    return {"source": source, "date": date, "count": len(rows),
            "items": [dict(r) for r in rows]}
