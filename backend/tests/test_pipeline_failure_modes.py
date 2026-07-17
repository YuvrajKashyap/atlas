import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from opensearchpy import OpenSearchException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.config import Settings
from atlas.enums import IndexBuildStatus, PipelineTaskStatus, PipelineTaskType
from atlas.fetcher import FetchResult, ResponseTooLargeError
from atlas.jobs import process_frontier_entry, process_pipeline_task, run_index_build
from atlas.models import (
    CrawlRun,
    Document,
    DomainLease,
    DomainState,
    FrontierEntry,
    IndexBuild,
    PipelineTask,
    WebResource,
)
from atlas.politeness import acquire_fetch_permit
from atlas.robots import RobotsDecision, RobotsService
from atlas.schemas import AllowedDomainInput, CrawlRunCreate
from atlas.services.runs import create_run, start_run
from atlas.sitemaps import SitemapDiscovery


def _task(session: Session, name: str) -> PipelineTask:
    run = create_run(
        session,
        CrawlRunCreate(
            name=name,
            seeds=[f"https://example.com/{name}"],
            allowed_domains=[AllowedDomainInput(domain="example.com", include_subdomains=False)],
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
    expires = datetime.now(UTC) + timedelta(minutes=5)
    task.status = PipelineTaskStatus.LEASED
    task.attempt_count += 1
    task.lease_token = token
    task.lease_owner = "failure-test"
    task.lease_expires_at = expires
    if task.task_type == PipelineTaskType.FETCH:
        entry = session.get(FrontierEntry, task.frontier_entry_id)
        assert entry is not None
        session.add(
            DomainLease(
                run_id=task.run_id,
                task_id=task.id,
                host=entry.host,
                lease_token=token,
                expires_at=expires,
            )
        )
    session.commit()
    return token


def _allow(
    _self: RobotsService,
    _session: Session,
    _run: CrawlRun,
    _entry: FrontierEntry,
    _domains: list[tuple[str, bool]],
) -> RobotsDecision:
    return RobotsDecision(True, "robots_allowed", 250)


def _response(url: str, *, status: int = 200, content_type: str = "text/html") -> FetchResult:
    return FetchResult(
        status_code=status,
        final_url=url,
        headers={"etag": '"fixture"', "last-modified": "Wed, 01 Jul 2026 00:00:00 GMT"},
        body=(
            b"<html><body><main><h1>Fixture</h1><p>Failure branch fixture.</p></main></body></html>"
        ),
        content_type=content_type,
        latency_ms=2,
        redirect_chain=[],
        request_headers={},
    )


def test_fetch_permit_enforces_delay_at_request_boundary(db_session: Session) -> None:
    task = _task(db_session, "request-boundary-permit")
    entry = db_session.get(FrontierEntry, task.frontier_entry_id)
    assert entry is not None

    first = acquire_fetch_permit(
        db_session,
        run_id=task.run_id,
        host=entry.host,
        delay_ms=100,
    )
    second = acquire_fetch_permit(
        db_session,
        run_id=task.run_id,
        host=entry.host,
        delay_ms=100,
    )

    assert (second - first).total_seconds() >= 0.09


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("permanent", "dead_lettered"),
        ("http", "retry_scheduled"),
        ("unsupported", "unsupported_content"),
    ],
)
def test_fetch_failure_and_terminal_content_modes(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected: str,
) -> None:
    task = _task(db_session, mode)
    token = _lease(db_session, task)
    monkeypatch.setattr("atlas.jobs.RobotsService.decide", _allow)

    def fetch(
        _run: CrawlRun,
        url: str,
        _domains: list[tuple[str, bool]],
        **_kwargs: object,
    ) -> FetchResult:
        if mode == "permanent":
            raise ResponseTooLargeError("too large")
        if mode == "http":
            return _response(url, status=503)
        return _response(url, content_type="application/json")

    monkeypatch.setattr("atlas.jobs.fetch_url", fetch)

    assert process_pipeline_task(str(task.id), str(token))["status"] == expected


def test_conditional_fetch_returns_not_modified(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _task(db_session, "conditional")
    run = db_session.get(CrawlRun, task.run_id)
    entry = db_session.get(FrontierEntry, task.frontier_entry_id)
    assert run is not None and entry is not None
    db_session.add(
        WebResource(
            definition_id=run.definition_id,
            normalized_url=entry.normalized_url,
            canonical_url=entry.normalized_url,
            host=entry.host,
            etag='"old"',
            last_modified="Tue, 30 Jun 2026 00:00:00 GMT",
        )
    )
    db_session.commit()
    token = _lease(db_session, task)
    monkeypatch.setattr("atlas.jobs.RobotsService.decide", _allow)

    def not_modified(
        _run: CrawlRun,
        url: str,
        _domains: list[tuple[str, bool]],
        **kwargs: object,
    ) -> FetchResult:
        conditional = cast(dict[str, str], kwargs["conditional_headers"])
        assert conditional == {
            "If-None-Match": '"old"',
            "If-Modified-Since": "Tue, 30 Jun 2026 00:00:00 GMT",
        }
        return _response(url, status=304)

    monkeypatch.setattr("atlas.jobs.fetch_url", not_modified)

    assert process_pipeline_task(str(task.id), str(token))["status"] == "not_modified"


def test_sitemap_discovery_is_recorded_without_blocking_page_fetch(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _task(db_session, "sitemap")
    entry = db_session.get(FrontierEntry, task.frontier_entry_id)
    assert entry is not None
    db_session.add(DomainState(run_id=task.run_id, host=entry.host))
    db_session.commit()
    token = _lease(db_session, task)

    def sitemap_policy(
        _self: RobotsService,
        _session: Session,
        _run: CrawlRun,
        _entry: FrontierEntry,
        _domains: list[tuple[str, bool]],
    ) -> RobotsDecision:
        return RobotsDecision(True, "robots_allowed", 250, ("https://example.com/sitemap.xml",))

    def discover(*_args: object, **_kwargs: object) -> SitemapDiscovery:
        return SitemapDiscovery(
            tuple(f"https://example.com/from-sitemap/{index}" for index in range(1001)),
            1,
            0,
        )

    def fetch(
        _run: CrawlRun,
        url: str,
        _domains: list[tuple[str, bool]],
        **_kwargs: object,
    ) -> FetchResult:
        return _response(url)

    monkeypatch.setattr("atlas.jobs.RobotsService.decide", sitemap_policy)
    monkeypatch.setattr("atlas.jobs.discover_sitemaps", discover)
    monkeypatch.setattr("atlas.jobs.fetch_url", fetch)

    assert process_pipeline_task(str(task.id), str(token))["status"] == "fetched"
    db_session.expire_all()
    state = db_session.scalar(select(DomainState).where(DomainState.run_id == task.run_id))
    assert state is not None and state.sitemap_url_count == 1001
    frontier_count = db_session.scalar(
        select(func.count()).select_from(FrontierEntry).where(FrontierEntry.run_id == task.run_id)
    )
    assert frontier_count == 1002


def test_sitemap_failure_is_non_blocking_and_extract_requires_artifact(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sitemap_task = _task(db_session, "sitemap-failure")
    entry = db_session.get(FrontierEntry, sitemap_task.frontier_entry_id)
    assert entry is not None
    db_session.add(DomainState(run_id=sitemap_task.run_id, host=entry.host))
    db_session.commit()
    sitemap_token = _lease(db_session, sitemap_task)

    def sitemap_policy(
        _self: RobotsService,
        _session: Session,
        _run: CrawlRun,
        _entry: FrontierEntry,
        _domains: list[tuple[str, bool]],
    ) -> RobotsDecision:
        return RobotsDecision(True, "robots_allowed", 250, ("https://example.com/sitemap.xml",))

    def fail_discovery(*_args: object, **_kwargs: object) -> SitemapDiscovery:
        raise ValueError("malformed sitemap")

    def fetch(
        _run: CrawlRun,
        url: str,
        _domains: list[tuple[str, bool]],
        **_kwargs: object,
    ) -> FetchResult:
        return _response(url)

    monkeypatch.setattr("atlas.jobs.RobotsService.decide", sitemap_policy)
    monkeypatch.setattr("atlas.jobs.discover_sitemaps", fail_discovery)
    monkeypatch.setattr("atlas.jobs.fetch_url", fetch)
    assert process_pipeline_task(str(sitemap_task.id), str(sitemap_token))["status"] == "fetched"

    missing_task = _task(db_session, "missing-artifact")
    missing_task.task_type = PipelineTaskType.EXTRACT
    missing_task.payload = {"attempt_id": str(uuid.uuid4())}
    db_session.commit()
    missing_token = _lease(db_session, missing_task)

    assert (
        process_pipeline_task(str(missing_task.id), str(missing_token))["status"] == "dead_lettered"
    )


def test_extraction_and_index_outages_dead_letter_or_retry(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch_task = _task(db_session, "stage-failures")
    fetch_token = _lease(db_session, fetch_task)
    monkeypatch.setattr("atlas.jobs.RobotsService.decide", _allow)

    def fetch(
        _run: CrawlRun,
        url: str,
        _domains: list[tuple[str, bool]],
        **_kwargs: object,
    ) -> FetchResult:
        return _response(url)

    monkeypatch.setattr("atlas.jobs.fetch_url", fetch)
    assert process_pipeline_task(str(fetch_task.id), str(fetch_token))["status"] == "fetched"
    db_session.expire_all()
    extract_task = db_session.scalar(
        select(PipelineTask).where(
            PipelineTask.run_id == fetch_task.run_id,
            PipelineTask.task_type == PipelineTaskType.EXTRACT,
        )
    )
    assert extract_task is not None
    extract_token = _lease(db_session, extract_task)

    def parser_failure(*_args: object, **_kwargs: object) -> object:
        raise ValueError("malformed parser input")

    monkeypatch.setattr("atlas.jobs.extract_page", parser_failure)
    assert (
        process_pipeline_task(str(extract_task.id), str(extract_token))["status"] == "dead_lettered"
    )


def test_index_outage_and_index_build_verification(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch_task = _task(db_session, "index-failure")
    fetch_token = _lease(db_session, fetch_task)
    monkeypatch.setattr("atlas.jobs.RobotsService.decide", _allow)

    def fetch(
        _run: CrawlRun,
        url: str,
        _domains: list[tuple[str, bool]],
        **_kwargs: object,
    ) -> FetchResult:
        return _response(url)

    class FailingIndex:
        schema_version = 2

        def __init__(self, _settings: Settings) -> None:
            pass

        def index_document(self, _document: Document, **_kwargs: object) -> str:
            raise OpenSearchException("injected index outage")

    monkeypatch.setattr("atlas.jobs.fetch_url", fetch)
    monkeypatch.setattr("atlas.jobs.DocumentIndex", FailingIndex)
    assert process_pipeline_task(str(fetch_task.id), str(fetch_token))["status"] == "fetched"
    db_session.expire_all()
    extract_task = db_session.scalar(
        select(PipelineTask).where(
            PipelineTask.run_id == fetch_task.run_id,
            PipelineTask.task_type == PipelineTaskType.EXTRACT,
        )
    )
    assert extract_task is not None
    extract_token = _lease(db_session, extract_task)
    assert process_pipeline_task(str(extract_task.id), str(extract_token))["status"] == "indexing"
    db_session.expire_all()
    index_task = db_session.scalar(
        select(PipelineTask).where(
            PipelineTask.run_id == fetch_task.run_id,
            PipelineTask.task_type == PipelineTaskType.INDEX,
        )
    )
    assert index_task is not None
    index_token = _lease(db_session, index_task)
    assert (
        process_pipeline_task(str(index_task.id), str(index_token))["status"] == "retry_scheduled"
    )

    class CountClient:
        def count(self, *, index: str) -> dict[str, int]:
            assert index.startswith("atlas-build-")
            return {"count": 1}

    class BuildIndex:
        schema_version = 2

        def __init__(self, _settings: Settings) -> None:
            self.client = CountClient()

        def create_build_index(self, build_id: uuid.UUID) -> str:
            return f"atlas-build-{build_id}"

        def index_document(self, _document: Document, *, index_name: str | None = None) -> str:
            assert index_name is not None
            return index_name

        def activate_index(self, index_name: str) -> None:
            assert index_name.startswith("atlas-build-")

    build = IndexBuild(status=IndexBuildStatus.PENDING, schema_version=2)
    db_session.add(build)
    db_session.commit()
    monkeypatch.setattr("atlas.jobs.DocumentIndex", BuildIndex)

    result = run_index_build(str(build.id))

    assert result == {"status": "succeeded", "indexed": 1}


def test_compatibility_frontier_shim_is_idempotent(db_session: Session) -> None:
    assert process_frontier_entry(str(uuid.uuid4())) == {"status": "missing"}
    run = create_run(db_session, _request_for_shim(), commit=True)
    entry = db_session.scalar(select(FrontierEntry).where(FrontierEntry.run_id == run.id))
    assert entry is not None

    assert process_frontier_entry(str(entry.id)) == {"status": "migrated_to_pipeline"}
    assert process_frontier_entry(str(entry.id)) == {"status": "migrated_to_pipeline"}


def _request_for_shim() -> CrawlRunCreate:
    return CrawlRunCreate(
        name="compatibility",
        seeds=["https://example.com/compatibility"],
        allowed_domains=[AllowedDomainInput(domain="example.com", include_subdomains=False)],
    )
