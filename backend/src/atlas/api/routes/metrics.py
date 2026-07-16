import uuid

from fastapi import APIRouter

from atlas.api.dependencies import DbSession
from atlas.schemas import MetricsOverview
from atlas.services.metrics import metrics_overview
from atlas.services.runs import get_run_or_raise

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/overview", response_model=MetricsOverview)
def get_metrics_overview(run_id: uuid.UUID, session: DbSession) -> MetricsOverview:
    get_run_or_raise(session, run_id)
    return metrics_overview(session, run_id)
