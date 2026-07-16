from fastapi import APIRouter
from opensearchpy import OpenSearchException
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text

from atlas.api.dependencies import DbSession
from atlas.config import get_settings
from atlas.indexer import DocumentIndex

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
def system_status(session: DbSession) -> dict[str, object]:
    settings = get_settings()
    session.execute(text("SELECT 1"))
    try:
        redis_ok = bool(Redis.from_url(settings.redis_url).ping())
    except RedisError:
        redis_ok = False
    try:
        index_health = DocumentIndex(settings).health()
    except OpenSearchException:
        index_health = {"status": "unavailable"}
    return {
        "status": "ok" if redis_ok and index_health.get("status") != "unavailable" else "degraded",
        "postgres": "ok",
        "redis": "ok" if redis_ok else "unavailable",
        "opensearch": index_health,
    }
