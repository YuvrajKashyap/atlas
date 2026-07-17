import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from atlas.enums import (
    ChangeKind,
    CrawlRunStatus,
    FetchOutcome,
    FrontierStatus,
    IncidentStatus,
    IndexBuildStatus,
    PipelineTaskStatus,
    PipelineTaskType,
)


class AllowedDomainInput(BaseModel):
    domain: str
    include_subdomains: bool = True


class CrawlRunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    seeds: list[str] = Field(min_length=1, max_length=20)
    allowed_domains: list[AllowedDomainInput] = Field(min_length=1, max_length=20)
    max_pages: int = Field(default=100, ge=1, le=100_000)
    max_depth: int = Field(default=2, ge=0, le=10)
    per_domain_delay_ms: int = Field(default=1000, ge=250, le=60_000)
    request_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    max_response_bytes: int = Field(default=2_000_000, ge=64_000, le=10_000_000)
    max_redirects: int = Field(default=5, ge=0, le=10)
    max_retries: int = Field(default=3, ge=0, le=8)
    max_duration_seconds: int = Field(default=3600, ge=60, le=86_400)
    global_concurrency: int = Field(default=20, ge=1, le=200)
    per_domain_concurrency: int = Field(default=1, ge=1, le=8)
    allowed_content_types: list[str] = Field(
        default_factory=lambda: ["text/html", "application/xhtml+xml"], min_length=1, max_length=10
    )
    allowed_ports: list[int] = Field(default_factory=lambda: [80, 443], min_length=1, max_length=4)
    user_agent: str = Field(
        default="AtlasBot/0.1 (+https://github.com/atlas-crawler)",
        min_length=8,
        max_length=255,
    )

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Run name cannot be blank")
        return stripped

    @field_validator("seeds")
    @classmethod
    def unique_seeds(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Seed URLs must be unique")
        return value

    @field_validator("allowed_ports")
    @classmethod
    def safe_ports(cls, value: list[int]) -> list[int]:
        if any(port not in {80, 443} for port in value):
            raise ValueError("Atlas only permits ports 80 and 443")
        return sorted(set(value))

    @field_validator("allowed_content_types")
    @classmethod
    def html_content_types(cls, value: list[str]) -> list[str]:
        normalized = sorted({item.split(";", 1)[0].strip().lower() for item in value})
        permitted = {"text/html", "application/xhtml+xml"}
        if not normalized or not set(normalized).issubset(permitted):
            raise ValueError("Atlas currently supports HTML and XHTML only")
        return normalized


class RunCounters(BaseModel):
    discovered: int = 0
    queued: int = 0
    fetching: int = 0
    indexed: int = 0
    failed: int = 0
    blocked: int = 0
    duplicates: int = 0
    retries: int = 0
    documents: int = 0


class CrawlRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    definition_id: uuid.UUID | None
    generation: int
    name: str
    status: CrawlRunStatus
    max_pages: int
    max_depth: int
    per_domain_delay_ms: int
    request_timeout_seconds: float
    max_response_bytes: int
    max_redirects: int
    max_retries: int
    max_duration_seconds: int
    global_concurrency: int
    per_domain_concurrency: int
    allowed_content_types: list[str]
    allowed_ports: list[int]
    user_agent: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    stop_requested_at: datetime | None
    seeds: list[str]
    allowed_domains: list[AllowedDomainInput]
    counters: RunCounters


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[dict[str, object]]


class FrontierEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    url: str
    normalized_url: str
    host: str
    status: FrontierStatus
    priority: int
    depth: int
    discovered_from_id: uuid.UUID | None
    first_seen_at: datetime
    next_fetch_at: datetime | None
    last_crawled_at: datetime | None
    retry_count: int
    fetch_attempt_count: int
    robots_allowed: bool | None
    blocked_reason: str | None
    last_error_type: str | None
    last_error_message: str | None


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    frontier_entry_id: uuid.UUID
    fetch_attempt_id: uuid.UUID
    resource_id: uuid.UUID | None
    previous_version_id: uuid.UUID | None
    version_number: int
    is_current: bool
    change_kind: ChangeKind
    url: str
    canonical_url: str
    host: str
    title: str | None
    description: str | None
    language: str | None
    headings: list[str]
    main_text: str
    text_length: int
    content_hash: str
    simhash: str | None
    simhash_bands: list[int]
    duplicate_cluster_id: uuid.UUID | None
    duplicate_of_document_id: uuid.UUID | None
    extraction_confidence: float
    parser_name: str
    parser_version: str
    extraction_warnings: list[str]
    extracted_at: datetime
    indexed_at: datetime | None
    index_name: str | None


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    frontier_entry_id: uuid.UUID
    resource_id: uuid.UUID | None
    previous_version_id: uuid.UUID | None
    version_number: int
    is_current: bool
    change_kind: ChangeKind
    url: str
    canonical_url: str
    host: str
    title: str | None
    description: str | None
    language: str | None
    text_length: int
    content_hash: str
    simhash: str | None
    duplicate_cluster_id: uuid.UUID | None
    duplicate_of_document_id: uuid.UUID | None
    extraction_confidence: float
    parser_name: str
    parser_version: str
    extraction_warnings: list[str]
    extracted_at: datetime
    indexed_at: datetime | None
    index_name: str | None


class FetchAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    frontier_entry_id: uuid.UUID
    attempt_number: int
    started_at: datetime
    finished_at: datetime | None
    outcome: FetchOutcome | None
    status_code: int | None
    final_url: str | None
    redirect_chain: list[dict[str, object]]
    content_type: str | None
    response_size_bytes: int | None
    latency_ms: float | None
    response_headers: dict[str, str]
    error_type: str | None
    error_message: str | None
    raw_body_key: str | None
    body_sha256: str | None


class ExtractionAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    fetch_attempt_id: uuid.UUID
    document_id: uuid.UUID | None
    parser_name: str
    parser_version: str
    succeeded: bool
    promoted: bool
    confidence: float | None
    text_length: int | None
    warnings: list[str]
    duration_ms: float | None
    error_type: str | None
    error_message: str | None
    created_at: datetime


class CrawlEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: uuid.UUID
    frontier_entry_id: uuid.UUID | None
    event_type: str
    payload: dict[str, object]
    created_at: datetime


class MetricsOverview(BaseModel):
    run_id: uuid.UUID
    counters: RunCounters
    throughput_per_minute: float
    fetch_latency_p50_ms: float | None
    fetch_latency_p95_ms: float | None
    parser_success_rate: float | None
    duplicate_rate: float | None
    http_statuses: dict[str, int]
    frontier_statuses: dict[str, int]
    active_domains: int
    recent_events: list[CrawlEventRead]


class CrawlDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    schedule_cron: str | None = Field(default=None, max_length=120)
    schedule_timezone: str = Field(default="UTC", min_length=1, max_length=80)
    config: CrawlRunCreate


class CrawlDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    enabled: bool
    schedule_cron: str | None
    schedule_timezone: str
    next_run_at: datetime | None
    config: dict[str, object]
    created_at: datetime
    updated_at: datetime


class PipelineTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    frontier_entry_id: uuid.UUID
    task_type: PipelineTaskType
    status: PipelineTaskStatus
    generation: int
    attempt_count: int
    max_attempts: int
    available_at: datetime
    lease_owner: str | None
    lease_expires_at: datetime | None
    last_heartbeat_at: datetime | None
    payload: dict[str, object]
    last_error_type: str | None
    last_error_message: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    worker_id: str
    queues: list[str]
    version: str
    current_task_id: uuid.UUID | None
    started_at: datetime
    last_seen_at: datetime
    details: dict[str, object]


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID | None
    status: IncidentStatus
    severity: str
    incident_type: str
    title: str
    details: dict[str, object]
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IndexBuildRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: IndexBuildStatus
    schema_version: int
    physical_index: str | None
    expected_documents: int
    indexed_documents: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
