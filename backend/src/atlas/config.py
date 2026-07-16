from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Atlas"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://atlas:atlas-local-password@localhost:5433/atlas"
    redis_url: str = "redis://localhost:6379/0"
    opensearch_url: str = "https://localhost:9200"
    opensearch_username: str = "admin"
    opensearch_password: str = Field(default="", repr=False)
    opensearch_verify_certs: bool = False
    opensearch_index_prefix: str = "atlas-documents"
    raw_store_path: Path = Field(
        default=Path("./data/raw"), validation_alias="ATLAS_RAW_STORE_PATH"
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:4173"],
        validation_alias="ATLAS_CORS_ORIGINS",
    )
    allow_private_networks: bool = Field(
        default=False, validation_alias="ATLAS_ALLOW_PRIVATE_NETWORKS"
    )
    log_level: str = Field(default="INFO", validation_alias="ATLAS_LOG_LEVEL")
    scheduler_poll_seconds: float = 1.0
    frontier_lease_seconds: int = 180
    robots_cache_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
