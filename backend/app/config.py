"""Centrale configuratie. Waarden komen uit omgevingsvariabelen of backend/.env.

API-sleutels worden uitsluitend server-side gelezen en nooit naar de browser gestuurd.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_prefix="VETERA_", extra="ignore"
    )

    data_dir: Path = PROJECT_DIR / "data"
    host: str = "127.0.0.1"
    port: int = 3000
    # Anthropic-sleutel mag ook als ANTHROPIC_API_KEY worden gezet.
    anthropic_api_key: str | None = None
    max_upload_mb: int = 50
    allow_remote_access: bool = False  # standaard alleen localhost
    # Online gebruik (bijv. Render): wachtwoord verplicht zodra allow_remote_access aan staat.
    app_password: str | None = None
    session_secret: str | None = None
    session_days: int = 30
    auto_monitor: bool = False  # in de cloud: server voert broncontroles zelf uit als de gebruiker "automatisch" kiest
    user_agent: str = "VeteraIntelligence/1.0 (lokale broncontrole; respecteert robots.txt)"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "vetera.db"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def imports_dir(self) -> Path:
        return self.data_dir / "imports"

    @property
    def logos_dir(self) -> Path:
        return self.data_dir / "logos"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def cloud(self) -> bool:
        return self.allow_remote_access

    def resolved_api_key(self) -> str | None:
        return self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or None

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.documents_dir, self.imports_dir, self.logos_dir,
                  self.reports_dir, self.backups_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
