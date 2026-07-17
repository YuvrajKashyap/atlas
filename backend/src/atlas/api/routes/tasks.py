import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement

from atlas.api.dependencies import DbSession
from atlas.audit import record_audit
from atlas.auth import Principal, require_admin
from atlas.enums import PipelineTaskStatus, PipelineTaskType
from atlas.models import PipelineTask, WorkerHeartbeat
from atlas.schemas import PipelineTaskRead, WorkerRead

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/tasks", response_model=list[PipelineTaskRead])
def list_tasks(
    session: DbSession,
    run_id: uuid.UUID | None = None,
    task_status: PipelineTaskStatus | None = None,
    task_type: PipelineTaskType | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PipelineTask]:
    filters: list[ColumnElement[bool]] = []
    if run_id:
        filters.append(PipelineTask.run_id == run_id)
    if task_status:
        filters.append(PipelineTask.status == task_status)
    if task_type:
        filters.append(PipelineTask.task_type == task_type)
    return list(
        session.scalars(
            select(PipelineTask)
            .where(*filters)
            .order_by(PipelineTask.created_at.desc())
            .limit(limit)
        )
    )


@router.get("/dead-letter", response_model=list[PipelineTaskRead])
def list_dead_letter(
    session: DbSession, limit: int = Query(default=100, ge=1, le=500)
) -> list[PipelineTask]:
    return list(
        session.scalars(
            select(PipelineTask)
            .where(PipelineTask.status == PipelineTaskStatus.DEAD_LETTERED)
            .order_by(PipelineTask.completed_at.desc())
            .limit(limit)
        )
    )


@router.post("/tasks/{task_id}/retry", response_model=PipelineTaskRead)
def retry_task(
    task_id: uuid.UUID,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> PipelineTask:
    task = session.get(PipelineTask, task_id)
    if task is None:
        raise LookupError("Pipeline task not found")
    if task.status != PipelineTaskStatus.DEAD_LETTERED:
        raise ValueError("Only dead-lettered tasks can be retried")
    task.status = PipelineTaskStatus.RETRY_SCHEDULED
    task.available_at = datetime.now(UTC)
    task.completed_at = None
    task.last_error_type = None
    task.last_error_message = None
    task.max_attempts = max(task.max_attempts, task.attempt_count + 1)
    record_audit(session, principal, "pipeline_task.retry", "pipeline_task", str(task.id))
    session.commit()
    return task


@router.post("/tasks/{task_id}/cancel", response_model=PipelineTaskRead)
def cancel_task(
    task_id: uuid.UUID,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> PipelineTask:
    task = session.get(PipelineTask, task_id)
    if task is None:
        raise LookupError("Pipeline task not found")
    if task.status == PipelineTaskStatus.SUCCEEDED:
        raise ValueError("Succeeded tasks cannot be cancelled")
    task.status = PipelineTaskStatus.CANCELLED
    task.completed_at = datetime.now(UTC)
    task.lease_token = None
    task.lease_expires_at = None
    record_audit(session, principal, "pipeline_task.cancel", "pipeline_task", str(task.id))
    session.commit()
    return task


@router.get("/workers", response_model=list[WorkerRead])
def list_workers(session: DbSession) -> list[WorkerHeartbeat]:
    return list(
        session.scalars(select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen_at.desc()))
    )
