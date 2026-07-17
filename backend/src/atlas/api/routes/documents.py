import difflib
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, or_, select

from atlas.api.dependencies import DbSession
from atlas.audit import record_audit
from atlas.auth import Principal, require_admin
from atlas.blob_store import get_blob_store
from atlas.config import get_settings
from atlas.extractor import extract_page
from atlas.indexer import DocumentIndex
from atlas.models import Document, DuplicateCluster, ExtractionAttempt, FetchAttempt
from atlas.pagination import decode_cursor, encode_cursor
from atlas.schemas import DocumentRead, DocumentSummary, ExtractionAttemptRead
from atlas.services.runs import get_run_or_raise

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def list_documents(
    session: DbSession,
    run_id: uuid.UUID,
    host: str | None = None,
    query: str | None = None,
    duplicates: bool | None = None,
    cursor: str | None = Query(default=None, max_length=1000),
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
    statement = select(Document).where(*filters)
    if cursor:
        cursor_time, cursor_id = decode_cursor(cursor)
        statement = statement.where(
            or_(
                Document.extracted_at < cursor_time,
                (Document.extracted_at == cursor_time) & (Document.id < cursor_id),
            )
        )
    elif page > 1:
        statement = statement.offset((page - 1) * page_size)
    documents = list(
        session.scalars(
            statement.order_by(Document.extracted_at.desc(), Document.id.desc()).limit(
                page_size + 1
            )
        )
    )
    has_more = len(documents) > page_size
    documents = documents[:page_size]
    next_cursor = (
        encode_cursor(documents[-1].extracted_at, documents[-1].id)
        if has_more and documents
        else None
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "next_cursor": next_cursor,
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


@router.get("/{document_id}/versions", response_model=list[DocumentSummary])
def list_document_versions(document_id: uuid.UUID, session: DbSession) -> list[Document]:
    document = session.get(Document, document_id)
    if document is None:
        raise LookupError("Document not found")
    if document.resource_id is None:
        return [document]
    return list(
        session.scalars(
            select(Document)
            .where(Document.resource_id == document.resource_id)
            .order_by(Document.version_number.desc())
        )
    )


@router.get("/{document_id}/parser-attempts", response_model=list[ExtractionAttemptRead])
def list_parser_attempts(document_id: uuid.UUID, session: DbSession) -> list[ExtractionAttempt]:
    document = session.get(Document, document_id)
    if document is None:
        raise LookupError("Document not found")
    return list(
        session.scalars(
            select(ExtractionAttempt)
            .where(ExtractionAttempt.fetch_attempt_id == document.fetch_attempt_id)
            .order_by(ExtractionAttempt.created_at.desc())
        )
    )


@router.get("/{document_id}/diff")
def diff_document_versions(
    document_id: uuid.UUID,
    session: DbSession,
    against_id: uuid.UUID | None = None,
) -> dict[str, object]:
    document = session.get(Document, document_id)
    if document is None:
        raise LookupError("Document not found")
    comparison_id = against_id or document.previous_version_id
    previous = session.get(Document, comparison_id) if comparison_id else None
    if previous is None:
        return {"document_id": str(document.id), "against_id": None, "diff": []}
    diff = list(
        difflib.unified_diff(
            previous.main_text.splitlines(),
            document.main_text.splitlines(),
            fromfile=f"version-{previous.version_number}",
            tofile=f"version-{document.version_number}",
            lineterm="",
            n=3,
        )
    )
    return {
        "document_id": str(document.id),
        "against_id": str(previous.id),
        "change_kind": document.change_kind.value,
        "diff": diff[:5000],
        "truncated": len(diff) > 5000,
    }


@router.post("/{document_id}/reparse-preview")
def reparse_preview(
    document_id: uuid.UUID,
    session: DbSession,
    _principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, object]:
    document = session.get(Document, document_id)
    if document is None:
        raise LookupError("Document not found")
    attempt = session.get(FetchAttempt, document.fetch_attempt_id)
    if attempt is None or not attempt.raw_body_key:
        raise LookupError("Raw response is not available")
    raw = (
        get_blob_store(get_settings())
        .get_html(attempt.raw_body_key)
        .decode("utf-8", errors="replace")
    )
    extracted = extract_page(raw, attempt.final_url or document.url)
    return {
        "document_id": str(document.id),
        "parser_name": extracted.parser_name,
        "parser_version": extracted.parser_version,
        "title": extracted.title,
        "description": extracted.description,
        "canonical_url": extracted.canonical_url,
        "headings": extracted.headings,
        "main_text": extracted.main_text,
        "text_length": len(extracted.main_text),
        "confidence": extracted.confidence,
        "warnings": extracted.warnings,
        "outbound_links": extracted.links,
        "changed": extracted.content_hash != document.content_hash,
    }


@router.get("/{document_id}/duplicate-cluster")
def get_duplicate_cluster(document_id: uuid.UUID, session: DbSession) -> dict[str, object]:
    document = session.get(Document, document_id)
    if document is None or document.duplicate_cluster_id is None:
        raise LookupError("Document is not part of a duplicate cluster")
    cluster = session.get(DuplicateCluster, document.duplicate_cluster_id)
    if cluster is None:
        raise LookupError("Duplicate cluster not found")
    members = list(
        session.scalars(
            select(Document)
            .where(Document.duplicate_cluster_id == cluster.id)
            .order_by(Document.extracted_at.desc())
        )
    )
    return {
        "id": str(cluster.id),
        "representative_document_id": str(cluster.representative_document_id)
        if cluster.representative_document_id
        else None,
        "member_count": cluster.member_count,
        "members": [
            DocumentSummary.model_validate(item).model_dump(mode="json") for item in members
        ],
    }


@router.get("/{document_id}/raw", response_class=PlainTextResponse)
def get_raw_document(document_id: uuid.UUID, session: DbSession) -> PlainTextResponse:
    document = session.get(Document, document_id)
    if document is None:
        raise LookupError("Document not found")
    attempt = session.get(FetchAttempt, document.fetch_attempt_id)
    if attempt is None or not attempt.raw_body_key:
        raise LookupError("Raw response is not available")
    body = get_blob_store(get_settings()).get_html(attempt.raw_body_key)
    return PlainTextResponse(
        body.decode("utf-8", errors="replace"),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="atlas-{document.id}.html.txt"'},
    )


@router.post("/{document_id}/reindex")
def reindex_document(
    document_id: uuid.UUID,
    session: DbSession,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, str]:
    document = session.get(Document, document_id)
    if document is None:
        raise LookupError("Document not found")
    index_name = DocumentIndex(get_settings()).index_document(document)
    document.index_name = index_name
    document.indexed_at = datetime.now(UTC)
    record_audit(session, principal, "document.reindex", "document", str(document.id))
    session.commit()
    return {"status": "indexed", "index": index_name}
