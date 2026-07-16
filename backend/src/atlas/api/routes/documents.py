import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, or_, select

from atlas.api.dependencies import DbSession
from atlas.blob_store import LocalBlobStore
from atlas.config import get_settings
from atlas.indexer import DocumentIndex
from atlas.models import Document, FetchAttempt
from atlas.schemas import DocumentRead, DocumentSummary
from atlas.services.runs import get_run_or_raise

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def list_documents(
    session: DbSession,
    run_id: uuid.UUID,
    host: str | None = None,
    query: str | None = None,
    duplicates: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> dict[str, object]:
    get_run_or_raise(session, run_id)
    filters = [Document.run_id == run_id]
    if host:
        filters.append(Document.host == host)
    if query:
        filters.append(or_(Document.title.ilike(f"%{query}%"), Document.url.ilike(f"%{query}%")))
    if duplicates is True:
        filters.append(Document.duplicate_of_document_id.is_not(None))
    elif duplicates is False:
        filters.append(Document.duplicate_of_document_id.is_(None))
    total = session.scalar(select(func.count()).select_from(Document).where(*filters)) or 0
    documents = list(
        session.scalars(
            select(Document)
            .where(*filters)
            .order_by(Document.extracted_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            DocumentSummary.model_validate(item).model_dump(mode="json") for item in documents
        ],
    }


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: uuid.UUID, session: DbSession) -> DocumentRead:
    document = session.get(Document, document_id)
    if document is None:
        raise LookupError("Document not found")
    return DocumentRead.model_validate(document)


@router.get("/{document_id}/raw", response_class=PlainTextResponse)
def get_raw_document(document_id: uuid.UUID, session: DbSession) -> PlainTextResponse:
    document = session.get(Document, document_id)
    if document is None:
        raise LookupError("Document not found")
    attempt = session.get(FetchAttempt, document.fetch_attempt_id)
    if attempt is None or not attempt.raw_body_key:
        raise LookupError("Raw response is not available")
    body = LocalBlobStore(get_settings().raw_store_path).get_html(attempt.raw_body_key)
    return PlainTextResponse(
        body.decode("utf-8", errors="replace"),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="atlas-{document.id}.html.txt"'},
    )


@router.post("/{document_id}/reindex")
def reindex_document(document_id: uuid.UUID, session: DbSession) -> dict[str, str]:
    document = session.get(Document, document_id)
    if document is None:
        raise LookupError("Document not found")
    index_name = DocumentIndex(get_settings()).index_document(document)
    document.index_name = index_name
    document.indexed_at = datetime.now(UTC)
    session.commit()
    return {"status": "indexed", "index": index_name}
