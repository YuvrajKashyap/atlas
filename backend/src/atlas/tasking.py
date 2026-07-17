import os
import socket
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from atlas.enums import PipelineTaskStatus, PipelineTaskType
from atlas.models import DomainLease, FrontierEntry, PipelineTask, WorkerHeartbeat
from atlas.retry import retry_delay

TASK_QUEUES = {
    PipelineTaskType.FETCH: "atlas-fetch",
    PipelineTaskType.EXTRACT: "atlas-extract",
    PipelineTaskType.INDEX: "atlas-index",
}


def create_pipeline_task(
    session: Session,
    *,
    run_id: uuid.UUID,
    frontier_entry_id: uuid.UUID,
    task_type: PipelineTaskType,
    generation: int,
    max_attempts: int,
    payload: dict[str, object] | None = None,
    available_at: datetime | None = None,
) -> uuid.UUID | None:
    task_id = uuid.uuid4()
    statement = (
        pg_insert(PipelineTask)
        .values(
            id=task_id,
            run_id=run_id,
            frontier_entry_id=frontier_entry_id,
            task_type=task_type,
            status=PipelineTaskStatus.READY,
            generation=generation,
            max_attempts=max_attempts,
            payload=payload or {},
            available_at=available_at or datetime.now(UTC),
        )
        .on_conflict_do_nothing(constraint="uq_pipeline_task_stage")
        .returning(PipelineTask.id)
    )
    return session.scalar(statement)


def heartbeat_task(
    session: Session,
    task_id: uuid.UUID,
    lease_token: uuid.UUID,
    *,
    lease_seconds: int,
) -> bool:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=lease_seconds)
    frontier_entry_id = session.scalar(
        update(PipelineTask)
        .where(
            PipelineTask.id == task_id,
            PipelineTask.status == PipelineTaskStatus.LEASED,
            PipelineTask.lease_token == lease_token,
        )
        .values(last_heartbeat_at=now, lease_expires_at=expires_at)
        .returning(PipelineTask.frontier_entry_id)
    )
    if frontier_entry_id:
        session.execute(
            update(FrontierEntry)
            .where(FrontierEntry.id == frontier_entry_id)
            .values(lease_expires_at=expires_at)
        )
        session.execute(
            update(DomainLease)
            .where(DomainLease.task_id == task_id, DomainLease.lease_token == lease_token)
            .values(expires_at=expires_at)
        )
    return bool(frontier_entry_id)


def complete_task(session: Session, task_id: uuid.UUID, lease_token: uuid.UUID) -> bool:
    now = datetime.now(UTC)
    frontier_entry_id = session.scalar(
        update(PipelineTask)
        .where(
            PipelineTask.id == task_id,
            PipelineTask.status == PipelineTaskStatus.LEASED,
            PipelineTask.lease_token == lease_token,
        )
        .values(
            status=PipelineTaskStatus.SUCCEEDED,
            completed_at=now,
            lease_owner=None,
            lease_token=None,
            lease_expires_at=None,
            rq_job_id=None,
            last_error_type=None,
            last_error_message=None,
        )
        .returning(PipelineTask.frontier_entry_id)
    )
    if frontier_entry_id:
        session.execute(
            update(FrontierEntry)
            .where(FrontierEntry.id == frontier_entry_id)
            .values(lease_expires_at=None, rq_job_id=None)
        )
        session.execute(delete(DomainLease).where(DomainLease.task_id == task_id))
    return bool(frontier_entry_id)


def fail_task(
    session: Session,
    task: PipelineTask,
    lease_token: uuid.UUID,
    *,
    error_type: str,
    error_message: str,
    transient: bool,
) -> PipelineTaskStatus:
    if task.status != PipelineTaskStatus.LEASED or task.lease_token != lease_token:
        return task.status
    now = datetime.now(UTC)
    retryable = transient and task.attempt_count < task.max_attempts
    task.status = (
        PipelineTaskStatus.RETRY_SCHEDULED if retryable else PipelineTaskStatus.DEAD_LETTERED
    )
    task.available_at = (
        now + retry_delay(task.attempt_count, str(task.id)) if retryable else task.available_at
    )
    task.last_error_type = error_type
    task.last_error_message = error_message[:4000]
    task.lease_owner = None
    task.lease_token = None
    task.lease_expires_at = None
    task.rq_job_id = None
    task.completed_at = None if retryable else now
    session.execute(
        update(FrontierEntry)
        .where(FrontierEntry.id == task.frontier_entry_id)
        .values(lease_expires_at=None, rq_job_id=None)
    )
    session.execute(delete(DomainLease).where(DomainLease.task_id == task.id))
    return task.status


def recover_expired_tasks(session: Session, *, limit: int = 500) -> tuple[int, int]:
    now = datetime.now(UTC)
    tasks = list(
        session.scalars(
            select(PipelineTask)
            .where(
                PipelineTask.status == PipelineTaskStatus.LEASED,
                PipelineTask.lease_expires_at < now,
            )
            .order_by(PipelineTask.lease_expires_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    recovered = 0
    dead_lettered = 0
    for task in tasks:
        if task.attempt_count < task.max_attempts:
            task.status = PipelineTaskStatus.RETRY_SCHEDULED
            task.available_at = now
            recovered += 1
        else:
            task.status = PipelineTaskStatus.DEAD_LETTERED
            task.completed_at = now
            dead_lettered += 1
        task.last_error_type = "lease_expired"
        task.last_error_message = "Worker lease expired before the stage completed"
        task.lease_owner = None
        task.lease_token = None
        task.lease_expires_at = None
        task.rq_job_id = None
        session.execute(
            update(FrontierEntry)
            .where(FrontierEntry.id == task.frontier_entry_id)
            .values(lease_expires_at=None, rq_job_id=None)
        )
        session.execute(delete(DomainLease).where(DomainLease.task_id == task.id))
    session.execute(delete(DomainLease).where(DomainLease.expires_at < now))
    return recovered, dead_lettered


def upsert_worker_heartbeat(
    session: Session,
    *,
    worker_id: str,
    queues: list[str],
    version: str,
    current_task_id: uuid.UUID | None,
) -> None:
    now = datetime.now(UTC)
    statement = pg_insert(WorkerHeartbeat).values(
        worker_id=worker_id,
        queues=queues,
        version=version,
        current_task_id=current_task_id,
        started_at=now,
        last_seen_at=now,
        details={"hostname": socket.gethostname(), "pid": os.getpid()},
    )
    statement = statement.on_conflict_do_update(
        index_elements=[WorkerHeartbeat.worker_id],
        set_={
            "queues": queues,
            "version": version,
            "current_task_id": current_task_id,
            "last_seen_at": now,
        },
    )
    session.execute(statement)
