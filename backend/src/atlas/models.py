import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from atlas.enums import (
    ChangeKind,
    CrawlRunStatus,
    FetchOutcome,
    FrontierStatus,
    IncidentStatus,
    IndexBuildStatus,
    IndexOperationStatus,
    ObservationOutcome,
    PipelineTaskStatus,
    PipelineTaskType,
)


def _crawl_run_status_values(enum_type: type[CrawlRunStatus]) -> list[str]:
    return [member.value for member in enum_type]


def _frontier_status_values(enum_type: type[FrontierStatus]) -> list[str]:
    return [member.value for member in enum_type]


def _fetch_outcome_values(enum_type: type[FetchOutcome]) -> list[str]:
    return [member.value for member in enum_type]


def _enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_type]


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CrawlDefinition(TimestampMixin, Base):
    __tablename__ = "crawl_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    schedule_cron: Mapped[str | None] = mapped_column(String(120))
    schedule_timezone: Mapped[str] = mapped_column(String(80), default="UTC", nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class CrawlRun(TimestampMixin, Base):
    __tablename__ = "crawl_runs"
    __table_args__ = (
        CheckConstraint("max_pages > 0", name="ck_crawl_runs_max_pages_positive"),
        CheckConstraint("max_depth >= 0", name="ck_crawl_runs_max_depth_nonnegative"),
        CheckConstraint("per_domain_delay_ms >= 250", name="ck_crawl_runs_polite_delay"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_definitions.id", ondelete="SET NULL"), index=True
    )
    generation: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[CrawlRunStatus] = mapped_column(
        Enum(
            CrawlRunStatus,
            name="crawl_run_status",
            values_callable=_crawl_run_status_values,
        ),
        default=CrawlRunStatus.DRAFT,
        nullable=False,
        index=True,
    )
    max_pages: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_depth: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    per_domain_delay_ms: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    request_timeout_seconds: Mapped[float] = mapped_column(Float, default=15.0, nullable=False)
    max_response_bytes: Mapped[int] = mapped_column(Integer, default=2_000_000, nullable=False)
    max_redirects: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_duration_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    global_concurrency: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    per_domain_concurrency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    allowed_content_types: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: ["text/html", "application/xhtml+xml"], nullable=False
    )
    allowed_ports: Mapped[list[int]] = mapped_column(
        JSONB, default=lambda: [80, 443], nullable=False
    )
    user_agent: Mapped[str] = mapped_column(
        String(255), default="AtlasBot/0.1 (+https://github.com/atlas-crawler)", nullable=False
    )
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrawlSeed(Base):
    __tablename__ = "crawl_seeds"
    __table_args__ = (UniqueConstraint("run_id", "normalized_url", name="uq_seed_run_url"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AllowedDomain(Base):
    __tablename__ = "allowed_domains"
    __table_args__ = (UniqueConstraint("run_id", "domain", name="uq_allowed_domain_run"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    include_subdomains: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DomainState(TimestampMixin, Base):
    __tablename__ = "domain_states"
    __table_args__ = (UniqueConstraint("run_id", "host", name="uq_domain_state_run_host"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    host: Mapped[str] = mapped_column(String(253), nullable=False)
    robots_url: Mapped[str | None] = mapped_column(Text)
    robots_status_code: Mapped[int | None] = mapped_column(Integer)
    robots_body: Mapped[str | None] = mapped_column(Text)
    robots_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    robots_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    robots_error: Mapped[str | None] = mapped_column(Text)
    sitemaps_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sitemap_url_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    crawl_delay_ms: Mapped[int | None] = mapped_column(Integer)
    next_allowed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class FrontierEntry(TimestampMixin, Base):
    __tablename__ = "frontier_entries"
    __table_args__ = (
        UniqueConstraint("run_id", "normalized_url", name="uq_frontier_run_normalized_url"),
        CheckConstraint("depth >= 0", name="ck_frontier_depth_nonnegative"),
        Index("ix_frontier_scheduler", "run_id", "status", "next_fetch_at", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    status: Mapped[FrontierStatus] = mapped_column(
        Enum(
            FrontierStatus,
            name="frontier_status",
            values_callable=_frontier_status_values,
        ),
        default=FrontierStatus.DISCOVERED,
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discovered_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("frontier_entries.id", ondelete="SET NULL")
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    next_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    rq_job_id: Mapped[str | None] = mapped_column(String(255))
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fetch_attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    robots_allowed: Mapped[bool | None] = mapped_column(Boolean)
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    last_error_type: Mapped[str | None] = mapped_column(String(120))
    last_error_message: Mapped[str | None] = mapped_column(Text)


class FetchAttempt(Base):
    __tablename__ = "fetch_attempts"
    __table_args__ = (
        UniqueConstraint("frontier_entry_id", "attempt_number", name="uq_fetch_attempt_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frontier_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frontier_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[FetchOutcome | None] = mapped_column(
        Enum(
            FetchOutcome,
            name="fetch_outcome",
            values_callable=_fetch_outcome_values,
        )
    )
    status_code: Mapped[int | None] = mapped_column(Integer, index=True)
    final_url: Mapped[str | None] = mapped_column(Text)
    redirect_chain: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    content_type: Mapped[str | None] = mapped_column(String(255))
    response_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    response_headers: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    request_headers: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_body_key: Mapped[str | None] = mapped_column(Text)
    body_sha256: Mapped[str | None] = mapped_column(String(64))


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("fetch_attempt_id", name="uq_document_fetch_attempt"),
        Index("ix_documents_run_content_hash", "run_id", "content_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frontier_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frontier_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fetch_attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fetch_attempts.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("web_resources.id", ondelete="CASCADE"), index=True
    )
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    change_kind: Mapped[ChangeKind] = mapped_column(
        Enum(ChangeKind, name="change_kind", values_callable=_enum_values),
        default=ChangeKind.INITIAL,
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(32), index=True)
    headings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    main_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_length: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    simhash: Mapped[str | None] = mapped_column(String(16), index=True)
    simhash_bands: Mapped[list[int]] = mapped_column(JSONB, default=list, nullable=False)
    duplicate_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("duplicate_clusters.id", ondelete="SET NULL"), index=True
    )
    duplicate_of_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    parser_name: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    extraction_warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    index_name: Mapped[str | None] = mapped_column(String(255))


class DiscoveredLink(Base):
    __tablename__ = "discovered_links"
    __table_args__ = (
        UniqueConstraint(
            "source_frontier_id", "normalized_target_url", name="uq_discovered_link_source_target"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_frontier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frontier_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_target_url: Mapped[str] = mapped_column(Text, nullable=False)
    target_frontier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("frontier_entries.id", ondelete="SET NULL")
    )
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CrawlEvent(Base):
    __tablename__ = "crawl_events"
    __table_args__ = (Index("ix_crawl_events_run_created", "run_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frontier_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("frontier_entries.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PipelineTask(TimestampMixin, Base):
    __tablename__ = "pipeline_tasks"
    __table_args__ = (
        UniqueConstraint(
            "frontier_entry_id", "task_type", "generation", name="uq_pipeline_task_stage"
        ),
        Index("ix_pipeline_tasks_scheduler", "status", "available_at", "task_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frontier_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frontier_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_type: Mapped[PipelineTaskType] = mapped_column(
        Enum(PipelineTaskType, name="pipeline_task_type", values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    status: Mapped[PipelineTaskStatus] = mapped_column(
        Enum(PipelineTaskStatus, name="pipeline_task_status", values_callable=_enum_values),
        default=PipelineTaskStatus.READY,
        nullable=False,
        index=True,
    )
    generation: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rq_job_id: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    last_error_type: Mapped[str | None] = mapped_column(String(120))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DomainLease(Base):
    __tablename__ = "domain_leases"
    __table_args__ = (Index("ix_domain_leases_host_expiry", "run_id", "host", "expires_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_tasks.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    host: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    lease_token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WebResource(TimestampMixin, Base):
    __tablename__ = "web_resources"
    __table_args__ = (
        UniqueConstraint("definition_id", "normalized_url", name="uq_resource_definition_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_definitions.id", ondelete="CASCADE"), index=True
    )
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    current_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    next_recrawl_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CrawlObservation(Base):
    __tablename__ = "crawl_observations"
    __table_args__ = (Index("ix_observations_resource_observed", "resource_id", "observed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("web_resources.id", ondelete="CASCADE"), index=True
    )
    fetch_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fetch_attempts.id", ondelete="SET NULL"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    outcome: Mapped[ObservationOutcome] = mapped_column(
        Enum(ObservationOutcome, name="observation_outcome", values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    change_kind: Mapped[ChangeKind | None] = mapped_column(
        Enum(ChangeKind, name="change_kind", values_callable=_enum_values, create_type=False)
    )
    status_code: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class ExtractionAttempt(Base):
    __tablename__ = "extraction_attempts"
    __table_args__ = (
        UniqueConstraint("fetch_attempt_id", "parser_version", name="uq_extraction_parser_attempt"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fetch_attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fetch_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    parser_name: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    text_length: Mapped[int | None] = mapped_column(Integer)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    error_type: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DuplicateCluster(TimestampMixin, Base):
    __tablename__ = "duplicate_clusters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_definitions.id", ondelete="CASCADE"), index=True
    )
    representative_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    member_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class IndexOperation(TimestampMixin, Base):
    __tablename__ = "index_operations"
    __table_args__ = (
        UniqueConstraint("document_id", "schema_version", name="uq_index_document_schema"),
        Index("ix_index_operations_scheduler", "status", "available_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[IndexOperationStatus] = mapped_column(
        Enum(IndexOperationStatus, name="index_operation_status", values_callable=_enum_values),
        default=IndexOperationStatus.PENDING,
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndexBuild(TimestampMixin, Base):
    __tablename__ = "index_builds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[IndexBuildStatus] = mapped_column(
        Enum(IndexBuildStatus, name="index_build_status", values_callable=_enum_values),
        default=IndexBuildStatus.PENDING,
        nullable=False,
        index=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    physical_index: Mapped[str | None] = mapped_column(String(255))
    expected_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    indexed_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    queues: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    current_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pipeline_tasks.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class MetricSample(Base):
    __tablename__ = "metric_samples"
    __table_args__ = (Index("ix_metric_samples_name_time", "metric_name", "observed_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), index=True
    )
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    labels: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class OperationalIncident(TimestampMixin, Base):
    __tablename__ = "operational_incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status", values_callable=_enum_values),
        default=IncidentStatus.OPEN,
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    incident_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
