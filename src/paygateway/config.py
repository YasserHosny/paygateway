from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database (Supabase PostgreSQL)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:[YOUR-PASSWORD]@db.thwjbagnrcasioiymlsi.supabase.co:5432/postgres"
    DATABASE_URL_SYNC: str = "postgresql://postgres:[YOUR-PASSWORD]@db.thwjbagnrcasioiymlsi.supabase.co:5432/postgres"
    DATABASE_SSL: bool = True

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Stripe
    STRIPE_SECRET_KEY: str
    STRIPE_PUBLISHABLE_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    STRIPE_API_VERSION: str = "2026-05-27.dahlia"

    # JWT
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:4200,http://localhost:3000"

    # Security
    API_KEY_SALT: str = "dev-salt-change-in-production"

    # App
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: str = "INFO"

    # Idempotency
    IDEMPOTENCY_KEY_TTL_HOURS: int = 24

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def _reset_settings() -> None:
    global _settings
    _settings = None
