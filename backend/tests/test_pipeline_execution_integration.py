import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.config import Settings
from atlas.enums import FrontierStatus, PipelineTaskStatus, PipelineTaskType
from atlas.fetcher import FetchNetworkError, FetchResult
from atlas.jobs import process_pipeline_task
from atlas.models import Document, DomainLease, FrontierEntry, IndexOperation, PipelineTask
from atlas.robots import RobotsDecision, RobotsService
from atlas.schemas import AllowedDomainInput, CrawlRunCreate
from atlas.services.runs import create_run, start_run
from atlas.tasking import create_pipeline_task


def _pipeline_task(session: Session, name: str = "pipeline") -> PipelineTask:
    run = create_run(
        session,
        CrawlRunCreate(
            name=name,
            seeds=[f"https://example.com/{name}"],
            allowed_domains=[AllowedDomainInput(domain="example.com", include_subdomains=False)],
            max_depth=2,
            per_domain_delay_ms=250,
        ),
        commit=False,
    )
    start_run(session, run.id, commit=False)
    session.commit()
    task = session.scalar(
        select(PipelineTask).where(
            PipelineTask.run_id == run.id,
            PipelineTask.task_type == PipelineTaskType.FETCH,
        )
    )
    assert task is not None
    return task


def _lease(session: Session, task: PipelineTask) -> uuid.UUID:
    token = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    task.status = PipelineTaskStatus.LEASED
    task.attempt_count += 1
    task.lease_token = token
    task.lease_owner = "integration-worker"
    task.lease_expires_at = expires_at
    if task.task_type == PipelineTaskType.FETCH:
        entry = session.get(FrontierEntry, task.frontier_entry_id)
        assert entry is not None
        session.add(
            DomainLease(
                run_id=task.run_id,
                task_id=task.id,
                host=entry.host,
                lease_token=token,
                expires_at=expires_at,
            )
        )
    session.commit()
    return token


class FakeIndex:
    schema_version = 2

    def __init__(self, _settings: Settings) -> None:
        pass

    def index_document(self, _document: Document, *, index_name: str | None = None) -> str:
        return index_name or "atlas-documents-write"


def test_fetch_extract_index_pipeline_is_durable_and_idempotent(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch_task = _pipeline_task(db_session)
    fetch_token = _lease(db_session, fetch_task)

    def allow(
        _self: RobotsService,
        _session: Session,
        _run: object,
        _entry: FrontierEntry,
        _domains: list[tuple[str, bool]],
    ) -> RobotsDecision:
        return RobotsDecision(True, "robots_allowed", 250)

    html = (
        b"<html lang='en'><head><title>Pipeline page</title>"
        b"<meta name='description' content='A durable integration page'></head>"
        b"<body><main><h1>Pipeline</h1><p>Durable extraction and indexing content.</p>"
        b"<a href='/next'>next</a></main></body></html>"
    )

    def fetch(
        _run: object,
        url: str,
        _domains: list[tuple[str, bool]],
        **_kwargs: object,
    ) -> FetchResult:
        return FetchResult(
            status_code=200,
            final_url=url,
            headers={"etag": '"pipeline"'},
            body=html,
            content_type="text/html; charset=utf-8",
            latency_ms=4,
            redirect_chain=[],
            request_headers={},
        )

    monkeypatch.setattr("atlas.jobs.RobotsService.decide", allow)
    monkeypatch.setattr("atlas.jobs.fetch_url", fetch)
    monkeypatch.setattr("atlas.jobs.DocumentIndex", FakeIndex)

    fetch_result = process_pipeline_task(str(fetch_task.id), str(fetch_token))
    assert fetch_result["status"] == "fetched"
    assert process_pipeline_task(str(fetch_task.id), str(fetch_token))["status"] == "stale_lease"

    db_session.expire_all()
    extract_task = db_session.scalar(
        select(PipelineTask).where(
            PipelineTask.run_id == fetch_task.run_id,
            PipelineTask.task_type == PipelineTaskType.EXTRACT,
        )
    )
    assert extract_task is not None
    extract_token = _lease(db_session, extract_task)
    extract_result = process_pipeline_task(str(extract_task.id), str(extract_token))
    assert extract_result["status"] == "indexing"

    db_session.expire_all()
    document = db_session.scalar(select(Document).where(Document.run_id == fetch_task.run_id))
    assert document is not None
    assert document.title == "Pipeline page"
    assert document.resource_id is not None
    discovered = list(
        db_session.scalars(select(FrontierEntry).where(FrontierEntry.run_id == fetch_task.run_id))
    )
    assert {entry.normalized_url for entry in discovered} == {
        "https://example.com/pipeline",
        "https://example.com/next",
    }

    index_task = db_session.scalar(
        select(PipelineTask).where(
            PipelineTask.run_id == fetch_task.run_id,
            PipelineTask.task_type == PipelineTaskType.INDEX,
        )
    )
    assert index_task is not None
    index_token = _lease(db_session, index_task)
    index_result = process_pipeline_task(str(index_task.id), str(index_token))
    assert index_result["status"] == "indexed"

    db_session.expire_all()
    operation = db_session.scalar(
        select(IndexOperation).where(IndexOperation.run_id == fetch_task.run_id)
    )
    entry = db_session.get(FrontierEntry, fetch_task.frontier_entry_id)
    assert operation is not None and operation.status.value == "succeeded"
    assert entry is not None and entry.status == FrontierStatus.INDEXED

    recrawl_task_id = create_pipeline_task(
        db_session,
        run_id=fetch_task.run_id,
        frontier_entry_id=fetch_task.frontier_entry_id,
        task_type=PipelineTaskType.FETCH,
        generation=2,
        max_attempts=3,
    )
    db_session.commit()
    assert recrawl_task_id is not None
    recrawl_task = db_session.get(PipelineTask, recrawl_task_id)
    assert recrawl_task is not None
    recrawl_token = _lease(db_session, recrawl_task)
    assert process_pipeline_task(str(recrawl_task.id), str(recrawl_token))["status"] == "fetched"
    db_session.expire_all()
    recrawl_extract = db_session.scalar(
        select(PipelineTask).where(
            PipelineTask.run_id == fetch_task.run_id,
            PipelineTask.task_type == PipelineTaskType.EXTRACT,
            PipelineTask.generation == 2,
        )
    )
    assert recrawl_extract is not None
    recrawl_extract_token = _lease(db_session, recrawl_extract)
    assert (
        process_pipeline_task(str(recrawl_extract.id), str(recrawl_extract_token))["status"]
        == "unchanged"
    )


def test_fetch_pipeline_handles_robots_and_transient_network_failures(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocked_task = _pipeline_task(db_session, "blocked")
    blocked_token = _lease(db_session, blocked_task)

    def block(
        _self: RobotsService,
        _session: Session,
        _run: object,
        _entry: FrontierEntry,
        _domains: list[tuple[str, bool]],
    ) -> RobotsDecision:
        return RobotsDecision(False, "robots_disallowed", 250)

    monkeypatch.setattr("atlas.jobs.RobotsService.decide", block)
    blocked = process_pipeline_task(str(blocked_task.id), str(blocked_token))
    assert blocked["status"] == "robots_blocked"

    transient_task = _pipeline_task(db_session, "transient")
    transient_token = _lease(db_session, transient_task)

    def allow(
        _self: RobotsService,
        _session: Session,
        _run: object,
        _entry: FrontierEntry,
        _domains: list[tuple[str, bool]],
    ) -> RobotsDecision:
        return RobotsDecision(True, "robots_allowed", 250)

    def fail_fetch(*_args: object, **_kwargs: object) -> FetchResult:
        raise FetchNetworkError("injected outage")

    monkeypatch.setattr("atlas.jobs.RobotsService.decide", allow)
    monkeypatch.setattr("atlas.jobs.fetch_url", fail_fetch)
    transient = process_pipeline_task(str(transient_task.id), str(transient_token))
    assert transient["status"] == "retry_scheduled"
    assert transient["error_type"] == "FetchNetworkError"
