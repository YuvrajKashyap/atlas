import hashlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from opensearchpy import OpenSearchException

from atlas.api.dependencies import DbSession
from atlas.audit import record_audit
from atlas.auth import Principal, require_viewer
from atlas.config import get_settings
from atlas.indexer import DocumentIndex

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search_documents(
    session: DbSession,
    principal: Annotated[Principal, Depends(require_viewer)],
    query: str = Query(min_length=1, max_length=500),
    run_id: uuid.UUID | None = None,
    host: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    language: str | None = Query(default=None, max_length=32),
    change_kind: str | None = Query(default=None, max_length=40),
    current_only: bool = True,
    extracted_after: str | None = None,
    cursor: str | None = Query(default=None, max_length=1000),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    try:
        result = DocumentIndex(get_settings()).search(
            query,
            run_id=run_id,
            host=host,
            min_confidence=min_confidence,
            language=language,
            change_kind=change_kind,
            current_only=current_only,
            extracted_after=extracted_after,
            cursor=cursor,
            page=page,
            page_size=page_size,
        )
        record_audit(
            session,
            principal,
            "search.execute",
            "search",
            None,
            payload={
                "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "run_id": str(run_id) if run_id else None,
                "host": host,
                "result_count": int(result.get("total", 0)),
                "schema_version": DocumentIndex.schema_version,
            },
        )
        session.commit()
        return result
    except OpenSearchException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search index is unavailable",
        ) from exc
