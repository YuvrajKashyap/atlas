import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from atlas.api.dependencies import DbSession
from atlas.audit import record_audit
from atlas.auth import Principal, require_admin
from atlas.models import CrawlEvent, CrawlRun
from atlas.schemas import CrawlEventRead, CrawlRunCreate, CrawlRunRead
from atlas.services.runs import (
    create_run,
    get_run_or_raise,
    serialize_run,
    start_run,
    stop_run,
)

router = APIRouter(prefix="/crawl-runs", tags=["crawl-runs"])


@router.post("", response_model=CrawlRunRead, status_code=status.HTTP_201_CREATED)
def create_crawl_run(
    request: CrawlRunCreate,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> CrawlRunRead:
    run = create_run(session, request)
    record_audit(session, principal, "crawl_run.create", "crawl_run", str(run.id))
    session.commit()
    return serialize_run(session, run)


@router.get("", response_model=list[CrawlRunRead])
def list_crawl_runs(
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[CrawlRunRead]:
    runs = list(session.scalars(select(CrawlRun).order_by(CrawlRun.created_at.desc()).limit(limit)))
    return [serialize_run(session, run) for run in runs]


@router.get("/{run_id}", response_model=CrawlRunRead)
def get_crawl_run(run_id: uuid.UUID, session: DbSession) -> CrawlRunRead:
    return serialize_run(session, get_run_or_raise(session, run_id))


@router.post("/{run_id}/start", response_model=CrawlRunRead)
def start_crawl_run(
    run_id: uuid.UUID,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> CrawlRunRead:
    run = start_run(session, run_id)
    record_audit(session, principal, "crawl_run.start", "crawl_run", str(run.id))
    session.commit()
    return serialize_run(session, run)


@router.post("/{run_id}/stop", response_model=CrawlRunRead)
def stop_crawl_run(
    run_id: uuid.UUID,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> CrawlRunRead:
    run = stop_run(session, run_id)
    record_audit(session, principal, "crawl_run.stop", "crawl_run", str(run.id))
    session.commit()
    return serialize_run(session, run)


@router.get("/{run_id}/events", response_model=list[CrawlEventRead])
def list_crawl_events(
    run_id: uuid.UUID,
    session: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CrawlEventRead]:
    get_run_or_raise(session, run_id)
    events = list(
        session.scalars(
            select(CrawlEvent)
            .where(CrawlEvent.run_id == run_id)
            .order_by(CrawlEvent.created_at.desc())
            .limit(limit)
        )
    )
    return [CrawlEventRead.model_validate(event) for event in events]
