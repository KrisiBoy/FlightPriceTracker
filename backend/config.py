"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "backend" / "data" / "flight_tracker.db"


class Settings(BaseSettings):
    """Runtime settings for the Flight Price Tracker backend."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"

    def normalized_database_url(self) -> str:
        """Return a SQLAlchemy-compatible database URL."""
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://") and "+psycopg" not in url:
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url
    app_env: str = "development"
    cors_origins: str = "*"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 168

    # Flight API (Step 2)
    flight_api_mode: str = "mock"
    rapidapi_key: str = ""
    serpapi_key: str = ""

    # Scheduler (Step 3) — comma-separated UTC hours, default 3 checks/day
    scheduler_hours: str = "8,14,20"
    scheduler_enabled: bool = True

    # Notifications (Step 4)
    notifications_enabled: bool = True
    email_provider: str = "auto"  # auto | resend | smtp
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    fcm_credentials_path: str = ""

    @property
    def is_development(self) -> bool:
        """Return True when running in development mode."""
        return self.app_env.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
