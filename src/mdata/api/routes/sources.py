"""Source registry + freshness: GET /api/health, GET /api/sources."""
from __future__ import annotations

from fastapi import APIRouter

from ...db import engine, test_connection
from sqlalchemy import text

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "db": test_connection()}


# Mapping of (source name) -> (table, time column) used to compute freshness.
_SOURCE_TABLES = [
    ("yahoo_daily",         "raw_yahoo_daily",            "scraped_at"),
    ("yahoo_history",       "raw_yahoo_history",          "scraped_at"),
    ("yahoo_earnings",      "raw_yahoo_earnings",         "scraped_at"),
    ("alpha_vantage",       "raw_alpha_vantage_history",  "scraped_at"),
    ("macrotrends",         "raw_macrotrends_history",    "scraped_at"),
    ("eoddata",             "raw_eoddata_daily",          "scraped_at"),
    ("fred",                "raw_fred",                   "scraped_at"),
    ("finviz",              "raw_finviz_daily",           "scraped_at"),
    ("cpc",                 "raw_cpc",                    "scraped_at"),
    ("short_finra",         "raw_short_finra",            "scraped_at"),
    ("bonds_bi",            "raw_bonds_bi",               "scraped_at"),
    ("bonds_finra",         "raw_bonds_finra",            "scraped_at"),
    ("etfdb_fundflow",      "raw_etfdb_fundflow",         "scraped_at"),
    ("etfcom_fundflow",     "raw_etfcom_fundflow",        "scraped_at"),
    ("reconcile_prices",    "reconcile_price_history",    "reconciled_at"),
]


@router.get("/sources")
def sources() -> list[dict]:
    """Approximate row count per data source.

    Row counts are *approximate*. For TimescaleDB hypertables the parent
    table's ``reltuples`` is always 0 — the planner stats live on the chunk
    child tables — so we sum ``reltuples`` across the chunks via
    ``pg_inherits``. Exact ``count(*)`` on a 25M-row hypertable is too slow
    for a dashboard endpoint. ``last_scraped`` is omitted here to keep the
    endpoint fast (it would require an index on the timestamp column or a
    full scan); use the per-source detail endpoints for freshness.
    """
    out = []
    with engine().connect() as conn:
        for name, table, _ts_col in _SOURCE_TABLES:
            approx = conn.execute(
                text(
                    """
                    SELECT COALESCE(
                        (SELECT sum(c.reltuples)::bigint
                         FROM pg_class c
                         JOIN pg_inherits i ON c.oid = i.inhrelid
                         JOIN pg_class p ON p.oid = i.inhparent
                         WHERE p.relname = :t),
                        (SELECT reltuples::bigint FROM pg_class WHERE relname = :t),
                        0
                    )
                    """
                ),
                {"t": table},
            ).scalar()
            out.append({
                "source": name,
                "table": table,
                "rows": int(approx or 0),
                "rows_exact": False,
            })
    return out


@router.get("/sources/{source_name}")
def source_detail(source_name: str) -> dict:
    """Exact row count + last-scraped timestamp for a single source.

    This does a real ``count(*)`` + ``max(ts)`` so it's slower than the
    listing endpoint — call it only when you need precise freshness for one
    source.
    """
    match = next((s for s in _SOURCE_TABLES if s[0] == source_name), None)
    if not match:
        return {"error": f"unknown source '{source_name}'",
                "available": [s[0] for s in _SOURCE_TABLES]}
    _name, table, ts_col = match
    with engine().connect() as conn:
        row = conn.execute(
            text(f"SELECT count(*) AS n, max({ts_col}) AS last_ts FROM {table}")
        ).fetchone()
    return {
        "source": source_name,
        "table": table,
        "rows": int(row[0] or 0),
        "rows_exact": True,
        "last_scraped": str(row[1]) if row[1] else None,
    }
