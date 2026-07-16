import uuid
from typing import Any

from sqlalchemy.orm import Session

from atlas.models import CrawlEvent


def emit_event(
    session: Session,
    run_id: uuid.UUID,
    event_type: str,
    *,
    frontier_entry_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> CrawlEvent:
    event = CrawlEvent(
        run_id=run_id,
        frontier_entry_id=frontier_entry_id,
        event_type=event_type,
        payload=payload or {},
    )
    session.add(event)
    return event
