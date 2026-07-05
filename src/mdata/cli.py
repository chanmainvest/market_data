"""Typer CLI entrypoint: ``mdata serve``, ``mdata reconcile``, ``mdata init-db``."""
from __future__ import annotations

import typer
from pathlib import Path

app = typer.Typer(no_args_is_help=True, help="market_data service")


@app.command()
def serve(
    host: str = typer.Option(None, "--host", help="Bind host"),
    port: int = typer.Option(None, "--port", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes"),
) -> None:
    """Run the FastAPI backend via uvicorn."""
    import uvicorn
    from .config import settings

    s = settings()
    uvicorn.run(
        "mdata.api.main:app",
        host=host or s.api_host,
        port=port or s.api_port,
        reload=reload,
    )


@app.command()
def reconcile(
    ticker: str = typer.Option(None, "--ticker", help="Reconcile a single ticker"),
    batch_size: int = typer.Option(None, "--batch-size", help="Max tickers to process"),
) -> None:
    """Run the cross-source price-history reconciliation."""
    from .reconcile import main
    raise SystemExit(main(ticker=ticker, batch_size=batch_size))


@app.command(name="init-db")
def init_db() -> None:
    """Apply docker/postgres/init.sql to the configured database."""
    from .db import engine
    from sqlalchemy import text
    root = Path(__file__).resolve().parents[2]
    sql_path = root / "docker" / "postgres" / "init.sql"
    if not sql_path.exists():
        typer.echo(f"init.sql not found at {sql_path}", err=True)
        raise typer.Exit(1)
    sql = sql_path.read_text(encoding="utf-8")
    with engine().begin() as conn:
        conn.execute(text(sql))
    typer.echo(f"applied {sql_path}")


@app.command()
def ingest(
    source: str = typer.Argument("all", help="source name or 'all'"),
) -> None:
    """Bulk-ingest legacy scraped CSVs from the data/ submodule into Postgres."""
    from .ingest import main as ingest_main
    raise SystemExit(ingest_main(source))


if __name__ == "__main__":
    app()
