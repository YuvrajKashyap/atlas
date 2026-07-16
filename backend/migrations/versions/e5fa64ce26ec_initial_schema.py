"""initial schema

Revision ID: e5fa64ce26ec
Revises:
Create Date: 2026-07-14 19:24:54.329267
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5fa64ce26ec"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "running",
                "stopping",
                "completed",
                "failed",
                "cancelled",
                name="crawl_run_status",
            ),
            nullable=False,
        ),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("per_domain_delay_ms", sa.Integer(), nullable=False),
        sa.Column("request_timeout_seconds", sa.Float(), nullable=False),
        sa.Column("max_response_bytes", sa.Integer(), nullable=False),
        sa.Column("max_redirects", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("user_agent", sa.String(length=255), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("max_depth >= 0", name="ck_crawl_runs_max_depth_nonnegative"),
        sa.CheckConstraint("max_pages > 0", name="ck_crawl_runs_max_pages_positive"),
        sa.CheckConstraint("per_domain_delay_ms >= 250", name="ck_crawl_runs_polite_delay"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_crawl_runs_status"), "crawl_runs", ["status"], unique=False)
    op.create_table(
        "allowed_domains",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("include_subdomains", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "domain", name="uq_allowed_domain_run"),
    )
    op.create_index(op.f("ix_allowed_domains_run_id"), "allowed_domains", ["run_id"], unique=False)
    op.create_table(
        "crawl_seeds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "normalized_url", name="uq_seed_run_url"),
    )
    op.create_index(op.f("ix_crawl_seeds_run_id"), "crawl_seeds", ["run_id"], unique=False)
    op.create_table(
        "domain_states",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("host", sa.String(length=253), nullable=False),
        sa.Column("robots_url", sa.Text(), nullable=True),
        sa.Column("robots_status_code", sa.Integer(), nullable=True),
        sa.Column("robots_body", sa.Text(), nullable=True),
        sa.Column("robots_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("robots_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("robots_error", sa.Text(), nullable=True),
        sa.Column("crawl_delay_ms", sa.Integer(), nullable=True),
        sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "host", name="uq_domain_state_run_host"),
    )
    op.create_index(
        op.f("ix_domain_states_next_allowed_at"), "domain_states", ["next_allowed_at"], unique=False
    )
    op.create_index(op.f("ix_domain_states_run_id"), "domain_states", ["run_id"], unique=False)
    op.create_table(
        "frontier_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("host", sa.String(length=253), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "discovered",
                "queued",
                "fetching",
                "fetched",
                "extracting",
                "indexing",
                "indexed",
                "retry_scheduled",
                "robots_blocked",
                "disallowed_domain",
                "duplicate_url",
                "duplicate_content",
                "unsupported_content",
                "budget_exhausted",
                "failed",
                name="frontier_status",
            ),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("discovered_from_id", sa.UUID(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("next_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rq_job_id", sa.String(length=255), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("fetch_attempt_count", sa.Integer(), nullable=False),
        sa.Column("robots_allowed", sa.Boolean(), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("last_error_type", sa.String(length=120), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("depth >= 0", name="ck_frontier_depth_nonnegative"),
        sa.ForeignKeyConstraint(
            ["discovered_from_id"], ["frontier_entries.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "normalized_url", name="uq_frontier_run_normalized_url"),
    )
    op.create_index(op.f("ix_frontier_entries_host"), "frontier_entries", ["host"], unique=False)
    op.create_index(
        op.f("ix_frontier_entries_lease_expires_at"),
        "frontier_entries",
        ["lease_expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_frontier_entries_next_fetch_at"),
        "frontier_entries",
        ["next_fetch_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_frontier_entries_run_id"), "frontier_entries", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_frontier_entries_status"), "frontier_entries", ["status"], unique=False
    )
    op.create_index(
        "ix_frontier_scheduler",
        "frontier_entries",
        ["run_id", "status", "next_fetch_at", "priority"],
        unique=False,
    )
    op.create_table(
        "crawl_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("frontier_entry_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["frontier_entry_id"], ["frontier_entries.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crawl_events_event_type"), "crawl_events", ["event_type"], unique=False
    )
    op.create_index(
        "ix_crawl_events_run_created", "crawl_events", ["run_id", "created_at"], unique=False
    )
    op.create_index(op.f("ix_crawl_events_run_id"), "crawl_events", ["run_id"], unique=False)
    op.create_table(
        "discovered_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("source_frontier_id", sa.UUID(), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("normalized_target_url", sa.Text(), nullable=False),
        sa.Column("target_frontier_id", sa.UUID(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_frontier_id"], ["frontier_entries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_frontier_id"], ["frontier_entries.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_frontier_id", "normalized_target_url", name="uq_discovered_link_source_target"
        ),
    )
    op.create_index(
        op.f("ix_discovered_links_run_id"), "discovered_links", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_discovered_links_source_frontier_id"),
        "discovered_links",
        ["source_frontier_id"],
        unique=False,
    )
    op.create_table(
        "fetch_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("frontier_entry_id", sa.UUID(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "outcome",
            sa.Enum(
                "succeeded",
                "transient_error",
                "permanent_error",
                "robots_blocked",
                "unsupported_content",
                name="fetch_outcome",
            ),
            nullable=True,
        ),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("redirect_chain", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("response_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("response_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_type", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_body_key", sa.Text(), nullable=True),
        sa.Column("body_sha256", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["frontier_entry_id"], ["frontier_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("frontier_entry_id", "attempt_number", name="uq_fetch_attempt_number"),
    )
    op.create_index(
        op.f("ix_fetch_attempts_frontier_entry_id"),
        "fetch_attempts",
        ["frontier_entry_id"],
        unique=False,
    )
    op.create_index(op.f("ix_fetch_attempts_run_id"), "fetch_attempts", ["run_id"], unique=False)
    op.create_index(
        op.f("ix_fetch_attempts_status_code"), "fetch_attempts", ["status_code"], unique=False
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("frontier_entry_id", sa.UUID(), nullable=False),
        sa.Column("fetch_attempt_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("host", sa.String(length=253), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("headings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("main_text", sa.Text(), nullable=False),
        sa.Column("text_length", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("duplicate_of_document_id", sa.UUID(), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("parser_name", sa.String(length=80), nullable=False),
        sa.Column("parser_version", sa.String(length=40), nullable=False),
        sa.Column("extraction_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("index_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_document_id"], ["documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["fetch_attempt_id"], ["fetch_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["frontier_entry_id"], ["frontier_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fetch_attempt_id", name="uq_document_fetch_attempt"),
    )
    op.create_index(
        op.f("ix_documents_frontier_entry_id"), "documents", ["frontier_entry_id"], unique=False
    )
    op.create_index(op.f("ix_documents_host"), "documents", ["host"], unique=False)
    op.create_index(op.f("ix_documents_language"), "documents", ["language"], unique=False)
    op.create_index(
        "ix_documents_run_content_hash", "documents", ["run_id", "content_hash"], unique=False
    )
    op.create_index(op.f("ix_documents_run_id"), "documents", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_documents_run_id"), table_name="documents")
    op.drop_index("ix_documents_run_content_hash", table_name="documents")
    op.drop_index(op.f("ix_documents_language"), table_name="documents")
    op.drop_index(op.f("ix_documents_host"), table_name="documents")
    op.drop_index(op.f("ix_documents_frontier_entry_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_fetch_attempts_status_code"), table_name="fetch_attempts")
    op.drop_index(op.f("ix_fetch_attempts_run_id"), table_name="fetch_attempts")
    op.drop_index(op.f("ix_fetch_attempts_frontier_entry_id"), table_name="fetch_attempts")
    op.drop_table("fetch_attempts")
    op.drop_index(op.f("ix_discovered_links_source_frontier_id"), table_name="discovered_links")
    op.drop_index(op.f("ix_discovered_links_run_id"), table_name="discovered_links")
    op.drop_table("discovered_links")
    op.drop_index(op.f("ix_crawl_events_run_id"), table_name="crawl_events")
    op.drop_index("ix_crawl_events_run_created", table_name="crawl_events")
    op.drop_index(op.f("ix_crawl_events_event_type"), table_name="crawl_events")
    op.drop_table("crawl_events")
    op.drop_index("ix_frontier_scheduler", table_name="frontier_entries")
    op.drop_index(op.f("ix_frontier_entries_status"), table_name="frontier_entries")
    op.drop_index(op.f("ix_frontier_entries_run_id"), table_name="frontier_entries")
    op.drop_index(op.f("ix_frontier_entries_next_fetch_at"), table_name="frontier_entries")
    op.drop_index(op.f("ix_frontier_entries_lease_expires_at"), table_name="frontier_entries")
    op.drop_index(op.f("ix_frontier_entries_host"), table_name="frontier_entries")
    op.drop_table("frontier_entries")
    op.drop_index(op.f("ix_domain_states_run_id"), table_name="domain_states")
    op.drop_index(op.f("ix_domain_states_next_allowed_at"), table_name="domain_states")
    op.drop_table("domain_states")
    op.drop_index(op.f("ix_crawl_seeds_run_id"), table_name="crawl_seeds")
    op.drop_table("crawl_seeds")
    op.drop_index(op.f("ix_allowed_domains_run_id"), table_name="allowed_domains")
    op.drop_table("allowed_domains")
    op.drop_index(op.f("ix_crawl_runs_status"), table_name="crawl_runs")
    op.drop_table("crawl_runs")
    postgresql.ENUM(name="fetch_outcome").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="frontier_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="crawl_run_status").drop(op.get_bind(), checkfirst=True)
