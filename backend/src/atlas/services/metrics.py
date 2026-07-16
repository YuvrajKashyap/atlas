import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.models import CrawlEvent, Document, FetchAttempt, FrontierEntry
from atlas.schemas import CrawlEventRead, MetricsOverview
from atlas.services.runs import get_run_counters


def metrics_overview(session: Session, run_id: uuid.UUID) -> MetricsOverview:
    frontier_statuses = {
        status.value: count
        for status, count in session.execute(
            select(FrontierEntry.status, func.count())
            .where(FrontierEntry.run_id == run_id)
            .group_by(FrontierEntry.status)
        )
    }
    http_statuses = {
        str(status): count
        for status, count in session.execute(
            select(FetchAttempt.status_code, func.count())
            .where(FetchAttempt.run_id == run_id, FetchAttempt.status_code.is_not(None))
            .group_by(FetchAttempt.status_code)
        )
    }
    percentiles = session.execute(
        select(
            func.percentile_cont(0.5).within_group(FetchAttempt.latency_ms).label("p50"),
            func.percentile_cont(0.95).within_group(FetchAttempt.latency_ms).label("p95"),
        ).where(FetchAttempt.run_id == run_id, FetchAttempt.latency_ms.is_not(None))
    ).one()
    cutoff = datetime.now(UTC) - timedelta(minutes=5)
    recent_fetches = (
        session.scalar(
            select(func.count())
            .select_from(FetchAttempt)
            .where(FetchAttempt.run_id == run_id, FetchAttempt.started_at >= cutoff)
        )
        or 0
    )
    document_count = (
        session.scalar(select(func.count()).select_from(Document).where(Document.run_id == run_id))
        or 0
    )
    duplicate_count = (
        session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.run_id == run_id, Document.duplicate_of_document_id.is_not(None))
        )
        or 0
    )
    parser_successes = (
        session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.run_id == run_id, Document.text_length > 0)
        )
        or 0
    )
    active_domains = (
        session.scalar(
            select(func.count(func.distinct(FrontierEntry.host))).where(
                FrontierEntry.run_id == run_id
            )
        )
        or 0
    )
    events = list(
        session.scalars(
            select(CrawlEvent)
            .where(CrawlEvent.run_id == run_id)
            .order_by(CrawlEvent.created_at.desc())
            .limit(12)
        )
    )
    return MetricsOverview(
        run_id=run_id,
        counters=get_run_counters(session, run_id),
        throughput_per_minute=round(recent_fetches / 5, 2),
        fetch_latency_p50_ms=float(percentiles.p50) if percentiles.p50 is not None else None,
        fetch_latency_p95_ms=float(percentiles.p95) if percentiles.p95 is not None else None,
        parser_success_rate=round(parser_successes / document_count, 3) if document_count else None,
        duplicate_rate=round(duplicate_count / document_count, 3) if document_count else None,
        http_statuses=http_statuses,
        frontier_statuses=frontier_statuses,
        active_domains=active_domains,
        recent_events=[CrawlEventRead.model_validate(event) for event in events],
    )
