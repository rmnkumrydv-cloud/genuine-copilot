"""Runtime configuration (env-driven, with safe offline defaults).

The deterministic core needs none of these set. Tokens/keys only unlock the
network-facing paths (GitHub API auth, the Groq explainer).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = parent of the `genuine` package dir.
ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- GitHub ingestion (optional auth) ---
    github_token: str = Field(default="", alias="GITHUB_TOKEN")

    # --- LLM explainer (Gate 5; template fallback used when empty) ---
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")

    # --- Storage ---
    db_path: str = Field(default="data/genuine.sqlite", alias="GENUINE_DB_PATH")
    clone_cache: str = Field(default="data/clones", alias="GENUINE_CLONE_CACHE")

    @property
    def db_file(self) -> Path:
        p = (ROOT / self.db_path) if not Path(self.db_path).is_absolute() else Path(self.db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def clone_dir(self) -> Path:
        p = (ROOT / self.clone_cache) if not Path(self.clone_cache).is_absolute() else Path(self.clone_cache)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def has_github_auth(self) -> bool:
        return bool(self.github_token.strip())

    @property
    def has_llm(self) -> bool:
        return bool(self.groq_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
