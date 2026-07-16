import uuid
from datetime import datetime
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

from atlas.enums import CrawlRunStatus, FetchOutcome, FrontierStatus


def _crawl_run_status_values(enum_type: type[CrawlRunStatus]) -> list[str]:
    return [member.value for member in enum_type]


def _frontier_status_values(enum_type: type[FrontierStatus]) -> list[str]:
    return [member.value for member in enum_type]


def _fetch_outcome_values(enum_type: type[FetchOutcome]) -> list[str]:
    return [member.value for member in enum_type]


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CrawlRun(TimestampMixin, Base):
    __tablename__ = "crawl_runs"
    __table_args__ = (
        CheckConstraint("max_pages > 0", name="ck_crawl_runs_max_pages_positive"),
        CheckConstraint("max_depth >= 0", name="ck_crawl_runs_max_depth_nonnegative"),
        CheckConstraint("per_domain_delay_ms >= 250", name="ck_crawl_runs_polite_delay"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    crawl_delay_ms: Mapped[int | None] = mapped_column(Integer)
    next_allowed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


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
