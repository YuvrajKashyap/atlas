import uuid

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from atlas.api.dependencies import DbSession
from atlas.enums import FrontierStatus
from atlas.models import FetchAttempt, FrontierEntry
from atlas.schemas import FetchAttemptRead, FrontierEntryRead
from atlas.services.runs import get_run_or_raise

router = APIRouter(prefix="/frontier", tags=["frontier"])


@router.get("")
def list_frontier(
    session: DbSession,
    run_id: uuid.UUID,
    status: FrontierStatus | None = None,
    host: str | None = None,
    query: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    get_run_or_raise(session, run_id)
    filters = [FrontierEntry.run_id == run_id]
    if status is not None:
        filters.append(FrontierEntry.status == status)
    if host:
        filters.append(FrontierEntry.host == host)
    if query:
        filters.append(
            or_(
                FrontierEntry.url.ilike(f"%{query}%"),
                FrontierEntry.normalized_url.ilike(f"%{query}%"),
            )
        )
    total = session.scalar(select(func.count()).select_from(FrontierEntry).where(*filters)) or 0
    entries = list(
        session.scalars(
            select(FrontierEntry)
            .where(*filters)
            .order_by(FrontierEntry.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            FrontierEntryRead.model_validate(entry).model_dump(mode="json") for entry in entries
        ],
    }


@router.get("/{entry_id}", response_model=FrontierEntryRead)
def get_frontier_entry(entry_id: uuid.UUID, session: DbSession) -> FrontierEntryRead:
    entry = session.get(FrontierEntry, entry_id)
    if entry is None:
        raise LookupError("Frontier entry not found")
    return FrontierEntryRead.model_validate(entry)


@router.get("/{entry_id}/attempts", response_model=list[FetchAttemptRead])
def list_fetch_attempts(entry_id: uuid.UUID, session: DbSession) -> list[FetchAttemptRead]:
    entry = session.get(FrontierEntry, entry_id)
    if entry is None:
        raise LookupError("Frontier entry not found")
    attempts = list(
        session.scalars(
            select(FetchAttempt)
            .where(FetchAttempt.frontier_entry_id == entry_id)
            .order_by(FetchAttempt.attempt_number.desc())
        )
    )
    return [FetchAttemptRead.model_validate(attempt) for attempt in attempts]
