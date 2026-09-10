"""Application configuration.

All configuration comes from environment variables (or a local ``.env`` file
during development). Nothing secret is ever hard-coded — that is a hard rule for
this project.

We use ``pydantic-settings`` because it:
  * reads env vars automatically (case-insensitive),
  * validates / coerces types (e.g. "true" -> bool, "a,b" -> list),
  * gives us one typed ``settings`` object to import everywhere.

Usage
-----
    from app.config import get_settings
    settings = get_settings()
    if settings.duffel_api_token:
        ...

``get_settings()`` is cached, so the ``.env`` file is only parsed once per
process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the ``backend/`` directory, used to locate bundled data files
# regardless of the current working directory.
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "app" / "data"


class Settings(BaseSettings):
    """Typed view over every environment variable the backend understands.

    Field names are lower_snake_case; the matching env var is the upper-case
    version (``duffel_api_token`` <- ``DUFFEL_API_TOKEN``). This is the default
    behaviour of pydantic-settings.
    """

    model_config = SettingsConfigDict(
        # Load a local .env if present. In production (Railway) there is no .env
        # file — the platform injects real environment variables instead.
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore unrelated env vars (Railway injects many)
    )

    # --- Core app --------------------------------------------------------
    app_env: str = Field(
        default="development",
        description="'development' or 'production'. Controls docs verbosity.",
    )

    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Front-end origins allowed to call the API.",
    )

    # --- Database -------------------------------------------------------
    database_url: str = Field(
        default=f"sqlite:///{DATA_DIR / 'local.sqlite3'}",
        description="SQLAlchemy database URL. SQLite locally, Postgres in prod.",
    )

    # --- Providers ----------------------------------------------------
    enabled_providers: list[str] = Field(
        default_factory=lambda: ["mock"],
        description="Provider keys to query, in priority order.",
    )

    # Duffel
    duffel_api_token: str = ""
    duffel_api_version: str = "v2"

    # Amadeus
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_hostname: str = "test.api.amadeus.com"

    # Kiwi / Tequila
    tequila_api_key: str = ""

    # Travelpayouts / Skyscanner affiliate
    travelpayouts_token: str = ""
    travelpayouts_marker: str = ""

    # --- Currency ---------------------------------------------------
    currency_provider: str = Field(
        default="er_api",
        description="'er_api' (open.er-api.com, no key) or 'exchangerate_host'.",
    )
    exchangerate_host_access_key: str = ""

    # --- Alerts ---------------------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "alerts@flight-scheduler.local"
    alerts_cron_secret: str = ""

    # ------------------------------------------------------------------
    # Validators: turn comma-separated strings into lists. This lets the
    # same value work whether it is set as `A,B,C` (Railway UI) or as a JSON
    # array. pydantic-settings would otherwise try to JSON-decode list fields.
    # ------------------------------------------------------------------
    @field_validator("cors_allow_origins", "enabled_providers", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            # Allow "a, b ,c" and ignore empty segments.
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env.lower().startswith("prod")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so the ``.env`` file is only read once. Tests can call
    ``get_settings.cache_clear()`` if they need to reload with patched env vars.
    """
    return Settings()
