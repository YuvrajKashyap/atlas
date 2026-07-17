# pyright: reportPrivateUsage=false

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import atlas.scheduler as scheduler
from atlas.enums import CrawlRunStatus, FrontierStatus, PipelineTaskStatus, PipelineTaskType
from atlas.models import (
    CrawlDefinition,
    CrawlRun,
    DomainLease,
    DomainState,
    FrontierEntry,
    MetricSample,
    PipelineTask,
)
from atlas.schemas import AllowedDomainInput, CrawlRunCreate
from atlas.services.runs import create_run, start_run, stop_run
from atlas.tasking import create_pipeline_task


class FakeQueue:
    def __init__(self, *, count: int = 0, fail: bool = False) -> None:
        self.count = count
        self.fail = fail
        self.enqueued: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def enqueue(self, *args: object, **kwargs: object) -> None:
        if self.fail:
            raise RuntimeError("injected redis loss")
        self.enqueued.append((args, kwargs))


def _request(name: str) -> CrawlRunCreate:
    return CrawlRunCreate(
        name=name,
        seeds=[f"https://example.com/{name}"],
        allowed_domains=[AllowedDomainInput(domain="example.com", include_subdomains=False)],
        per_domain_delay_ms=250,
        max_duration_seconds=60,
    )


def _queues(*, fail_fetch: bool = False) -> dict[PipelineTaskType, FakeQueue]:
    return {
        PipelineTaskType.FETCH: FakeQueue(count=2, fail=fail_fetch),
        PipelineTaskType.EXTRACT: FakeQueue(count=1),
        PipelineTaskType.INDEX: FakeQueue(count=0),
    }


def test_scheduler_creates_due_run_bootstraps_leases_and_samples(db_session: Session) -> None:
    definition = CrawlDefinition(
        name="due-definition",
        enabled=True,
        schedule_cron="*/5 * * * *",
        schedule_timezone="UTC",
        next_run_at=datetime.now(UTC) - timedelta(minutes=1),
        config=_request("scheduled").model_dump(mode="json"),
    )
    db_session.add(definition)
    db_session.commit()

    assert scheduler._create_due_runs() == 1
    db_session.expire_all()
    scheduled_run = db_session.scalar(
        select(CrawlRun).where(CrawlRun.definition_id == definition.id)
    )
    assert scheduled_run is not None
    assert scheduled_run.status == CrawlRunStatus.RUNNING
    assert definition.next_run_at is not None

    run = create_run(db_session, _request("bootstrap"), commit=False)
    run.status = CrawlRunStatus.RUNNING
    run.started_at = datetime.now(UTC)
    db_session.commit()
    assert scheduler._bootstrap_fetch_tasks() == 1
    assert scheduler._bootstrap_fetch_tasks() == 0

    db_session.expire_all()
    task = db_session.scalar(select(PipelineTask).where(PipelineTask.run_id == run.id))
    assert task is not None
    state = db_session.scalar(
        select(DomainState).where(DomainState.run_id == run.id, DomainState.host == "example.com")
    )
    if state is not None:
        state.next_allowed_at = None
        db_session.commit()
    queues = _queues()
    assert scheduler._lease_and_enqueue(cast(Any, queues)) >= 1
    db_session.expire_all()
    task = db_session.get(PipelineTask, task.id)
    assert task is not None and task.status == PipelineTaskStatus.LEASED
    assert queues[PipelineTaskType.FETCH].enqueued
    assert db_session.scalar(select(DomainLease).where(DomainLease.task_id == task.id)) is not None

    sample_count = scheduler._sample_metrics(cast(Any, queues))
    assert sample_count == 4
    assert len(list(db_session.scalars(select(MetricSample)))) == 4

    task.status = PipelineTaskStatus.SUCCEEDED
    task.lease_token = None
    task.lease_expires_at = None
    db_session.execute(delete(DomainLease).where(DomainLease.task_id == task.id))
    other_tasks = list(
        db_session.scalars(
            select(PipelineTask).where(
                PipelineTask.run_id == run.id,
                PipelineTask.id != task.id,
            )
        )
    )
    for other in other_tasks:
        other.status = PipelineTaskStatus.SUCCEEDED
    db_session.commit()
    assert scheduler._finalize_runs() >= 1
    db_session.refresh(run)
    assert run.status == CrawlRunStatus.COMPLETED


def test_scheduler_honors_politeness_failure_recovery_and_stop(db_session: Session) -> None:
    run = create_run(db_session, _request("polite"), commit=False)
    start_run(db_session, run.id, commit=False)
    db_session.commit()
    task = db_session.scalar(select(PipelineTask).where(PipelineTask.run_id == run.id))
    assert task is not None
    now = datetime.now(UTC)
    assert scheduler._can_lease_fetch(db_session, task, run, now)
    token = uuid.uuid4()
    task.status = PipelineTaskStatus.LEASED
    task.lease_token = token
    task.lease_expires_at = now + timedelta(minutes=5)
    db_session.add(
        DomainLease(
            run_id=run.id,
            task_id=task.id,
            host="example.com",
            lease_token=token,
            expires_at=task.lease_expires_at,
        )
    )
    db_session.flush()
    assert not scheduler._can_lease_fetch(db_session, task, run, now)
    db_session.execute(delete(DomainLease).where(DomainLease.task_id == task.id))
    task.status = PipelineTaskStatus.READY
    task.lease_token = None
    task.lease_expires_at = None
    db_session.commit()
    failed_queues = _queues(fail_fetch=True)
    assert scheduler._lease_and_enqueue(cast(Any, failed_queues)) == 0
    db_session.expire_all()
    task = db_session.get(PipelineTask, task.id)
    assert task is not None and task.status == PipelineTaskStatus.RETRY_SCHEDULED
    assert task.last_error_type == "enqueue_error"

    task.status = PipelineTaskStatus.LEASED
    task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    task.attempt_count = 1
    db_session.commit()
    assert scheduler._recover_expired_leases() == (1, 0)

    stop_run(db_session, run.id)
    assert scheduler._finalize_runs() == 1
    db_session.refresh(run)
    assert run.status == CrawlRunStatus.CANCELLED
    entries = list(db_session.scalars(select(FrontierEntry).where(FrontierEntry.run_id == run.id)))
    assert all(entry.status == FrontierStatus.BUDGET_EXHAUSTED for entry in entries)


def test_scheduler_checks_each_fetch_host_once_per_tick(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = create_run(db_session, _request("host-batch"), commit=False)
    start_run(db_session, run.id, commit=False)
    for suffix in ("one", "two"):
        entry = FrontierEntry(
            run_id=run.id,
            url=f"https://example.com/{suffix}",
            normalized_url=f"https://example.com/{suffix}",
            host="example.com",
            status=FrontierStatus.DISCOVERED,
            depth=0,
            next_fetch_at=datetime.now(UTC),
        )
        db_session.add(entry)
        db_session.flush()
        create_pipeline_task(
            db_session,
            run_id=run.id,
            frontier_entry_id=entry.id,
            task_type=PipelineTaskType.FETCH,
            generation=run.generation,
            max_attempts=2,
        )
    db_session.commit()

    calls = 0
    original = scheduler._can_lease_fetch

    def counted(*args: Any, **kwargs: Any) -> bool:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(scheduler, "_can_lease_fetch", counted)
    queues = _queues()

    assert scheduler._lease_and_enqueue(cast(Any, queues)) == 1
    assert calls == 1
    assert len(queues[PipelineTaskType.FETCH].enqueued) == 1


def test_scheduler_prioritizes_downstream_pipeline_stages(db_session: Session) -> None:
    run = create_run(db_session, _request("stage-priority"), commit=False)
    start_run(db_session, run.id, commit=False)
    run.global_concurrency = 1
    entry = db_session.scalar(select(FrontierEntry).where(FrontierEntry.run_id == run.id))
    assert entry is not None
    create_pipeline_task(
        db_session,
        run_id=run.id,
        frontier_entry_id=entry.id,
        task_type=PipelineTaskType.EXTRACT,
        generation=run.generation,
        max_attempts=2,
    )
    create_pipeline_task(
        db_session,
        run_id=run.id,
        frontier_entry_id=entry.id,
        task_type=PipelineTaskType.INDEX,
        generation=run.generation,
        max_attempts=2,
    )
    db_session.commit()
    queues = _queues()

    assert scheduler._lease_and_enqueue(cast(Any, queues)) == 1
    assert len(queues[PipelineTaskType.INDEX].enqueued) == 1
    assert not queues[PipelineTaskType.EXTRACT].enqueued
    assert not queues[PipelineTaskType.FETCH].enqueued


def test_scheduler_duration_and_run_once_orchestration(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = create_run(db_session, _request("duration"), commit=False)
    start_run(db_session, run.id, commit=False)
    run.started_at = datetime.now(UTC) - timedelta(minutes=2)
    for task in db_session.scalars(select(PipelineTask).where(PipelineTask.run_id == run.id)):
        task.status = PipelineTaskStatus.SUCCEEDED
    db_session.commit()

    assert scheduler._finalize_runs() == 1
    db_session.refresh(run)
    assert run.status == CrawlRunStatus.CANCELLED

    monkeypatch.setattr(scheduler, "_create_due_runs", lambda: 1)
    monkeypatch.setattr(scheduler, "_bootstrap_fetch_tasks", lambda: 2)
    monkeypatch.setattr(scheduler, "_recover_expired_leases", lambda: (3, 4))

    def lease(_queues: object) -> int:
        return 5

    def sample(_queues: object) -> int:
        return 7

    monkeypatch.setattr(scheduler, "_lease_and_enqueue", lease)
    monkeypatch.setattr(scheduler, "_finalize_runs", lambda: 6)
    monkeypatch.setattr(scheduler, "_sample_metrics", sample)

    result = scheduler.run_once(cast(Any, _queues()))

    assert result == {
        "scheduled_runs": 1,
        "bootstrapped": 2,
        "recovered": 3,
        "dead_lettered": 4,
        "enqueued": 5,
        "finalized": 6,
        "samples": 7,
    }

    assert scheduler.run_once(
        cast(Any, _queues()),
        sample_metrics=False,
        perform_maintenance=False,
    ) == {
        "scheduled_runs": 0,
        "bootstrapped": 0,
        "recovered": 0,
        "dead_lettered": 0,
        "enqueued": 5,
        "finalized": 0,
        "samples": 0,
    }


def test_scheduler_main_builds_queues_and_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    class StopScheduler(RuntimeError):
        pass

    redis = object()
    created_queues: list[str] = []
    samples: list[bool] = []
    maintenance: list[bool] = []

    class MainQueue:
        def __init__(self, name: str, *, connection: object) -> None:
            assert connection is redis
            created_queues.append(name)

    def run(
        _queues: object,
        *,
        sample_metrics: bool = True,
        perform_maintenance: bool = True,
    ) -> dict[str, int]:
        samples.append(sample_metrics)
        maintenance.append(perform_maintenance)
        return {"enqueued": 1}

    def stop(_seconds: float) -> None:
        raise StopScheduler

    def redis_from_url(_url: str, **_kwargs: object) -> object:
        return redis

    monkeypatch.setattr(scheduler.Redis, "from_url", redis_from_url)
    monkeypatch.setattr(scheduler, "Queue", MainQueue)
    monkeypatch.setattr(scheduler, "run_once", run)
    monkeypatch.setattr(scheduler.time, "sleep", stop)

    with pytest.raises(StopScheduler):
        scheduler.main()

    assert created_queues == ["atlas-fetch", "atlas-extract", "atlas-index"]
    assert samples == [True]
    assert maintenance == [True]
