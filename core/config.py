"""
CareerPilot — Configuration
============================
Single source of truth for all settings. Loaded from environment variables
or a .env file via pydantic-settings.

Usage
-----
>>> from core.config import settings
>>> print(settings.openai_api_key)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ───────────────────────────────────────────────────────────────────
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model name")
    ollama_base_url: str = Field(
        default="http://localhost:11434", description="Ollama server URL"
    )
    ollama_model: str = Field(default="llama3.1", description="Local Ollama model name")

    @property
    def use_ollama(self) -> bool:
        """Automatically fall back to Ollama when no OpenAI key is set."""
        return not self.openai_api_key

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./careerpilot.db",
        description="SQLAlchemy async database URL",
    )

    # ── Gmail ─────────────────────────────────────────────────────────────────
    gmail_credentials_path: str = Field(default="./credentials.json")
    gmail_token_path: str = Field(default="./token.json")

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    linkedin_email: str = Field(default="")
    linkedin_password: str = Field(default="")

    # ── Job Search ────────────────────────────────────────────────────────────
    target_roles: list[str] = Field(
        default=["Machine Learning Engineer", "AI Engineer"],
        description="Job titles to track",
    )
    target_locations: list[str] = Field(
        default=["Remote"],
        description="Target job locations",
    )
    max_daily_applications: int = Field(default=10, ge=1, le=50)

    # ── Predictor ─────────────────────────────────────────────────────────────
    min_fit_score: float = Field(default=65.0, ge=0.0, le=100.0)

    # ── Agent ─────────────────────────────────────────────────────────────────
    tracker_poll_interval: int = Field(
        default=3600, description="Seconds between Tracker job polls"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("target_roles", "target_locations", mode="before")
    @classmethod
    def parse_comma_list(cls, v: str | list[str]) -> list[str]:
        """Accept comma-separated strings or native lists."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings (singleton)."""
    return Settings()


# Module-level convenience alias
settings: Settings = get_settings()
