import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.enums import PipelineTaskStatus, PipelineTaskType
from atlas.models import DomainLease, FrontierEntry, PipelineTask, WorkerHeartbeat
from atlas.schemas import AllowedDomainInput, CrawlRunCreate
from atlas.services.runs import create_run, start_run
from atlas.tasking import (
    complete_task,
    fail_task,
    heartbeat_task,
    recover_expired_tasks,
    upsert_worker_heartbeat,
)


def _started_task(session: Session) -> PipelineTask:
    run = create_run(
        session,
        CrawlRunCreate(
            name="lease lifecycle",
            seeds=["https://example.com/"],
            allowed_domains=[AllowedDomainInput(domain="example.com", include_subdomains=False)],
        ),
        commit=False,
    )
    start_run(session, run.id, commit=False)
    session.commit()
    task = session.scalar(select(PipelineTask).where(PipelineTask.run_id == run.id))
    assert task is not None
    return task


def _lease(session: Session, task: PipelineTask, *, attempts: int = 1) -> uuid.UUID:
    token = uuid.uuid4()
    task.status = PipelineTaskStatus.LEASED
    task.attempt_count = attempts
    task.lease_token = token
    task.lease_owner = "test-worker"
    task.lease_expires_at = datetime.now(UTC) + timedelta(minutes=1)
    task.rq_job_id = f"job-{task.id}"
    entry = session.get(FrontierEntry, task.frontier_entry_id)
    assert entry is not None
    entry.lease_expires_at = task.lease_expires_at
    entry.rq_job_id = task.rq_job_id
    session.add(
        DomainLease(
            run_id=task.run_id,
            task_id=task.id,
            host="example.com",
            lease_token=token,
            expires_at=task.lease_expires_at,
        )
    )
    session.commit()
    return token


def test_heartbeat_complete_and_worker_upsert(db_session: Session) -> None:
    task = _started_task(db_session)
    token = _lease(db_session, task)

    assert heartbeat_task(db_session, task.id, token, lease_seconds=120)
    assert not heartbeat_task(db_session, task.id, uuid.uuid4(), lease_seconds=120)
    entry = db_session.get(FrontierEntry, task.frontier_entry_id)
    assert entry is not None and entry.lease_expires_at == task.lease_expires_at
    assert complete_task(db_session, task.id, token)
    assert not complete_task(db_session, task.id, token)
    db_session.expire(entry)
    assert entry.lease_expires_at is None
    assert entry.rq_job_id is None

    upsert_worker_heartbeat(
        db_session,
        worker_id="worker-one",
        queues=["atlas-fetch"],
        version="1",
        current_task_id=None,
    )
    upsert_worker_heartbeat(
        db_session,
        worker_id="worker-one",
        queues=["atlas-fetch", "atlas-index"],
        version="2",
        current_task_id=task.id,
    )
    db_session.commit()
    worker = db_session.get(WorkerHeartbeat, "worker-one")
    assert worker is not None
    assert worker.version == "2"
    assert worker.current_task_id == task.id


def test_failure_retry_dead_letter_and_expired_recovery(db_session: Session) -> None:
    task = _started_task(db_session)
    token = _lease(db_session, task, attempts=1)

    assert (
        fail_task(
            db_session,
            task,
            token,
            error_type="network",
            error_message="temporary",
            transient=True,
        )
        == PipelineTaskStatus.RETRY_SCHEDULED
    )
    assert (
        fail_task(
            db_session,
            task,
            token,
            error_type="stale",
            error_message="ignored",
            transient=True,
        )
        == PipelineTaskStatus.RETRY_SCHEDULED
    )
    db_session.commit()
    retry_entry = db_session.get(FrontierEntry, task.frontier_entry_id)
    assert retry_entry is not None and retry_entry.lease_expires_at is None
    assert retry_entry.rq_job_id is None

    token = _lease(db_session, task, attempts=task.max_attempts)
    assert (
        fail_task(
            db_session,
            task,
            token,
            error_type="permanent",
            error_message="x" * 5000,
            transient=False,
        )
        == PipelineTaskStatus.DEAD_LETTERED
    )
    db_session.commit()

    first = _started_task(db_session)
    first.task_type = PipelineTaskType.EXTRACT
    first.generation += 1
    first.max_attempts = 3
    first_token = _lease(db_session, first, attempts=1)
    first_expired_at = datetime.now(UTC) - timedelta(seconds=1)
    first.lease_expires_at = first_expired_at
    lease = db_session.scalar(select(DomainLease).where(DomainLease.lease_token == first_token))
    assert lease is not None
    lease.expires_at = first_expired_at

    second = _started_task(db_session)
    second.task_type = PipelineTaskType.INDEX
    second.generation += 2
    second_token = _lease(db_session, second, attempts=second.max_attempts)
    second_expired_at = datetime.now(UTC) - timedelta(seconds=1)
    second.lease_expires_at = second_expired_at
    second_lease = db_session.scalar(
        select(DomainLease).where(DomainLease.lease_token == second_token)
    )
    assert second_lease is not None
    second_lease.expires_at = second_expired_at
    db_session.commit()

    recovered, dead = recover_expired_tasks(db_session)

    assert (recovered, dead) == (1, 1)
    assert first.status == PipelineTaskStatus.RETRY_SCHEDULED
    assert second.status == PipelineTaskStatus.DEAD_LETTERED
    first_entry = db_session.get(FrontierEntry, first.frontier_entry_id)
    second_entry = db_session.get(FrontierEntry, second.frontier_entry_id)
    assert first_entry is not None and first_entry.lease_expires_at is None
    assert second_entry is not None and second_entry.lease_expires_at is None
