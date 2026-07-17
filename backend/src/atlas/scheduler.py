import time
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from croniter import croniter
from redis import Redis
from rq import Queue
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.orm import Session

from atlas.config import get_settings
from atlas.db import SessionLocal
from atlas.enums import (
    CrawlRunStatus,
    FrontierStatus,
    PipelineTaskStatus,
    PipelineTaskType,
)
from atlas.events import emit_event
from atlas.logging import configure_logging
from atlas.models import (
    CrawlDefinition,
    CrawlRun,
    DomainLease,
    DomainState,
    FetchAttempt,
    FrontierEntry,
    MetricSample,
    PipelineTask,
)
from atlas.schemas import CrawlRunCreate
from atlas.services.runs import create_run, start_run
from atlas.tasking import TASK_QUEUES, create_pipeline_task, recover_expired_tasks

settings = get_settings()
logger = structlog.get_logger(__name__)


def build_job_id(entry_id: uuid.UUID, attempt_number: int) -> str:
    return f"fetch-{entry_id}-{attempt_number}"


def build_task_job_id(task: PipelineTask) -> str:
    return f"{task.task_type.value}-{task.id}-{task.attempt_count}"


def _create_due_runs() -> int:
    now = datetime.now(UTC)
    created = 0
    with SessionLocal() as session:
        definitions = list(
            session.scalars(
                select(CrawlDefinition)
                .where(
                    CrawlDefinition.enabled.is_(True),
                    CrawlDefinition.schedule_cron.is_not(None),
                    CrawlDefinition.next_run_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
        )
        for definition in definitions:
            try:
                if definition.schedule_cron is None:
                    continue
                request = CrawlRunCreate.model_validate(definition.config)
                previous_generation = session.scalar(
                    select(func.max(CrawlRun.generation)).where(
                        CrawlRun.definition_id == definition.id
                    )
                )
                run = create_run(session, request, commit=False)
                run.definition_id = definition.id
                run.generation = (previous_generation or 0) + 1
                session.flush()
                start_run(session, run.id, commit=False)
                definition.next_run_at = croniter(definition.schedule_cron, now).get_next(datetime)
                emit_event(
                    session,
                    run.id,
                    "run.scheduled",
                    payload={"definition_id": str(definition.id)},
                )
                created += 1
            except Exception as exc:
                logger.exception("scheduled_run_creation_failed", definition_id=str(definition.id))
                definition.next_run_at = now + timedelta(minutes=15)
                definition.config = {**definition.config, "last_schedule_error": str(exc)[:500]}
        session.commit()
    return created


def _bootstrap_fetch_tasks() -> int:
    created = 0
    with SessionLocal() as session:
        entries = list(
            session.scalars(
                select(FrontierEntry)
                .join(CrawlRun, CrawlRun.id == FrontierEntry.run_id)
                .where(
                    CrawlRun.status == CrawlRunStatus.RUNNING,
                    FrontierEntry.status.in_(
                        [FrontierStatus.DISCOVERED, FrontierStatus.RETRY_SCHEDULED]
                    ),
                    ~exists(
                        select(PipelineTask.id).where(
                            PipelineTask.frontier_entry_id == FrontierEntry.id,
                            PipelineTask.task_type == PipelineTaskType.FETCH,
                            PipelineTask.generation == CrawlRun.generation,
                        )
                    ),
                )
                .order_by(FrontierEntry.priority.desc(), FrontierEntry.created_at)
                .limit(1000)
            )
        )
        for entry in entries:
            run = session.get(CrawlRun, entry.run_id)
            if run is None:
                continue
            task_id = create_pipeline_task(
                session,
                run_id=run.id,
                frontier_entry_id=entry.id,
                task_type=PipelineTaskType.FETCH,
                generation=run.generation,
                max_attempts=max(1, run.max_retries + 1),
                available_at=entry.next_fetch_at,
            )
            created += int(task_id is not None)
        session.commit()
    return created


def _recover_expired_leases() -> tuple[int, int]:
    with SessionLocal() as session:
        recovered, dead_lettered = recover_expired_tasks(session)
        session.commit()
        return recovered, dead_lettered


def _can_lease_fetch(session: Session, task: PipelineTask, run: CrawlRun, now: datetime) -> bool:
    attempted = (
        session.scalar(
            select(func.count()).select_from(FetchAttempt).where(FetchAttempt.run_id == run.id)
        )
        or 0
    )
    if attempted >= run.max_pages:
        return False
    entry = session.get(FrontierEntry, task.frontier_entry_id)
    if entry is None:
        return False
    active_for_host = (
        session.scalar(
            select(func.count())
            .select_from(DomainLease)
            .where(
                DomainLease.run_id == run.id,
                DomainLease.host == entry.host,
                DomainLease.expires_at > now,
            )
        )
        or 0
    )
    if active_for_host >= run.per_domain_concurrency:
        return False
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
        return False
    delay_ms = max(run.per_domain_delay_ms, state.crawl_delay_ms or 0)
    state.next_allowed_at = now + timedelta(milliseconds=delay_ms)
    return True


def _lease_and_enqueue(queues: dict[PipelineTaskType, Queue]) -> int:
    now = datetime.now(UTC)
    enqueued = 0
    with SessionLocal() as session:
        candidates = list(
            session.execute(
                select(PipelineTask, CrawlRun, FrontierEntry)
                .join(CrawlRun, CrawlRun.id == PipelineTask.run_id)
                .join(FrontierEntry, FrontierEntry.id == PipelineTask.frontier_entry_id)
                .where(
                    CrawlRun.status == CrawlRunStatus.RUNNING,
                    PipelineTask.status.in_(
                        [PipelineTaskStatus.READY, PipelineTaskStatus.RETRY_SCHEDULED]
                    ),
                    PipelineTask.available_at <= now,
                )
                .order_by(PipelineTask.available_at, PipelineTask.created_at)
                .limit(200)
                .with_for_update(of=PipelineTask, skip_locked=True)
            )
        )
        run_active: dict[uuid.UUID, int] = {}
        checked_fetch_hosts: set[tuple[uuid.UUID, str]] = set()
        for task, run, entry in candidates:
            active = run_active.get(run.id)
            if active is None:
                active = (
                    session.scalar(
                        select(func.count())
                        .select_from(PipelineTask)
                        .where(
                            PipelineTask.run_id == run.id,
                            PipelineTask.status == PipelineTaskStatus.LEASED,
                        )
                    )
                    or 0
                )
            if active >= run.global_concurrency:
                continue
            if task.task_type == PipelineTaskType.FETCH:
                fetch_host = (run.id, entry.host)
                if fetch_host in checked_fetch_hosts:
                    continue
                checked_fetch_hosts.add(fetch_host)
                if not _can_lease_fetch(session, task, run, now):
                    continue

            token = uuid.uuid4()
            task.status = PipelineTaskStatus.LEASED
            task.attempt_count += 1
            task.lease_owner = "atlas-scheduler"
            task.lease_token = token
            task.last_heartbeat_at = now
            task.lease_expires_at = now + timedelta(seconds=settings.task_lease_seconds)
            task.rq_job_id = build_task_job_id(task)
            entry.status = {
                PipelineTaskType.FETCH: FrontierStatus.QUEUED,
                PipelineTaskType.EXTRACT: FrontierStatus.EXTRACTING,
                PipelineTaskType.INDEX: FrontierStatus.INDEXING,
            }[task.task_type]
            entry.lease_expires_at = task.lease_expires_at
            entry.rq_job_id = task.rq_job_id
            if task.task_type == PipelineTaskType.FETCH:
                session.add(
                    DomainLease(
                        run_id=run.id,
                        task_id=task.id,
                        host=entry.host,
                        lease_token=token,
                        expires_at=task.lease_expires_at,
                    )
                )
            emit_event(
                session,
                run.id,
                "pipeline.leased",
                frontier_entry_id=entry.id,
                payload={
                    "task_id": str(task.id),
                    "stage": task.task_type.value,
                    "attempt": task.attempt_count,
                },
            )
            session.commit()
            try:
                queues[task.task_type].enqueue(
                    "atlas.jobs.process_pipeline_task",
                    str(task.id),
                    str(token),
                    job_id=task.rq_job_id,
                    job_timeout=max(settings.task_lease_seconds - 15, 30),
                    result_ttl=300,
                    failure_ttl=86_400,
                )
            except Exception as exc:
                logger.exception("enqueue_failed", task_id=str(task.id))
                current = session.get(PipelineTask, task.id)
                if current is not None and current.lease_token == token:
                    current.status = PipelineTaskStatus.RETRY_SCHEDULED
                    current.available_at = now + timedelta(seconds=5)
                    current.lease_owner = None
                    current.lease_token = None
                    current.lease_expires_at = None
                    current.rq_job_id = None
                    current.last_error_type = "enqueue_error"
                    current.last_error_message = str(exc)[:2000]
                    entry.status = FrontierStatus.RETRY_SCHEDULED
                    entry.lease_expires_at = None
                    entry.rq_job_id = None
                    session.execute(delete(DomainLease).where(DomainLease.task_id == task.id))
                    session.commit()
            else:
                enqueued += 1
                run_active[run.id] = active + 1
    return enqueued


def _finalize_runs() -> int:
    now = datetime.now(UTC)
    finalized = 0
    with SessionLocal() as session:
        runs = list(
            session.scalars(
                select(CrawlRun).where(
                    CrawlRun.status.in_([CrawlRunStatus.RUNNING, CrawlRunStatus.STOPPING])
                )
            )
        )
        for run in runs:
            if (
                run.status == CrawlRunStatus.RUNNING
                and run.started_at is not None
                and run.started_at + timedelta(seconds=run.max_duration_seconds) <= now
            ):
                run.status = CrawlRunStatus.STOPPING
                run.stop_requested_at = now
                emit_event(session, run.id, "run.duration_exhausted")
            if run.status == CrawlRunStatus.STOPPING:
                session.execute(
                    update(PipelineTask)
                    .where(
                        PipelineTask.run_id == run.id,
                        PipelineTask.status.in_(
                            [PipelineTaskStatus.READY, PipelineTaskStatus.RETRY_SCHEDULED]
                        ),
                    )
                    .values(status=PipelineTaskStatus.CANCELLED, completed_at=now)
                )
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
            active = (
                session.scalar(
                    select(func.count())
                    .select_from(PipelineTask)
                    .where(
                        PipelineTask.run_id == run.id,
                        PipelineTask.status.in_(
                            [
                                PipelineTaskStatus.READY,
                                PipelineTaskStatus.LEASED,
                                PipelineTaskStatus.RETRY_SCHEDULED,
                            ]
                        ),
                    )
                )
                or 0
            )
            if active == 0:
                cancelled = run.status == CrawlRunStatus.STOPPING
                run.status = CrawlRunStatus.CANCELLED if cancelled else CrawlRunStatus.COMPLETED
                run.finished_at = now
                emit_event(session, run.id, "run.cancelled" if cancelled else "run.completed")
                finalized += 1
        session.commit()
    return finalized


def _sample_metrics(queues: dict[PipelineTaskType, Queue]) -> int:
    now = datetime.now(UTC)
    samples: list[MetricSample] = []
    with SessionLocal() as session:
        for task_type, queue in queues.items():
            samples.append(
                MetricSample(
                    metric_name="queue_depth",
                    value=float(queue.count),
                    labels={"queue": TASK_QUEUES[task_type], "stage": task_type.value},
                    observed_at=now,
                )
            )
        oldest = session.scalar(
            select(func.min(PipelineTask.available_at)).where(
                PipelineTask.status.in_(
                    [PipelineTaskStatus.READY, PipelineTaskStatus.RETRY_SCHEDULED]
                )
            )
        )
        queue_age = max(0.0, (now - oldest).total_seconds()) if oldest else 0.0
        samples.append(
            MetricSample(
                metric_name="queue_age_seconds", value=queue_age, labels={}, observed_at=now
            )
        )
        session.add_all(samples)
        session.commit()
    return len(samples)


def run_once(
    queues: dict[PipelineTaskType, Queue], *, sample_metrics: bool = True
) -> dict[str, int]:
    scheduled_runs = _create_due_runs()
    bootstrapped = _bootstrap_fetch_tasks()
    recovered, dead_lettered = _recover_expired_leases()
    enqueued = _lease_and_enqueue(queues)
    finalized = _finalize_runs()
    samples = _sample_metrics(queues) if sample_metrics else 0
    return {
        "scheduled_runs": scheduled_runs,
        "bootstrapped": bootstrapped,
        "recovered": recovered,
        "dead_lettered": dead_lettered,
        "enqueued": enqueued,
        "finalized": finalized,
        "samples": samples,
    }


def main() -> None:
    configure_logging(settings.log_level)
    redis = Redis.from_url(settings.redis_url, password=settings.redis_password or None)
    queues = {
        task_type: Queue(queue_name, connection=redis)
        for task_type, queue_name in TASK_QUEUES.items()
    }
    logger.info("scheduler_started", poll_seconds=settings.scheduler_poll_seconds)
    last_sampled_at: datetime | None = None
    while True:
        try:
            now = datetime.now(UTC)
            should_sample = (
                last_sampled_at is None
                or (now - last_sampled_at).total_seconds() >= settings.metrics_sample_seconds
            )
            result = run_once(queues, sample_metrics=should_sample)
            if should_sample:
                last_sampled_at = now
            if any(result.values()):
                logger.info("scheduler_tick", **result)
        except Exception:
            logger.exception("scheduler_tick_failed")
        time.sleep(settings.scheduler_poll_seconds)


if __name__ == "__main__":
    main()
