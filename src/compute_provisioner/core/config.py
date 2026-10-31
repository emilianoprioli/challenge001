from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="COMPUTE_",
        extra="ignore",
    )

    service_name: str = "Compute Provisioner"
    environment: str = "local"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://compute:compute@localhost:5432/compute"
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_pool_timeout_seconds: int = 10
    provider_url: str = "http://127.0.0.1:8001"
    provider_timeout_seconds: float = 3.0
    worker_poll_seconds: float = 30.0
    worker_max_attempts: int = 4
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        """Normalize provider URLs so SQLAlchemy uses the installed Psycopg 3 driver."""
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
