"""Application configuration, loaded from environment / .env file.

Mirrors the knowledge_base house style: pydantic-settings BaseSettings with
a computed db_url property and an lru_cache singleton.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_user: str = "mdata"
    postgres_password: str = "mdata"
    postgres_db: str = "mdata"

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    @property
    def db_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()
