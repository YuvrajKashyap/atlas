import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from atlas.models import DomainState


def acquire_fetch_permit(
    session: Session,
    *,
    run_id: uuid.UUID,
    host: str,
    delay_ms: int,
) -> datetime:
    """Serialize real request starts for a crawl domain and return the permit time."""
    while True:
        state = session.scalar(
            select(DomainState)
            .where(DomainState.run_id == run_id, DomainState.host == host)
            .with_for_update()
        )
        if state is None:
            session.execute(
                pg_insert(DomainState)
                .values(run_id=run_id, host=host)
                .on_conflict_do_nothing(constraint="uq_domain_state_run_host")
            )
            state = session.scalar(
                select(DomainState)
                .where(DomainState.run_id == run_id, DomainState.host == host)
                .with_for_update()
            )
        if state is None:
            raise RuntimeError("Unable to create domain politeness state")

        now = datetime.now(UTC)
        if state.next_allowed_at is not None and state.next_allowed_at > now:
            wait_seconds = (state.next_allowed_at - now).total_seconds()
            session.rollback()
            time.sleep(wait_seconds)
            continue

        effective_delay_ms = max(delay_ms, state.crawl_delay_ms or 0)
        state.next_allowed_at = now + timedelta(milliseconds=effective_delay_ms)
        session.commit()
        return now
