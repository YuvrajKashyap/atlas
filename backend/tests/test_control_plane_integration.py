import uuid
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.blob_store import get_blob_store
from atlas.config import get_settings
from atlas.enums import (
    ChangeKind,
    IncidentStatus,
    PipelineTaskStatus,
)
from atlas.models import (
    Document,
    DomainState,
    DuplicateCluster,
    ExtractionAttempt,
    FetchAttempt,
    FrontierEntry,
    MetricSample,
    OperationalIncident,
    PipelineTask,
    WebResource,
    WorkerHeartbeat,
)


def _run_payload(name: str = "Integration crawl") -> dict[str, object]:
    return {
        "name": name,
        "seeds": [
            "https://example.com/",
            "https://example.com/docs",
            "https://example.com/about",
        ],
        "allowed_domains": [{"domain": "example.com", "include_subdomains": False}],
        "max_pages": 20,
        "max_depth": 2,
        "per_domain_delay_ms": 250,
    }


def _json(response: httpx.Response) -> Any:
    return response.json()


def test_run_frontier_task_and_metrics_interfaces(api_client: TestClient) -> None:
    created_response = cast(
        httpx.Response, api_client.post("/api/v1/crawl-runs", json=_run_payload())
    )
    assert created_response.status_code == 201
    created = cast(dict[str, Any], _json(created_response))
    run_id = created["id"]

    assert cast(httpx.Response, api_client.get("/api/v1/crawl-runs")).status_code == 200
    assert cast(httpx.Response, api_client.get(f"/api/v1/crawl-runs/{run_id}")).status_code == 200

    started = cast(httpx.Response, api_client.post(f"/api/v1/crawl-runs/{run_id}/start"))
    assert started.status_code == 200
    assert _json(started)["status"] == "running"

    tasks = cast(httpx.Response, api_client.get(f"/api/v1/operations/tasks?run_id={run_id}"))
    assert len(_json(tasks)) == 3

    first = cast(
        httpx.Response,
        api_client.get(f"/api/v1/frontier?run_id={run_id}&page_size=1"),
    )
    first_payload = cast(dict[str, Any], _json(first))
    assert first_payload["total"] == 3
    assert first_payload["next_cursor"]
    second = cast(
        httpx.Response,
        api_client.get(
            f"/api/v1/frontier?run_id={run_id}&page_size=1&cursor={first_payload['next_cursor']}"
        ),
    )
    assert _json(second)["items"][0]["id"] != first_payload["items"][0]["id"]
    entry_id = first_payload["items"][0]["id"]
    assert cast(httpx.Response, api_client.get(f"/api/v1/frontier/{entry_id}")).status_code == 200
    assert (
        _json(cast(httpx.Response, api_client.get(f"/api/v1/frontier/{entry_id}/attempts"))) == []
    )

    metrics = cast(httpx.Response, api_client.get(f"/api/v1/metrics/overview?run_id={run_id}"))
    assert metrics.status_code == 200
    assert _json(metrics)["counters"]["discovered"] == 3

    stopped = cast(httpx.Response, api_client.post(f"/api/v1/crawl-runs/{run_id}/stop"))
    assert _json(stopped)["status"] == "stopping"
    events = cast(httpx.Response, api_client.get(f"/api/v1/crawl-runs/{run_id}/events"))
    assert len(_json(events)) >= 3


def test_definition_task_and_operations_interfaces(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition_response = cast(
        httpx.Response,
        api_client.post(
            "/api/v1/crawl-definitions",
            json={
                "name": "Nightly docs",
                "description": "Integration schedule",
                "schedule_cron": "0 2 * * *",
                "schedule_timezone": "UTC",
                "config": _run_payload("Scheduled crawl"),
            },
        ),
    )
    assert definition_response.status_code == 201
    definition = cast(dict[str, Any], _json(definition_response))
    definition_id = definition["id"]
    assert _json(cast(httpx.Response, api_client.get("/api/v1/crawl-definitions")))
    assert (
        cast(
            httpx.Response, api_client.get(f"/api/v1/crawl-definitions/{definition_id}")
        ).status_code
        == 200
    )
    toggled = cast(
        httpx.Response, api_client.post(f"/api/v1/crawl-definitions/{definition_id}/toggle")
    )
    assert _json(toggled)["enabled"] is False
    triggered = cast(
        httpx.Response, api_client.post(f"/api/v1/crawl-definitions/{definition_id}/trigger")
    )
    run_id = _json(triggered)["id"]

    task = db_session.scalar(select(PipelineTask).where(PipelineTask.run_id == uuid.UUID(run_id)))
    assert task is not None
    task.status = PipelineTaskStatus.DEAD_LETTERED
    task.completed_at = datetime.now(UTC)
    db_session.commit()
    dead = cast(httpx.Response, api_client.get("/api/v1/operations/dead-letter"))
    assert any(item["id"] == str(task.id) for item in _json(dead))
    retried = cast(httpx.Response, api_client.post(f"/api/v1/operations/tasks/{task.id}/retry"))
    assert _json(retried)["status"] == "retry_scheduled"
    cancelled = cast(httpx.Response, api_client.post(f"/api/v1/operations/tasks/{task.id}/cancel"))
    assert _json(cancelled)["status"] == "cancelled"

    db_session.add_all(
        [
            DomainState(
                run_id=uuid.UUID(run_id),
                host="example.com",
                robots_status_code=200,
                crawl_delay_ms=250,
                last_success_at=datetime.now(UTC),
            ),
            MetricSample(
                run_id=uuid.UUID(run_id),
                metric_name="queue_depth",
                value=2,
                labels={"queue": "fetch"},
            ),
            WorkerHeartbeat(
                worker_id="worker-test",
                queues=["atlas-fetch"],
                version="test",
                started_at=datetime.now(UTC),
                last_seen_at=datetime.now(UTC),
                details={},
            ),
            OperationalIncident(
                run_id=uuid.UUID(run_id),
                status=IncidentStatus.OPEN,
                severity="warning",
                incident_type="test",
                title="Injected integration incident",
                details={},
            ),
        ]
    )
    db_session.commit()
    incident = db_session.scalar(select(OperationalIncident))
    assert incident is not None

    assert _json(
        cast(httpx.Response, api_client.get(f"/api/v1/operations/domains?run_id={run_id}"))
    )
    assert _json(
        cast(
            httpx.Response,
            api_client.get("/api/v1/operations/metrics/timeseries?metric_name=queue_depth"),
        )
    )
    assert _json(cast(httpx.Response, api_client.get("/api/v1/operations/workers")))
    acknowledged = cast(
        httpx.Response,
        api_client.post(f"/api/v1/operations/incidents/{incident.id}/acknowledge"),
    )
    assert _json(acknowledged)["status"] == "acknowledged"
    resolved = cast(
        httpx.Response,
        api_client.post(f"/api/v1/operations/incidents/{incident.id}/resolve"),
    )
    assert _json(resolved)["status"] == "resolved"

    class FakeQueue:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def enqueue(self, *_args: object, **_kwargs: object) -> None:
            return None

    monkeypatch.setattr("atlas.api.routes.operations.Queue", FakeQueue)
    build = cast(httpx.Response, api_client.post("/api/v1/operations/index-builds"))
    assert build.status_code == 202
    assert _json(cast(httpx.Response, api_client.get("/api/v1/operations/index-builds")))


def test_document_parser_raw_search_and_comparison_interfaces(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left = cast(httpx.Response, api_client.post("/api/v1/crawl-runs", json=_run_payload("Left")))
    right = cast(httpx.Response, api_client.post("/api/v1/crawl-runs", json=_run_payload("Right")))
    left_id = uuid.UUID(_json(left)["id"])
    right_id = uuid.UUID(_json(right)["id"])
    entry = db_session.scalar(select(FrontierEntry).where(FrontierEntry.run_id == left_id))
    assert entry is not None
    attempt = FetchAttempt(
        run_id=left_id,
        frontier_entry_id=entry.id,
        attempt_number=1,
        status_code=200,
        final_url=entry.normalized_url,
        content_type="text/html",
        latency_ms=12,
        response_headers={"etag": '"test"'},
        request_headers={},
        redirect_chain=[],
    )
    db_session.add(attempt)
    db_session.flush()
    html = (
        b"<html><head><title>Stored page</title></head><body><main><h1>Stored</h1>"
        b"<p>Real stored parser input.</p></main></body></html>"
    )
    attempt.raw_body_key = get_blob_store(get_settings()).put_html(left_id, attempt.id, html)
    resource = WebResource(
        normalized_url=entry.normalized_url,
        canonical_url=entry.normalized_url,
        host=entry.host,
    )
    db_session.add(resource)
    db_session.flush()
    cluster = DuplicateCluster(member_count=1)
    db_session.add(cluster)
    db_session.flush()
    document = Document(
        run_id=left_id,
        frontier_entry_id=entry.id,
        fetch_attempt_id=attempt.id,
        resource_id=resource.id,
        version_number=1,
        is_current=True,
        change_kind=ChangeKind.INITIAL,
        url=entry.normalized_url,
        canonical_url=entry.normalized_url,
        host=entry.host,
        title="Stored page",
        description="Stored description",
        language="en",
        headings=["Stored"],
        main_text="Stored Real stored parser input.",
        text_length=32,
        content_hash="a" * 64,
        simhash="0000000000000001",
        simhash_bands=[1, 2, 3, 4],
        duplicate_cluster_id=cluster.id,
        extraction_confidence=0.9,
        parser_name="trafilatura",
        parser_version="2",
        extraction_warnings=[],
    )
    db_session.add(document)
    db_session.flush()
    cluster.representative_document_id = document.id
    resource.current_document_id = document.id
    db_session.add(
        ExtractionAttempt(
            run_id=left_id,
            fetch_attempt_id=attempt.id,
            document_id=document.id,
            parser_name="trafilatura",
            parser_version="2",
            succeeded=True,
            promoted=True,
            confidence=0.9,
            text_length=32,
            warnings=[],
            duration_ms=3,
        )
    )
    db_session.commit()

    listed = cast(
        httpx.Response,
        api_client.get(f"/api/v1/documents?run_id={left_id}&page_size=1"),
    )
    assert _json(listed)["total"] == 1
    document_id = str(document.id)
    for suffix in ("", "/versions", "/diff", "/parser-attempts", "/duplicate-cluster", "/raw"):
        assert (
            cast(
                httpx.Response, api_client.get(f"/api/v1/documents/{document_id}{suffix}")
            ).status_code
            == 200
        )
    preview = cast(
        httpx.Response, api_client.post(f"/api/v1/documents/{document_id}/reparse-preview")
    )
    assert _json(preview)["title"] == "Stored page"

    class FakeDocumentIndex:
        schema_version = 2

        def __init__(self, _settings: object) -> None:
            pass

        def index_document(self, _document: Document) -> str:
            return "atlas-documents-write"

        def search(self, _query: str, **_kwargs: object) -> dict[str, object]:
            return {
                "total": 1,
                "took_ms": 1,
                "page": 1,
                "page_size": 20,
                "next_cursor": None,
                "facets": {},
                "items": [{"document_id": document_id}],
            }

    monkeypatch.setattr("atlas.api.routes.documents.DocumentIndex", FakeDocumentIndex)
    monkeypatch.setattr("atlas.api.routes.search.DocumentIndex", FakeDocumentIndex)
    assert (
        _json(cast(httpx.Response, api_client.post(f"/api/v1/documents/{document_id}/reindex")))[
            "status"
        ]
        == "indexed"
    )
    assert _json(cast(httpx.Response, api_client.get("/api/v1/search?query=stored")))["total"] == 1
    comparison = cast(
        httpx.Response,
        api_client.get(
            f"/api/v1/operations/runs/compare?left_run_id={left_id}&right_run_id={right_id}"
        ),
    )
    assert comparison.status_code == 200
