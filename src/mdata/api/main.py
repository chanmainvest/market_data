"""FastAPI application entrypoint.

All routes live under the ``/api`` prefix and are registered from the
``routes`` subpackage. CORS is wide-open for local development.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import routes  # noqa: F401  (registers routers on import)


def create_app() -> FastAPI:
    app = FastAPI(title="market_data API", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    routes.register(app)
    return app


app = create_app()
