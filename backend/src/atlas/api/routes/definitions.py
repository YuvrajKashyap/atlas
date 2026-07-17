import uuid
from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from atlas.api.dependencies import DbSession
from atlas.audit import record_audit
from atlas.auth import Principal, require_admin
from atlas.models import CrawlDefinition, CrawlRun
from atlas.schemas import CrawlDefinitionCreate, CrawlDefinitionRead, CrawlRunCreate, CrawlRunRead
from atlas.services.runs import create_run, serialize_run, start_run

router = APIRouter(prefix="/crawl-definitions", tags=["crawl-definitions"])


@router.post("", response_model=CrawlDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_definition(
    request: CrawlDefinitionCreate,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> CrawlDefinition:
    if session.scalar(select(CrawlDefinition.id).where(CrawlDefinition.name == request.name)):
        raise ValueError("A crawl definition with this name already exists")
    try:
        timezone = ZoneInfo(request.schedule_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unknown schedule timezone") from exc
    next_run_at = None
    if request.schedule_cron:
        if not croniter.is_valid(request.schedule_cron):
            raise ValueError("Invalid cron expression")
        next_run_at = (
            croniter(request.schedule_cron, datetime.now(timezone))
            .get_next(datetime)
            .astimezone(UTC)
        )
    definition = CrawlDefinition(
        name=request.name.strip(),
        description=request.description,
        schedule_cron=request.schedule_cron,
        schedule_timezone=request.schedule_timezone,
        next_run_at=next_run_at,
        config=request.config.model_dump(mode="json"),
    )
    session.add(definition)
    session.flush()
    record_audit(
        session, principal, "crawl_definition.create", "crawl_definition", str(definition.id)
    )
    session.commit()
    return definition


@router.get("", response_model=list[CrawlDefinitionRead])
def list_definitions(
    session: DbSession, limit: int = Query(default=100, ge=1, le=200)
) -> list[CrawlDefinition]:
    return list(
        session.scalars(
            select(CrawlDefinition).order_by(CrawlDefinition.created_at.desc()).limit(limit)
        )
    )


@router.get("/{definition_id}", response_model=CrawlDefinitionRead)
def get_definition(definition_id: uuid.UUID, session: DbSession) -> CrawlDefinition:
    definition = session.get(CrawlDefinition, definition_id)
    if definition is None:
        raise LookupError("Crawl definition not found")
    return definition


@router.post("/{definition_id}/trigger", response_model=CrawlRunRead)
def trigger_definition(
    definition_id: uuid.UUID,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> CrawlRunRead:
    definition = session.get(CrawlDefinition, definition_id)
    if definition is None:
        raise LookupError("Crawl definition not found")
    request = CrawlRunCreate.model_validate(definition.config)
    previous_generation = session.scalar(
        select(func.max(CrawlRun.generation)).where(CrawlRun.definition_id == definition.id)
    )
    run = create_run(session, request, commit=False)
    run.definition_id = definition.id
    run.generation = (previous_generation or 0) + 1
    session.flush()
    start_run(session, run.id, commit=False)
    record_audit(
        session,
        principal,
        "crawl_definition.trigger",
        "crawl_definition",
        str(definition.id),
        payload={"run_id": str(run.id)},
    )
    session.commit()
    return serialize_run(session, run)


@router.post("/{definition_id}/toggle", response_model=CrawlDefinitionRead)
def toggle_definition(
    definition_id: uuid.UUID,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> CrawlDefinition:
    definition = session.get(CrawlDefinition, definition_id)
    if definition is None:
        raise LookupError("Crawl definition not found")
    definition.enabled = not definition.enabled
    record_audit(
        session,
        principal,
        "crawl_definition.toggle",
        "crawl_definition",
        str(definition.id),
        payload={"enabled": definition.enabled},
    )
    session.commit()
    return definition
