import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from redis import Redis
from rq import Queue
from sqlalchemy import case, func, select

from atlas.api.dependencies import DbSession
from atlas.audit import record_audit
from atlas.auth import Principal, require_admin
from atlas.config import get_settings
from atlas.enums import IncidentStatus, IndexBuildStatus
from atlas.models import (
    CrawlRun,
    Document,
    DomainState,
    FetchAttempt,
    IndexBuild,
    MetricSample,
    OperationalIncident,
)
from atlas.schemas import IncidentRead, IndexBuildRead
from atlas.services.runs import get_run_counters

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/domains")
def domain_health(session: DbSession, run_id: uuid.UUID | None = None) -> list[dict[str, object]]:
    filters = [DomainState.run_id == run_id] if run_id else []
    attempts = (
        select(
            FetchAttempt.run_id.label("run_id"),
            func.coalesce(FetchAttempt.final_url, "").label("final_url"),
            func.count(FetchAttempt.id).label("attempts"),
            func.avg(FetchAttempt.latency_ms).label("avg_latency"),
            func.sum(case((FetchAttempt.status_code.between(200, 399), 1), else_=0)).label(
                "successes"
            ),
        )
        .group_by(FetchAttempt.run_id, FetchAttempt.final_url)
        .subquery()
    )
    states = list(
        session.scalars(
            select(DomainState)
            .where(*filters)
            .order_by(DomainState.consecutive_failures.desc(), DomainState.host)
        )
    )
    results: list[dict[str, object]] = []
    for state in states:
        run_attempts = session.execute(
            select(
                func.count(FetchAttempt.id),
                func.avg(FetchAttempt.latency_ms),
                func.sum(case((FetchAttempt.status_code.between(200, 399), 1), else_=0)),
            ).where(
                FetchAttempt.run_id == state.run_id,
                FetchAttempt.final_url.ilike(f"%://{state.host}/%"),
            )
        ).one()
        total = int(run_attempts[0] or 0)
        successes = int(run_attempts[2] or 0)
        results.append(
            {
                "run_id": str(state.run_id),
                "host": state.host,
                "robots_status": state.robots_status_code,
                "crawl_delay_ms": state.crawl_delay_ms,
                "next_allowed_at": state.next_allowed_at,
                "attempts": total,
                "success_rate": round(successes / total, 3) if total else None,
                "average_latency_ms": round(float(run_attempts[1]), 2)
                if run_attempts[1] is not None
                else None,
                "consecutive_failures": state.consecutive_failures,
                "last_success_at": state.last_success_at,
                "last_failure_at": state.last_failure_at,
            }
        )
    _ = attempts
    return results


@router.get("/metrics/timeseries")
def metrics_timeseries(
    session: DbSession,
    metric_name: str,
    run_id: uuid.UUID | None = None,
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=2000, ge=1, le=10_000),
) -> list[dict[str, object]]:
    filters = [
        MetricSample.metric_name == metric_name,
        MetricSample.observed_at >= datetime.now(UTC) - timedelta(hours=hours),
    ]
    if run_id:
        filters.append(MetricSample.run_id == run_id)
    samples = list(
        session.scalars(
            select(MetricSample).where(*filters).order_by(MetricSample.observed_at).limit(limit)
        )
    )
    return [
        {
            "metric_name": sample.metric_name,
            "value": sample.value,
            "labels": sample.labels,
            "observed_at": sample.observed_at,
        }
        for sample in samples
    ]


@router.get("/incidents", response_model=list[IncidentRead])
def list_incidents(
    session: DbSession,
    incident_status: IncidentStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OperationalIncident]:
    filters = [OperationalIncident.status == incident_status] if incident_status else []
    return list(
        session.scalars(
            select(OperationalIncident)
            .where(*filters)
            .order_by(OperationalIncident.created_at.desc())
            .limit(limit)
        )
    )


@router.post("/incidents/{incident_id}/acknowledge", response_model=IncidentRead)
def acknowledge_incident(
    incident_id: uuid.UUID,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> OperationalIncident:
    incident = session.get(OperationalIncident, incident_id)
    if incident is None:
        raise LookupError("Incident not found")
    incident.status = IncidentStatus.ACKNOWLEDGED
    incident.acknowledged_at = datetime.now(UTC)
    record_audit(session, principal, "incident.acknowledge", "incident", str(incident.id))
    session.commit()
    return incident


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentRead)
def resolve_incident(
    incident_id: uuid.UUID,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> OperationalIncident:
    incident = session.get(OperationalIncident, incident_id)
    if incident is None:
        raise LookupError("Incident not found")
    incident.status = IncidentStatus.RESOLVED
    incident.resolved_at = datetime.now(UTC)
    record_audit(session, principal, "incident.resolve", "incident", str(incident.id))
    session.commit()
    return incident


@router.post("/index-builds", response_model=IndexBuildRead, status_code=status.HTTP_202_ACCEPTED)
def create_index_build(
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> IndexBuild:
    build = IndexBuild(status=IndexBuildStatus.PENDING, schema_version=2)
    session.add(build)
    session.flush()
    settings = get_settings()
    Queue(
        "atlas-index",
        connection=Redis.from_url(settings.redis_url, password=settings.redis_password or None),
    ).enqueue(
        "atlas.jobs.run_index_build",
        str(build.id),
        job_id=f"index-build-{build.id}",
        job_timeout=7200,
        result_ttl=86_400,
        failure_ttl=604_800,
    )
    record_audit(session, principal, "index_build.create", "index_build", str(build.id))
    session.commit()
    return build


@router.get("/index-builds", response_model=list[IndexBuildRead])
def list_index_builds(
    session: DbSession, limit: int = Query(default=50, ge=1, le=200)
) -> list[IndexBuild]:
    return list(
        session.scalars(select(IndexBuild).order_by(IndexBuild.created_at.desc()).limit(limit))
    )


@router.get("/runs/compare")
def compare_runs(
    left_run_id: uuid.UUID, right_run_id: uuid.UUID, session: DbSession
) -> dict[str, object]:
    left = session.get(CrawlRun, left_run_id)
    right = session.get(CrawlRun, right_run_id)
    if left is None or right is None:
        raise LookupError("One or both crawl runs were not found")
    left_counters = get_run_counters(session, left.id)
    right_counters = get_run_counters(session, right.id)
    left_documents = {
        item[0]: item[1]
        for item in session.execute(
            select(Document.canonical_url, Document.content_hash).where(Document.run_id == left.id)
        )
    }
    right_documents = {
        item[0]: item[1]
        for item in session.execute(
            select(Document.canonical_url, Document.content_hash).where(Document.run_id == right.id)
        )
    }
    return {
        "left": {"run_id": str(left.id), "counters": left_counters.model_dump()},
        "right": {"run_id": str(right.id), "counters": right_counters.model_dump()},
        "new_urls": sorted(set(right_documents) - set(left_documents))[:1000],
        "removed_urls": sorted(set(left_documents) - set(right_documents))[:1000],
        "changed_urls": sorted(
            url
            for url in set(left_documents) & set(right_documents)
            if left_documents[url] != right_documents[url]
        )[:1000],
    }
