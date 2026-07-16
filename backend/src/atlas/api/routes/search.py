import uuid

from fastapi import APIRouter, HTTPException, Query, status
from opensearchpy import OpenSearchException

from atlas.config import get_settings
from atlas.indexer import DocumentIndex

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search_documents(
    query: str = Query(min_length=1, max_length=500),
    run_id: uuid.UUID | None = None,
    host: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    try:
        return DocumentIndex(get_settings()).search(
            query,
            run_id=run_id,
            host=host,
            min_confidence=min_confidence,
            page=page,
            page_size=page_size,
        )
    except OpenSearchException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search index is unavailable",
        ) from exc
