import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.enums import CrawlRunStatus, FrontierStatus, PipelineTaskType
from atlas.events import emit_event
from atlas.models import AllowedDomain, CrawlRun, CrawlSeed, Document, FrontierEntry
from atlas.schemas import AllowedDomainInput, CrawlRunCreate, CrawlRunRead, RunCounters
from atlas.tasking import create_pipeline_task
from atlas.urls import (
    UrlPolicyError,
    host_for_url,
    is_host_allowed,
    normalize_domain,
    normalize_url,
)


class RunStateError(RuntimeError):
    pass


def create_run(session: Session, request: CrawlRunCreate, *, commit: bool = True) -> CrawlRun:
    allowed = [
        (normalize_domain(item.domain), item.include_subdomains) for item in request.allowed_domains
    ]
    if len({domain for domain, _include_subdomains in allowed}) != len(allowed):
        raise UrlPolicyError("Allowed domains must be unique")
    normalized_seeds: list[tuple[str, str]] = []
    seen_seeds: set[str] = set()
    for seed in request.seeds:
        normalized = normalize_url(seed)
        if normalized in seen_seeds:
            raise UrlPolicyError("Seed URLs must be unique after normalization")
        if not is_host_allowed(host_for_url(normalized), allowed):
            raise UrlPolicyError(f"Seed URL is outside the allowlist: {seed}")
        normalized_seeds.append((seed, normalized))
        seen_seeds.add(normalized)

    snapshot = request.model_dump(mode="json")
    run = CrawlRun(
        name=request.name.strip(),
        max_pages=request.max_pages,
        max_depth=request.max_depth,
        per_domain_delay_ms=request.per_domain_delay_ms,
        request_timeout_seconds=request.request_timeout_seconds,
        max_response_bytes=request.max_response_bytes,
        max_redirects=request.max_redirects,
        max_retries=request.max_retries,
        max_duration_seconds=request.max_duration_seconds,
        global_concurrency=request.global_concurrency,
        per_domain_concurrency=request.per_domain_concurrency,
        allowed_content_types=request.allowed_content_types,
        allowed_ports=request.allowed_ports,
        user_agent=request.user_agent,
        config_snapshot=snapshot,
    )
    session.add(run)
    session.flush()

    for domain, include_subdomains in allowed:
        session.add(
            AllowedDomain(run_id=run.id, domain=domain, include_subdomains=include_subdomains)
        )
    for original, normalized in normalized_seeds:
        session.add(CrawlSeed(run_id=run.id, url=original, normalized_url=normalized))
        session.add(
            FrontierEntry(
                run_id=run.id,
                url=original,
                normalized_url=normalized,
                host=host_for_url(normalized),
                status=FrontierStatus.DISCOVERED,
                priority=100,
                depth=0,
                next_fetch_at=datetime.now(UTC),
            )
        )
    emit_event(session, run.id, "run.created", payload={"seed_count": len(normalized_seeds)})
    if commit:
        session.commit()
    return run


def start_run(session: Session, run_id: uuid.UUID, *, commit: bool = True) -> CrawlRun:
    run = session.get(CrawlRun, run_id)
    if run is None:
        raise LookupError("Crawl run not found")
    if run.status != CrawlRunStatus.DRAFT:
        raise RunStateError(f"Only draft runs can start; current status is {run.status.value}")
    run.status = CrawlRunStatus.RUNNING
    run.started_at = datetime.now(UTC)
    seeds = list(session.scalars(select(FrontierEntry).where(FrontierEntry.run_id == run.id)))
    for entry in seeds:
        create_pipeline_task(
            session,
            run_id=run.id,
            frontier_entry_id=entry.id,
            task_type=PipelineTaskType.FETCH,
            generation=run.generation,
            max_attempts=max(1, run.max_retries + 1),
        )
    emit_event(session, run.id, "run.started")
    if commit:
        session.commit()
    return run


def stop_run(session: Session, run_id: uuid.UUID) -> CrawlRun:
    run = session.get(CrawlRun, run_id)
    if run is None:
        raise LookupError("Crawl run not found")
    if run.status != CrawlRunStatus.RUNNING:
        raise RunStateError(f"Only running runs can stop; current status is {run.status.value}")
    run.status = CrawlRunStatus.STOPPING
    run.stop_requested_at = datetime.now(UTC)
    emit_event(session, run.id, "run.stop_requested")
    session.commit()
    return run


def get_run_counters(session: Session, run_id: uuid.UUID) -> RunCounters:
    status_counts = {
        status.value: count
        for status, count in session.execute(
            select(FrontierEntry.status, func.count())
            .where(FrontierEntry.run_id == run_id)
            .group_by(FrontierEntry.status)
        )
    }
    document_count = (
        session.scalar(select(func.count()).select_from(Document).where(Document.run_id == run_id))
        or 0
    )
    return RunCounters(
        discovered=sum(status_counts.values()),
        queued=status_counts.get(FrontierStatus.QUEUED.value, 0),
        fetching=sum(
            status_counts.get(status.value, 0)
            for status in (
                FrontierStatus.FETCHING,
                FrontierStatus.FETCHED,
                FrontierStatus.EXTRACTING,
                FrontierStatus.INDEXING,
            )
        ),
        indexed=status_counts.get(FrontierStatus.INDEXED.value, 0),
        failed=status_counts.get(FrontierStatus.FAILED.value, 0),
        blocked=status_counts.get(FrontierStatus.ROBOTS_BLOCKED.value, 0),
        duplicates=sum(
            status_counts.get(status.value, 0)
            for status in (FrontierStatus.DUPLICATE_URL, FrontierStatus.DUPLICATE_CONTENT)
        ),
        retries=status_counts.get(FrontierStatus.RETRY_SCHEDULED.value, 0),
        documents=document_count,
    )


def serialize_run(session: Session, run: CrawlRun) -> CrawlRunRead:
    seeds = list(
        session.scalars(
            select(CrawlSeed.url).where(CrawlSeed.run_id == run.id).order_by(CrawlSeed.created_at)
        )
    )
    domains = list(
        session.scalars(
            select(AllowedDomain)
            .where(AllowedDomain.run_id == run.id)
            .order_by(AllowedDomain.domain)
        )
    )
    return CrawlRunRead(
        id=run.id,
        definition_id=run.definition_id,
        generation=run.generation,
        name=run.name,
        status=run.status,
        max_pages=run.max_pages,
        max_depth=run.max_depth,
        per_domain_delay_ms=run.per_domain_delay_ms,
        request_timeout_seconds=run.request_timeout_seconds,
        max_response_bytes=run.max_response_bytes,
        max_redirects=run.max_redirects,
        max_retries=run.max_retries,
        max_duration_seconds=run.max_duration_seconds,
        global_concurrency=run.global_concurrency,
        per_domain_concurrency=run.per_domain_concurrency,
        allowed_content_types=run.allowed_content_types,
        allowed_ports=run.allowed_ports,
        user_agent=run.user_agent,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        stop_requested_at=run.stop_requested_at,
        seeds=seeds,
        allowed_domains=[
            AllowedDomainInput(domain=item.domain, include_subdomains=item.include_subdomains)
            for item in domains
        ],
        counters=get_run_counters(session, run.id),
    )


def get_run_or_raise(session: Session, run_id: uuid.UUID) -> CrawlRun:
    run = session.get(CrawlRun, run_id)
    if run is None:
        raise LookupError("Crawl run not found")
    return run
