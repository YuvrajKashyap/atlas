import time
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from redis import Redis
from rq import Queue
from sqlalchemy import func, select, update

from atlas.config import get_settings
from atlas.db import SessionLocal
from atlas.enums import TERMINAL_FRONTIER_STATUSES, CrawlRunStatus, FrontierStatus
from atlas.events import emit_event
from atlas.logging import configure_logging
from atlas.models import CrawlRun, DomainState, FrontierEntry

settings = get_settings()
logger = structlog.get_logger(__name__)


def build_job_id(entry_id: uuid.UUID, attempt_number: int) -> str:
    return f"fetch-{entry_id}-{attempt_number}"


def _recover_expired_leases() -> int:
    now = datetime.now(UTC)
    with SessionLocal() as session:
        entries = list(
            session.scalars(
                select(FrontierEntry)
                .where(
                    FrontierEntry.status.in_(
                        [
                            FrontierStatus.QUEUED,
                            FrontierStatus.FETCHING,
                            FrontierStatus.FETCHED,
                            FrontierStatus.EXTRACTING,
                            FrontierStatus.INDEXING,
                        ]
                    ),
                    FrontierEntry.lease_expires_at.is_not(None),
                    FrontierEntry.lease_expires_at < now,
                )
                .with_for_update(skip_locked=True)
            )
        )
        for entry in entries:
            entry.status = FrontierStatus.RETRY_SCHEDULED
            entry.next_fetch_at = now
            entry.lease_expires_at = None
            entry.rq_job_id = None
            entry.last_error_type = "lease_expired"
            entry.last_error_message = (
                "Worker lease expired before the pipeline reached a terminal state"
            )
            emit_event(
                session,
                entry.run_id,
                "frontier.lease_recovered",
                frontier_entry_id=entry.id,
            )
        session.commit()
        return len(entries)


def _finalize_runs() -> None:
    now = datetime.now(UTC)
    active_statuses = [
        status for status in FrontierStatus if status not in TERMINAL_FRONTIER_STATUSES
    ]
    with SessionLocal() as session:
        runs = list(
            session.scalars(
                select(CrawlRun).where(
                    CrawlRun.status.in_([CrawlRunStatus.RUNNING, CrawlRunStatus.STOPPING])
                )
            )
        )
        for run in runs:
            attempted = (
                session.scalar(
                    select(func.count())
                    .select_from(FrontierEntry)
                    .where(FrontierEntry.run_id == run.id, FrontierEntry.fetch_attempt_count > 0)
                )
                or 0
            )
            if attempted >= run.max_pages or run.status == CrawlRunStatus.STOPPING:
                session.execute(
                    update(FrontierEntry)
                    .where(
                        FrontierEntry.run_id == run.id,
                        FrontierEntry.status.in_(
                            [FrontierStatus.DISCOVERED, FrontierStatus.RETRY_SCHEDULED]
                        ),
                    )
                    .values(status=FrontierStatus.BUDGET_EXHAUSTED, next_fetch_at=None)
                )
            remaining = (
                session.scalar(
                    select(func.count())
                    .select_from(FrontierEntry)
                    .where(
                        FrontierEntry.run_id == run.id, FrontierEntry.status.in_(active_statuses)
                    )
                )
                or 0
            )
            if remaining == 0:
                stopped = run.status == CrawlRunStatus.STOPPING
                run.status = CrawlRunStatus.CANCELLED if stopped else CrawlRunStatus.COMPLETED
                run.finished_at = now
                event_type = "run.cancelled" if stopped else "run.completed"
                emit_event(session, run.id, event_type, payload={"attempted": attempted})
        session.commit()


def _lease_and_enqueue(queue: Queue) -> int:
    now = datetime.now(UTC)
    enqueued = 0
    with SessionLocal() as session:
        runs = list(
            session.scalars(
                select(CrawlRun)
                .where(CrawlRun.status == CrawlRunStatus.RUNNING)
                .order_by(CrawlRun.started_at)
            )
        )
        for run in runs:
            run_enqueued = 0
            attempted = (
                session.scalar(
                    select(func.count())
                    .select_from(FrontierEntry)
                    .where(FrontierEntry.run_id == run.id, FrontierEntry.fetch_attempt_count > 0)
                )
                or 0
            )
            active = (
                session.scalar(
                    select(func.count())
                    .select_from(FrontierEntry)
                    .where(
                        FrontierEntry.run_id == run.id,
                        FrontierEntry.status.in_(
                            [
                                FrontierStatus.QUEUED,
                                FrontierStatus.FETCHING,
                                FrontierStatus.FETCHED,
                                FrontierStatus.EXTRACTING,
                                FrontierStatus.INDEXING,
                            ]
                        ),
                    )
                )
                or 0
            )
            available_slots = max(0, min(20, run.max_pages - attempted - active))
            if available_slots == 0:
                continue
            candidates = list(
                session.scalars(
                    select(FrontierEntry)
                    .where(
                        FrontierEntry.run_id == run.id,
                        FrontierEntry.status.in_(
                            [FrontierStatus.DISCOVERED, FrontierStatus.RETRY_SCHEDULED]
                        ),
                        FrontierEntry.next_fetch_at <= now,
                    )
                    .order_by(
                        FrontierEntry.priority.desc(),
                        FrontierEntry.depth,
                        FrontierEntry.created_at,
                    )
                    .limit(available_slots * 3)
                    .with_for_update(skip_locked=True)
                )
            )
            leased_hosts: set[str] = set()
            for entry in candidates:
                if run_enqueued >= available_slots or entry.host in leased_hosts:
                    continue
                state = session.scalar(
                    select(DomainState)
                    .where(DomainState.run_id == run.id, DomainState.host == entry.host)
                    .with_for_update()
                )
                if state is None:
                    state = DomainState(run_id=run.id, host=entry.host)
                    session.add(state)
                    session.flush()
                if state.next_allowed_at is not None and state.next_allowed_at > now:
                    continue
                delay_ms = max(run.per_domain_delay_ms, state.crawl_delay_ms or 0)
                state.next_allowed_at = now + timedelta(milliseconds=delay_ms)
                job_id = build_job_id(entry.id, entry.fetch_attempt_count + 1)
                entry.status = FrontierStatus.QUEUED
                entry.lease_expires_at = now + timedelta(seconds=settings.frontier_lease_seconds)
                entry.rq_job_id = job_id
                emit_event(
                    session,
                    run.id,
                    "frontier.queued",
                    frontier_entry_id=entry.id,
                    payload={"job_id": job_id, "host": entry.host},
                )
                session.commit()
                try:
                    queue.enqueue(
                        "atlas.jobs.process_frontier_entry",
                        str(entry.id),
                        job_id=job_id,
                        job_timeout=max(settings.frontier_lease_seconds - 10, 30),
                        result_ttl=60,
                        failure_ttl=86_400,
                    )
                except Exception as exc:
                    logger.exception("enqueue_failed", frontier_entry_id=str(entry.id))
                    entry.status = FrontierStatus.RETRY_SCHEDULED
                    entry.next_fetch_at = now + timedelta(seconds=5)
                    entry.lease_expires_at = None
                    entry.rq_job_id = None
                    entry.last_error_type = "enqueue_error"
                    entry.last_error_message = str(exc)[:2000]
                    emit_event(
                        session,
                        run.id,
                        "frontier.enqueue_failed",
                        frontier_entry_id=entry.id,
                        payload={"job_id": job_id, "error": type(exc).__name__},
                    )
                    session.commit()
                else:
                    enqueued += 1
                    run_enqueued += 1
                    leased_hosts.add(entry.host)
        return enqueued


def run_once(queue: Queue) -> dict[str, int]:
    recovered = _recover_expired_leases()
    enqueued = _lease_and_enqueue(queue)
    _finalize_runs()
    return {"recovered": recovered, "enqueued": enqueued}


def main() -> None:
    configure_logging(settings.log_level)
    redis = Redis.from_url(settings.redis_url)
    queue = Queue("atlas-fetch", connection=redis)
    logger.info("scheduler_started", poll_seconds=settings.scheduler_poll_seconds)
    while True:
        try:
            result = run_once(queue)
            if result["recovered"] or result["enqueued"]:
                logger.info("scheduler_tick", **result)
        except Exception:
            logger.exception("scheduler_tick_failed")
        time.sleep(settings.scheduler_poll_seconds)


if __name__ == "__main__":
    main()
