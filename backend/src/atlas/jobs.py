import hashlib
import uuid
from datetime import UTC, datetime

import httpx
import structlog
from opensearchpy import OpenSearchException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from atlas.blob_store import LocalBlobStore
from atlas.config import get_settings
from atlas.db import SessionLocal
from atlas.enums import CrawlRunStatus, FetchOutcome, FrontierStatus
from atlas.events import emit_event
from atlas.extractor import extract_page
from atlas.fetcher import (
    RedirectPolicyError,
    ResponseTooLargeError,
    fetch_url,
    is_html_content_type,
)
from atlas.indexer import DocumentIndex
from atlas.models import (
    AllowedDomain,
    CrawlRun,
    DiscoveredLink,
    Document,
    DomainState,
    FetchAttempt,
    FrontierEntry,
)
from atlas.retry import is_transient_status, retry_delay
from atlas.robots import RobotsService
from atlas.urls import UrlPolicyError, host_for_url, is_host_allowed

logger = structlog.get_logger(__name__)
settings = get_settings()


def _schedule_failure(
    run: CrawlRun,
    entry: FrontierEntry,
    attempt: FetchAttempt,
    *,
    error_type: str,
    error_message: str,
    transient: bool,
) -> None:
    now = datetime.now(UTC)
    attempt.finished_at = now
    attempt.error_type = error_type
    attempt.error_message = error_message[:2000]
    attempt.outcome = FetchOutcome.TRANSIENT_ERROR if transient else FetchOutcome.PERMANENT_ERROR
    entry.last_error_type = error_type
    entry.last_error_message = error_message[:2000]
    entry.lease_expires_at = None
    entry.rq_job_id = None
    if transient and entry.retry_count < run.max_retries:
        entry.retry_count += 1
        entry.status = FrontierStatus.RETRY_SCHEDULED
        entry.next_fetch_at = now + retry_delay(entry.retry_count, str(entry.id))
    else:
        entry.status = FrontierStatus.FAILED


def process_frontier_entry(entry_id: str) -> dict[str, str]:
    frontier_id = uuid.UUID(entry_id)
    log = logger.bind(frontier_entry_id=entry_id)
    with SessionLocal() as session:
        entry = session.get(FrontierEntry, frontier_id)
        if entry is None:
            return {"status": "missing"}
        run = session.get(CrawlRun, entry.run_id)
        if run is None:
            return {"status": "missing_run"}
        if entry.status != FrontierStatus.QUEUED:
            return {"status": "idempotent_skip", "frontier_status": entry.status.value}
        if run.status not in {CrawlRunStatus.RUNNING, CrawlRunStatus.STOPPING}:
            entry.status = FrontierStatus.BUDGET_EXHAUSTED
            entry.lease_expires_at = None
            session.commit()
            return {"status": "run_not_active"}

        allowed_rows = list(
            session.scalars(select(AllowedDomain).where(AllowedDomain.run_id == run.id))
        )
        allowed_domains = [(item.domain, item.include_subdomains) for item in allowed_rows]
        entry.status = FrontierStatus.FETCHING
        entry.fetch_attempt_count += 1
        attempt = FetchAttempt(
            run_id=run.id,
            frontier_entry_id=entry.id,
            attempt_number=entry.fetch_attempt_count,
        )
        session.add(attempt)
        emit_event(
            session,
            run.id,
            "fetch.started",
            frontier_entry_id=entry.id,
            payload={"url": entry.normalized_url, "attempt": attempt.attempt_number},
        )
        session.commit()

        robots = RobotsService(settings)
        try:
            decision = robots.decide(session, run, entry, allowed_domains)
        except Exception as exc:  # defensive boundary around third-party parsing/networking
            _schedule_failure(
                run,
                entry,
                attempt,
                error_type="robots_error",
                error_message=str(exc),
                transient=True,
            )
            emit_event(
                session,
                run.id,
                "robots.error",
                frontier_entry_id=entry.id,
                payload={"error": type(exc).__name__},
            )
            session.commit()
            return {"status": entry.status.value}

        entry.robots_allowed = decision.allowed
        domain_state = session.scalar(
            select(DomainState).where(DomainState.run_id == run.id, DomainState.host == entry.host)
        )
        if domain_state is not None:
            domain_state.crawl_delay_ms = decision.crawl_delay_ms

        if not decision.allowed:
            temporary = (
                decision.reason.startswith("robots_unavailable") or "temporary" in decision.reason
            )
            if temporary:
                _schedule_failure(
                    run,
                    entry,
                    attempt,
                    error_type="robots_temporarily_unavailable",
                    error_message=decision.reason,
                    transient=True,
                )
            else:
                attempt.finished_at = datetime.now(UTC)
                attempt.outcome = FetchOutcome.ROBOTS_BLOCKED
                attempt.error_type = "robots_blocked"
                attempt.error_message = decision.reason
                entry.status = FrontierStatus.ROBOTS_BLOCKED
                entry.blocked_reason = decision.reason
                entry.lease_expires_at = None
            emit_event(
                session,
                run.id,
                "robots.blocked",
                frontier_entry_id=entry.id,
                payload={"reason": decision.reason},
            )
            session.commit()
            return {"status": entry.status.value}

        emit_event(
            session,
            run.id,
            "robots.allowed",
            frontier_entry_id=entry.id,
            payload={"crawl_delay_ms": decision.crawl_delay_ms},
        )
        session.commit()

        try:
            result = fetch_url(
                run,
                entry.normalized_url,
                allowed_domains,
                allow_private_networks=settings.allow_private_networks,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            _schedule_failure(
                run,
                entry,
                attempt,
                error_type=type(exc).__name__,
                error_message=str(exc),
                transient=True,
            )
            emit_event(
                session,
                run.id,
                "fetch.retry_scheduled"
                if entry.status == FrontierStatus.RETRY_SCHEDULED
                else "fetch.failed",
                frontier_entry_id=entry.id,
                payload={"error": type(exc).__name__},
            )
            session.commit()
            return {"status": entry.status.value}
        except (UrlPolicyError, RedirectPolicyError, ResponseTooLargeError) as exc:
            _schedule_failure(
                run,
                entry,
                attempt,
                error_type=type(exc).__name__,
                error_message=str(exc),
                transient=False,
            )
            emit_event(
                session,
                run.id,
                "fetch.failed",
                frontier_entry_id=entry.id,
                payload={"error": type(exc).__name__, "message": str(exc)},
            )
            session.commit()
            return {"status": entry.status.value}

        attempt.status_code = result.status_code
        attempt.final_url = result.final_url
        attempt.redirect_chain = result.redirect_chain
        attempt.content_type = result.content_type
        attempt.response_size_bytes = len(result.body)
        attempt.latency_ms = result.latency_ms
        attempt.response_headers = result.headers
        attempt.finished_at = datetime.now(UTC)

        if not 200 <= result.status_code < 300:
            _schedule_failure(
                run,
                entry,
                attempt,
                error_type=f"http_{result.status_code}",
                error_message=f"HTTP request returned {result.status_code}",
                transient=is_transient_status(result.status_code),
            )
            emit_event(
                session,
                run.id,
                "fetch.retry_scheduled"
                if entry.status == FrontierStatus.RETRY_SCHEDULED
                else "fetch.failed",
                frontier_entry_id=entry.id,
                payload={"status_code": result.status_code},
            )
            session.commit()
            return {"status": entry.status.value}

        if not is_html_content_type(result.content_type):
            attempt.outcome = FetchOutcome.UNSUPPORTED_CONTENT
            entry.status = FrontierStatus.UNSUPPORTED_CONTENT
            entry.blocked_reason = f"content_type:{result.content_type or 'missing'}"
            entry.lease_expires_at = None
            emit_event(
                session,
                run.id,
                "fetch.unsupported_content",
                frontier_entry_id=entry.id,
                payload={"content_type": result.content_type},
            )
            session.commit()
            return {"status": entry.status.value}

        attempt.outcome = FetchOutcome.SUCCEEDED
        attempt.body_sha256 = hashlib.sha256(result.body).hexdigest()
        blob_store = LocalBlobStore(settings.raw_store_path)
        attempt.raw_body_key = blob_store.put_html(run.id, attempt.id, result.body)
        entry.status = FrontierStatus.FETCHED
        entry.last_crawled_at = datetime.now(UTC)
        emit_event(
            session,
            run.id,
            "fetch.succeeded",
            frontier_entry_id=entry.id,
            payload={
                "status_code": result.status_code,
                "latency_ms": result.latency_ms,
                "response_size_bytes": len(result.body),
            },
        )
        session.commit()

        entry.status = FrontierStatus.EXTRACTING
        session.commit()
        html = result.body.decode("utf-8", errors="replace")
        try:
            extracted = extract_page(html, result.final_url)
        except Exception as exc:
            _schedule_failure(
                run,
                entry,
                attempt,
                error_type="extraction_error",
                error_message=str(exc),
                transient=False,
            )
            emit_event(
                session,
                run.id,
                "extraction.failed",
                frontier_entry_id=entry.id,
                payload={"error": type(exc).__name__},
            )
            session.commit()
            return {"status": entry.status.value}

        existing_document = session.scalar(
            select(Document)
            .where(
                Document.run_id == run.id,
                Document.content_hash == extracted.content_hash,
                Document.duplicate_of_document_id.is_(None),
            )
            .order_by(Document.extracted_at)
            .limit(1)
        )
        document = Document(
            run_id=run.id,
            frontier_entry_id=entry.id,
            fetch_attempt_id=attempt.id,
            url=result.final_url,
            canonical_url=extracted.canonical_url,
            host=host_for_url(result.final_url),
            title=extracted.title,
            description=extracted.description,
            language=extracted.language,
            headings=extracted.headings,
            main_text=extracted.main_text,
            text_length=len(extracted.main_text),
            content_hash=extracted.content_hash,
            duplicate_of_document_id=existing_document.id if existing_document else None,
            extraction_confidence=extracted.confidence,
            parser_name=extracted.parser_name,
            parser_version=extracted.parser_version,
            extraction_warnings=extracted.warnings,
        )
        session.add(document)
        session.flush()

        accepted_count = 0
        for target_url in extracted.links[:500]:
            target_host = host_for_url(target_url)
            accepted = entry.depth < run.max_depth and is_host_allowed(target_host, allowed_domains)
            rejection_reason = None
            target_frontier_id = None
            if not accepted:
                rejection_reason = (
                    "max_depth_reached"
                    if entry.depth >= run.max_depth
                    else "outside_domain_allowlist"
                )
            else:
                statement = (
                    pg_insert(FrontierEntry)
                    .values(
                        id=uuid.uuid4(),
                        run_id=run.id,
                        url=target_url,
                        normalized_url=target_url,
                        host=target_host,
                        status=FrontierStatus.DISCOVERED,
                        priority=max(0, 100 - (entry.depth + 1) * 10),
                        depth=entry.depth + 1,
                        discovered_from_id=entry.id,
                        next_fetch_at=datetime.now(UTC),
                    )
                    .on_conflict_do_nothing(constraint="uq_frontier_run_normalized_url")
                    .returning(FrontierEntry.id)
                )
                target_frontier_id = session.scalar(statement)
                if target_frontier_id is None:
                    target_frontier_id = session.scalar(
                        select(FrontierEntry.id).where(
                            FrontierEntry.run_id == run.id,
                            FrontierEntry.normalized_url == target_url,
                        )
                    )
                    rejection_reason = "duplicate_url"
                else:
                    accepted_count += 1
            link_statement = (
                pg_insert(DiscoveredLink)
                .values(
                    id=uuid.uuid4(),
                    run_id=run.id,
                    source_frontier_id=entry.id,
                    target_url=target_url,
                    normalized_target_url=target_url,
                    target_frontier_id=target_frontier_id,
                    accepted=accepted,
                    rejection_reason=rejection_reason,
                )
                .on_conflict_do_nothing(constraint="uq_discovered_link_source_target")
            )
            session.execute(link_statement)

        emit_event(
            session,
            run.id,
            "extraction.succeeded",
            frontier_entry_id=entry.id,
            payload={
                "document_id": str(document.id),
                "text_length": document.text_length,
                "confidence": document.extraction_confidence,
                "links_discovered": len(extracted.links),
                "links_accepted": accepted_count,
            },
        )

        if existing_document is not None:
            entry.status = FrontierStatus.DUPLICATE_CONTENT
            entry.lease_expires_at = None
            emit_event(
                session,
                run.id,
                "document.duplicate_content",
                frontier_entry_id=entry.id,
                payload={
                    "document_id": str(document.id),
                    "duplicate_of_document_id": str(existing_document.id),
                },
            )
            session.commit()
            return {"status": entry.status.value, "document_id": str(document.id)}

        entry.status = FrontierStatus.INDEXING
        session.commit()
        try:
            document.index_name = DocumentIndex(settings).index_document(document)
        except OpenSearchException as exc:
            entry.status = FrontierStatus.FAILED
            entry.last_error_type = "index_error"
            entry.last_error_message = str(exc)[:2000]
            entry.lease_expires_at = None
            emit_event(
                session,
                run.id,
                "index.failed",
                frontier_entry_id=entry.id,
                payload={"document_id": str(document.id), "error": type(exc).__name__},
            )
            session.commit()
            return {"status": entry.status.value, "document_id": str(document.id)}

        document.indexed_at = datetime.now(UTC)
        entry.status = FrontierStatus.INDEXED
        entry.lease_expires_at = None
        entry.rq_job_id = None
        emit_event(
            session,
            run.id,
            "index.succeeded",
            frontier_entry_id=entry.id,
            payload={"document_id": str(document.id), "index": document.index_name},
        )
        session.commit()
        log.info("frontier_entry_processed", document_id=str(document.id))
        return {"status": entry.status.value, "document_id": str(document.id)}
