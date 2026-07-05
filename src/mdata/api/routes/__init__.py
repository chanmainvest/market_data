"""Route registration. Each module exposes a ``router`` (APIRouter)."""
from __future__ import annotations

from fastapi import FastAPI

from . import (
    bonds,
    earnings,
    fundflow,
    macro,
    prices,
    snapshot,
    sources,
    tickers,
)


def register(app: FastAPI) -> None:
    for module in (
        sources,
        tickers,
        prices,
        snapshot,
        macro,
        earnings,
        bonds,
        fundflow,
    ):
        app.include_router(module.router, prefix="/api")
