"""SQLAlchemy engine + session helpers for the mdata service.

House style: raw ``text()`` SQL (no ORM duplication). Schema is owned by
docker/postgres/init.sql.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def engine() -> Engine:
    global _engine, _SessionFactory
    if _engine is None:
        _engine = create_engine(settings().db_url, pool_pre_ping=True, future=True)
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


@contextmanager
def session() -> Iterator[Session]:
    engine()
    sess = _SessionFactory()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


def test_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
