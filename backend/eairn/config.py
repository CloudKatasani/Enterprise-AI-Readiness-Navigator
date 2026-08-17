"""Runtime configuration for the EAIRN backend.

Everything that varies between environments lives here. Defaults are chosen so
that `uvicorn eairn.main:app` works on a laptop with zero external services:
SQLite on disk, no LLM key, no platform credentials.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = Path(__file__).resolve().parent / "seed"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EAIRN_", env_file=".env", extra="ignore")

    # Postgres is the production target; SQLite keeps local dev and CI dependency-free.
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'eairn.db'}"
    sql_echo: bool = False

    # Rubric that new assessments run against unless the caller pins a version.
    default_rubric_version: str = "2.0"

    # Findings below this confidence never influence a score; they queue for a
    # human reviewer instead (blueprint S13, rule 2).
    confidence_threshold: float = 0.80

    # Row-level sampling is off by default and is a separate, permission-gated
    # capability (blueprint S3 / S17). Flipping this alone is not enough --
    # per-dataset authorization records are still required.
    allow_row_sampling: bool = False

    # AI Advisor. Without a key the advisor falls back to deterministic,
    # evidence-grounded templates so the product is fully functional offline.
    anthropic_api_key: str | None = None
    advisor_model: str = "claude-opus-5"
    advisor_effort: str = "medium"
    advisor_max_tokens: int = 8000

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
