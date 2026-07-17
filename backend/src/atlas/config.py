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
        populate_by_name=True,
    )

    app_name: str = "Atlas"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://atlas:atlas-local-password@localhost:5433/atlas"
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = Field(default="", validation_alias="ATLAS_REDIS_PASSWORD", repr=False)
    opensearch_url: str = "https://localhost:9200"
    opensearch_username: str = "admin"
    opensearch_password: str = Field(default="", repr=False)
    opensearch_verify_certs: bool = False
    opensearch_aws_region: str = Field(default="", validation_alias="ATLAS_OPENSEARCH_AWS_REGION")
    opensearch_index_prefix: str = "atlas-documents"
    raw_store_path: Path = Field(
        default=Path("./data/raw"), validation_alias="ATLAS_RAW_STORE_PATH"
    )
    blob_store_backend: str = Field(default="local", validation_alias="ATLAS_BLOB_STORE_BACKEND")
    s3_bucket: str = Field(default="", validation_alias="ATLAS_S3_BUCKET")
    s3_prefix: str = Field(default="raw", validation_alias="ATLAS_S3_PREFIX")
    s3_kms_key_id: str = Field(default="", validation_alias="ATLAS_S3_KMS_KEY_ID")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:4173"],
        validation_alias="ATLAS_CORS_ORIGINS",
    )
    allow_private_networks: bool = Field(
        default=False, validation_alias="ATLAS_ALLOW_PRIVATE_NETWORKS"
    )
    log_level: str = Field(default="INFO", validation_alias="ATLAS_LOG_LEVEL")
    scheduler_poll_seconds: float = Field(
        default=0.1,
        ge=0.05,
        validation_alias="ATLAS_SCHEDULER_POLL_SECONDS",
    )
    scheduler_maintenance_seconds: float = Field(
        default=30,
        ge=1,
        validation_alias="ATLAS_SCHEDULER_MAINTENANCE_SECONDS",
    )
    frontier_lease_seconds: int = 180
    task_lease_seconds: int = 300
    task_heartbeat_seconds: int = 30
    robots_cache_hours: int = 24
    auth_mode: str = Field(default="disabled", validation_alias="ATLAS_AUTH_MODE")
    oidc_issuer: str = Field(default="", validation_alias="ATLAS_OIDC_ISSUER")
    oidc_audience: str = Field(default="", validation_alias="ATLAS_OIDC_AUDIENCE")
    oidc_jwks_url: str = Field(default="", validation_alias="ATLAS_OIDC_JWKS_URL")
    oidc_admin_group: str = Field(default="atlas-admin", validation_alias="ATLAS_OIDC_ADMIN_GROUP")
    oidc_viewer_group: str = Field(
        default="atlas-viewer", validation_alias="ATLAS_OIDC_VIEWER_GROUP"
    )
    cognito_domain: str = Field(default="", validation_alias="ATLAS_COGNITO_DOMAIN")
    cognito_client_id: str = Field(default="", validation_alias="ATLAS_COGNITO_CLIENT_ID")
    rate_limit_per_minute: int = 120
    metrics_sample_seconds: int = 15
    prometheus_endpoint_enabled: bool = Field(
        default=True, validation_alias="ATLAS_PROMETHEUS_ENDPOINT_ENABLED"
    )
    otlp_endpoint: str = Field(default="", validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
