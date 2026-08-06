from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore"
    )

    PROJECT_NAME: str = "Tanisi ERP"

    DATABASE_URL: str = "postgresql+psycopg2://tanisi:tanisi@localhost:5432/tanisi_erp"

    SECRET_KEY: str = "dev-secret-key-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    CORS_ORIGINS: str = "http://localhost:5173"

    WHATSAPP_CLOUD_API_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_API_VERSION: str = "v20.0"
    # Set in Meta's App Dashboard webhook config to match this value, so GET verification succeeds.
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = "tanisi-whatsapp-webhook"

    PUBLIC_BASE_URL: str = "http://localhost:8000"

    UPLOAD_DIR: Path = Path(__file__).resolve().parents[2] / "uploads"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
