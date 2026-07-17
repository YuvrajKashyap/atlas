import hashlib
import os
import socket
import time
import uuid
from datetime import UTC, datetime

import structlog
from opensearchpy import OpenSearchException
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from atlas.blob_store import get_blob_store
from atlas.config import get_settings
from atlas.db import SessionLocal
from atlas.enums import (
    ChangeKind,
    CrawlRunStatus,
    FetchOutcome,
    FrontierStatus,
    IndexBuildStatus,
    IndexOperationStatus,
    ObservationOutcome,
    PipelineTaskStatus,
    PipelineTaskType,
)
from atlas.events import emit_event
from atlas.extractor import extract_page
from atlas.fetcher import (
    FetchNetworkError,
    FetchTimeoutError,
    RedirectPolicyError,
    ResponseTooLargeError,
    fetch_url,
    is_html_content_type,
)
from atlas.indexer import DocumentIndex
from atlas.models import (
    AllowedDomain,
    CrawlObservation,
    CrawlRun,
    DiscoveredLink,
    Document,
    DomainState,
    DuplicateCluster,
    ExtractionAttempt,
    FetchAttempt,
    FrontierEntry,
    IndexBuild,
    IndexOperation,
    PipelineTask,
    WebResource,
)
from atlas.retry import is_transient_status
from atlas.robots import RobotsService
from atlas.similarity import (
    classify_change,
    decode_simhash,
    encode_simhash,
    hamming_distance,
    simhash64,
    simhash_bands,
)
from atlas.sitemaps import MAX_SITEMAP_DOCUMENTS, discover_sitemaps
from atlas.tasking import (
    complete_task,
    create_pipeline_task,
    fail_task,
    heartbeat_task,
    upsert_worker_heartbeat,
)
from atlas.urls import UrlPolicyError, host_for_url, is_host_allowed

logger = structlog.get_logger(__name__)
settings = get_settings()


def _worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def _task_context(task_id: str, lease_token: str) -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(task_id), uuid.UUID(lease_token)


def _load_leased_task(
    session: Session, task_id: uuid.UUID, lease_token: uuid.UUID
) -> PipelineTask | None:
    task = session.get(PipelineTask, task_id)
    if (
        task is None
        or task.status != PipelineTaskStatus.LEASED
        or task.lease_token != lease_token
        or (task.lease_expires_at is not None and task.lease_expires_at <= datetime.now(UTC))
    ):
        return None
    return task


def _record_task_failure(
    task: PipelineTask,
    lease_token: uuid.UUID,
    *,
    error_type: str,
    error_message: str,
    transient: bool,
) -> dict[str, str]:
    with SessionLocal() as session:
        current = session.get(PipelineTask, task.id)
        if current is None:
            return {"status": "missing"}
        entry = session.get(FrontierEntry, current.frontier_entry_id)
        new_status = fail_task(
            session,
            current,
            lease_token,
            error_type=error_type,
            error_message=error_message,
            transient=transient,
        )
        if entry is not None:
            entry.last_error_type = error_type
            entry.last_error_message = error_message[:2000]
            entry.lease_expires_at = None
            entry.rq_job_id = None
            entry.status = (
                FrontierStatus.RETRY_SCHEDULED
                if new_status == PipelineTaskStatus.RETRY_SCHEDULED
                else FrontierStatus.FAILED
            )
            emit_event(
                session,
                current.run_id,
                "pipeline.retry_scheduled"
                if new_status == PipelineTaskStatus.RETRY_SCHEDULED
                else "pipeline.dead_lettered",
                frontier_entry_id=entry.id,
                payload={
                    "task_id": str(current.id),
                    "stage": current.task_type.value,
                    "error_type": error_type,
                },
            )
        session.commit()
        return {"status": new_status.value, "error_type": error_type}


def _find_resource(session: Session, run: CrawlRun, url: str) -> WebResource | None:
    return session.scalar(
        select(WebResource).where(
            WebResource.definition_id == run.definition_id,
            WebResource.normalized_url == url,
        )
    )


def _process_fetch(task: PipelineTask, lease_token: uuid.UUID) -> dict[str, str]:
    task_id = task.id
    with SessionLocal() as session:
        loaded_task = _load_leased_task(session, task_id, lease_token)
        if loaded_task is None:
            return {"status": "stale_lease"}
        task = loaded_task
        entry = session.get(FrontierEntry, task.frontier_entry_id)
        run = session.get(CrawlRun, task.run_id)
        if entry is None or run is None:
            return {"status": "missing_parent"}
        if run.status not in {CrawlRunStatus.RUNNING, CrawlRunStatus.STOPPING}:
            entry.status = FrontierStatus.BUDGET_EXHAUSTED
            complete_task(session, task.id, lease_token)
            session.commit()
            return {"status": "run_not_active"}
        allowed_rows = list(
            session.scalars(select(AllowedDomain).where(AllowedDomain.run_id == run.id))
        )
        allowed_domains = [(item.domain, item.include_subdomains) for item in allowed_rows]
        resource = _find_resource(session, run, entry.normalized_url)
        conditional_headers: dict[str, str] = {}
        if resource is not None:
            if resource.etag:
                conditional_headers["If-None-Match"] = resource.etag
            if resource.last_modified:
                conditional_headers["If-Modified-Since"] = resource.last_modified
        entry.status = FrontierStatus.FETCHING
        entry.fetch_attempt_count += 1
        attempt = FetchAttempt(
            run_id=run.id,
            frontier_entry_id=entry.id,
            attempt_number=entry.fetch_attempt_count,
            request_headers=conditional_headers,
        )
        session.add(attempt)
        session.flush()
        emit_event(
            session,
            run.id,
            "fetch.started",
            frontier_entry_id=entry.id,
            payload={"task_id": str(task.id), "attempt": attempt.attempt_number},
        )
        heartbeat_task(session, task.id, lease_token, lease_seconds=settings.task_lease_seconds)
        session.commit()

    with SessionLocal() as session:
        loaded_task = _load_leased_task(session, task_id, lease_token)
        if loaded_task is None:
            return {"status": "stale_lease"}
        task = loaded_task
        entry = session.get(FrontierEntry, task.frontier_entry_id)
        run = session.get(CrawlRun, task.run_id)
        attempt = session.scalar(
            select(FetchAttempt)
            .where(FetchAttempt.frontier_entry_id == task.frontier_entry_id)
            .order_by(FetchAttempt.attempt_number.desc())
            .limit(1)
        )
        if entry is None or run is None or attempt is None:
            return {"status": "missing_parent"}
        allowed_rows = list(
            session.scalars(select(AllowedDomain).where(AllowedDomain.run_id == run.id))
        )
        allowed_domains = [(item.domain, item.include_subdomains) for item in allowed_rows]
        resource = _find_resource(session, run, entry.normalized_url)

        try:
            decision = RobotsService(settings).decide(session, run, entry, allowed_domains)
            if not decision.allowed:
                temporary = "temporary" in decision.reason or decision.reason.startswith(
                    "robots_unavailable"
                )
                if temporary:
                    raise FetchNetworkError(decision.reason)
                now = datetime.now(UTC)
                attempt.finished_at = now
                attempt.outcome = FetchOutcome.ROBOTS_BLOCKED
                attempt.error_type = "robots_blocked"
                attempt.error_message = decision.reason
                entry.status = FrontierStatus.ROBOTS_BLOCKED
                entry.blocked_reason = decision.reason
                session.add(
                    CrawlObservation(
                        run_id=run.id,
                        resource_id=resource.id if resource else None,
                        fetch_attempt_id=attempt.id,
                        outcome=ObservationOutcome.ROBOTS_BLOCKED,
                    )
                )
                complete_task(session, task.id, lease_token)
                emit_event(
                    session,
                    run.id,
                    "robots.blocked",
                    frontier_entry_id=entry.id,
                    payload={"reason": decision.reason},
                )
                session.commit()
                return {"status": entry.status.value}

            domain_state = session.scalar(
                select(DomainState).where(
                    DomainState.run_id == run.id,
                    DomainState.host == entry.host,
                )
            )
            if (
                entry.depth == 0
                and decision.sitemaps
                and domain_state is not None
                and domain_state.sitemaps_discovered_at is None
            ):
                try:
                    sitemap_delay_ms = max(
                        250,
                        decision.crawl_delay_ms or run.per_domain_delay_ms or 1000,
                    )
                    sitemap_lease_seconds = max(
                        settings.task_lease_seconds,
                        30 + (MAX_SITEMAP_DOCUMENTS * sitemap_delay_ms // 1000),
                    )
                    heartbeat_task(
                        session,
                        task.id,
                        lease_token,
                        lease_seconds=sitemap_lease_seconds,
                    )
                    session.commit()
                    sitemap_result = discover_sitemaps(
                        run,
                        decision.sitemaps,
                        allowed_domains,
                        settings,
                        delay_ms=decision.crawl_delay_ms,
                    )
                    accepted_sitemaps = _discover_links(
                        session,
                        run=run,
                        entry=entry,
                        links=list(sitemap_result.urls),
                        allowed_domains=allowed_domains,
                        target_depth=0,
                    )
                    domain_state.sitemaps_discovered_at = datetime.now(UTC)
                    domain_state.sitemap_url_count = len(sitemap_result.urls)
                    emit_event(
                        session,
                        run.id,
                        "sitemap.discovered",
                        frontier_entry_id=entry.id,
                        payload={
                            "advertised": len(decision.sitemaps),
                            "documents_fetched": sitemap_result.documents_fetched,
                            "urls_found": len(sitemap_result.urls),
                            "urls_accepted": accepted_sitemaps,
                            "urls_rejected": sitemap_result.rejected_urls,
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "sitemap.discovery_failed",
                        run_id=str(run.id),
                        host=entry.host,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
                    emit_event(
                        session,
                        run.id,
                        "sitemap.failed",
                        frontier_entry_id=entry.id,
                        payload={"error_type": type(exc).__name__, "message": str(exc)[:500]},
                    )

            result = fetch_url(
                run,
                entry.normalized_url,
                allowed_domains,
                allow_private_networks=settings.allow_private_networks,
                conditional_headers=attempt.request_headers,
            )
        except (FetchTimeoutError, FetchNetworkError) as exc:
            attempt.finished_at = datetime.now(UTC)
            attempt.error_type = type(exc).__name__
            attempt.error_message = str(exc)[:2000]
            attempt.outcome = FetchOutcome.TRANSIENT_ERROR
            session.commit()
            return _record_task_failure(
                task,
                lease_token,
                error_type=type(exc).__name__,
                error_message=str(exc),
                transient=True,
            )
        except (UrlPolicyError, RedirectPolicyError, ResponseTooLargeError) as exc:
            attempt.finished_at = datetime.now(UTC)
            attempt.error_type = type(exc).__name__
            attempt.error_message = str(exc)[:2000]
            attempt.outcome = FetchOutcome.PERMANENT_ERROR
            session.commit()
            return _record_task_failure(
                task,
                lease_token,
                error_type=type(exc).__name__,
                error_message=str(exc),
                transient=False,
            )

        attempt.status_code = result.status_code
        attempt.final_url = result.final_url
        attempt.redirect_chain = result.redirect_chain
        attempt.content_type = result.content_type
        attempt.response_size_bytes = len(result.body)
        attempt.latency_ms = result.latency_ms
        attempt.response_headers = result.headers
        attempt.request_headers = result.request_headers
        attempt.finished_at = datetime.now(UTC)

        if result.status_code == 304 and resource is not None:
            attempt.outcome = FetchOutcome.SUCCEEDED
            resource.last_checked_at = datetime.now(UTC)
            resource.consecutive_failures = 0
            session.add(
                CrawlObservation(
                    run_id=run.id,
                    resource_id=resource.id,
                    fetch_attempt_id=attempt.id,
                    document_id=resource.current_document_id,
                    outcome=ObservationOutcome.NOT_MODIFIED,
                    change_kind=ChangeKind.UNCHANGED,
                    status_code=304,
                    etag=result.headers.get("etag") or resource.etag,
                    last_modified=result.headers.get("last-modified") or resource.last_modified,
                )
            )
            entry.status = FrontierStatus.INDEXED
            entry.last_crawled_at = datetime.now(UTC)
            complete_task(session, task.id, lease_token)
            emit_event(
                session,
                run.id,
                "document.not_modified",
                frontier_entry_id=entry.id,
                payload={"resource_id": str(resource.id)},
            )
            session.commit()
            return {"status": "not_modified"}

        if not 200 <= result.status_code < 300:
            transient = is_transient_status(result.status_code)
            attempt.outcome = (
                FetchOutcome.TRANSIENT_ERROR if transient else FetchOutcome.PERMANENT_ERROR
            )
            session.commit()
            return _record_task_failure(
                task,
                lease_token,
                error_type=f"http_{result.status_code}",
                error_message=f"HTTP request returned {result.status_code}",
                transient=transient,
            )

        if not is_html_content_type(result.content_type, run.allowed_content_types):
            attempt.outcome = FetchOutcome.UNSUPPORTED_CONTENT
            entry.status = FrontierStatus.UNSUPPORTED_CONTENT
            entry.blocked_reason = f"content_type:{result.content_type or 'missing'}"
            complete_task(session, task.id, lease_token)
            session.commit()
            return {"status": entry.status.value}

        attempt.outcome = FetchOutcome.SUCCEEDED
        attempt.body_sha256 = hashlib.sha256(result.body).hexdigest()
        attempt.raw_body_key = get_blob_store(settings).put_html(run.id, attempt.id, result.body)
        entry.status = FrontierStatus.FETCHED
        entry.last_crawled_at = datetime.now(UTC)
        observation = CrawlObservation(
            run_id=run.id,
            resource_id=resource.id if resource else None,
            fetch_attempt_id=attempt.id,
            outcome=ObservationOutcome.FETCHED,
            status_code=result.status_code,
            etag=result.headers.get("etag"),
            last_modified=result.headers.get("last-modified"),
        )
        session.add(observation)
        session.flush()
        create_pipeline_task(
            session,
            run_id=run.id,
            frontier_entry_id=entry.id,
            task_type=PipelineTaskType.EXTRACT,
            generation=task.generation,
            max_attempts=max(1, run.max_retries + 1),
            payload={"attempt_id": str(attempt.id), "observation_id": str(observation.id)},
        )
        complete_task(session, task.id, lease_token)
        emit_event(
            session,
            run.id,
            "fetch.succeeded",
            frontier_entry_id=entry.id,
            payload={"attempt_id": str(attempt.id), "latency_ms": result.latency_ms},
        )
        session.commit()
        return {"status": entry.status.value, "attempt_id": str(attempt.id)}


def _near_duplicate(
    session: Session, run: CrawlRun, current_simhash: int, bands: list[int]
) -> Document | None:
    candidates = list(
        session.scalars(
            select(Document)
            .where(
                Document.is_current.is_(True),
                Document.simhash.is_not(None),
                or_(*(Document.simhash_bands.contains([band]) for band in bands)),
            )
            .order_by(Document.extracted_at.desc())
            .limit(200)
        )
    )
    for candidate in candidates:
        decoded = decode_simhash(candidate.simhash)
        if decoded is not None and hamming_distance(decoded, current_simhash) <= 3:
            return candidate
    return None


def _discover_links(
    session: Session,
    *,
    run: CrawlRun,
    entry: FrontierEntry,
    links: list[str],
    allowed_domains: list[tuple[str, bool]],
    target_depth: int | None = None,
) -> int:
    accepted_count = 0
    for target_url in links[:1000]:
        target_host = host_for_url(target_url)
        discovered_depth = entry.depth + 1 if target_depth is None else target_depth
        within_depth = target_depth is not None or entry.depth < run.max_depth
        accepted = within_depth and is_host_allowed(target_host, allowed_domains)
        rejection_reason = None
        target_frontier_id = None
        if not accepted:
            rejection_reason = (
                "max_depth_reached" if not within_depth else "outside_domain_allowlist"
            )
        else:
            new_frontier_id = uuid.uuid4()
            statement = (
                pg_insert(FrontierEntry)
                .values(
                    id=new_frontier_id,
                    run_id=run.id,
                    url=target_url,
                    normalized_url=target_url,
                    host=target_host,
                    status=FrontierStatus.DISCOVERED,
                    priority=max(0, 100 - discovered_depth * 10),
                    depth=discovered_depth,
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
                create_pipeline_task(
                    session,
                    run_id=run.id,
                    frontier_entry_id=target_frontier_id,
                    task_type=PipelineTaskType.FETCH,
                    generation=run.generation,
                    max_attempts=max(1, run.max_retries + 1),
                )
        session.execute(
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
    return accepted_count


def _process_extract(task: PipelineTask, lease_token: uuid.UUID) -> dict[str, str]:
    task_id = task.id
    started = time.perf_counter()
    with SessionLocal() as session:
        loaded_task = _load_leased_task(session, task_id, lease_token)
        if loaded_task is None:
            return {"status": "stale_lease"}
        task = loaded_task
        entry = session.get(FrontierEntry, task.frontier_entry_id)
        run = session.get(CrawlRun, task.run_id)
        attempt_id = uuid.UUID(str(task.payload["attempt_id"]))
        attempt = session.get(FetchAttempt, attempt_id)
        if entry is None or run is None or attempt is None or not attempt.raw_body_key:
            return _record_task_failure(
                task,
                lease_token,
                error_type="missing_fetch_artifact",
                error_message="Extraction task cannot find its raw fetch artifact",
                transient=False,
            )
        entry.status = FrontierStatus.EXTRACTING
        heartbeat_task(session, task.id, lease_token, lease_seconds=settings.task_lease_seconds)
        session.commit()

        try:
            html = (
                get_blob_store(settings)
                .get_html(attempt.raw_body_key)
                .decode("utf-8", errors="replace")
            )
            extracted = extract_page(html, attempt.final_url or entry.normalized_url)
        except Exception as exc:
            session.add(
                ExtractionAttempt(
                    run_id=run.id,
                    fetch_attempt_id=attempt.id,
                    parser_name="unknown",
                    parser_version="unknown",
                    succeeded=False,
                    warnings=[],
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:2000],
                )
            )
            session.commit()
            return _record_task_failure(
                task,
                lease_token,
                error_type="extraction_error",
                error_message=str(exc),
                transient=False,
            )

        resource = _find_resource(session, run, entry.normalized_url)
        if resource is None:
            resource = WebResource(
                definition_id=run.definition_id,
                normalized_url=entry.normalized_url,
                canonical_url=extracted.canonical_url,
                host=entry.host,
            )
            session.add(resource)
            session.flush()
        previous = (
            session.get(Document, resource.current_document_id)
            if resource.current_document_id
            else None
        )
        fingerprint = simhash64(extracted.main_text)
        bands = simhash_bands(fingerprint)
        metadata_changed = bool(
            previous
            and (
                previous.title != extracted.title
                or previous.description != extracted.description
                or previous.canonical_url != extracted.canonical_url
            )
        )
        change_kind = classify_change(
            previous_hash=previous.content_hash if previous else None,
            current_hash=extracted.content_hash,
            previous_simhash=previous.simhash if previous else None,
            current_simhash=fingerprint,
            metadata_changed=metadata_changed,
        )
        observation_id = task.payload.get("observation_id")
        observation = (
            session.get(CrawlObservation, uuid.UUID(str(observation_id)))
            if observation_id
            else None
        )

        extraction_attempt = ExtractionAttempt(
            run_id=run.id,
            fetch_attempt_id=attempt.id,
            parser_name=extracted.parser_name,
            parser_version=extracted.parser_version,
            succeeded=True,
            confidence=extracted.confidence,
            text_length=len(extracted.main_text),
            warnings=extracted.warnings,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        session.add(extraction_attempt)

        now = datetime.now(UTC)
        resource.last_checked_at = now
        resource.etag = attempt.response_headers.get("etag") or resource.etag
        resource.last_modified = (
            attempt.response_headers.get("last-modified") or resource.last_modified
        )
        resource.consecutive_failures = 0
        resource.canonical_url = extracted.canonical_url

        if change_kind == ChangeKind.UNCHANGED and previous is not None:
            extraction_attempt.document_id = previous.id
            extraction_attempt.promoted = False
            if observation is not None:
                observation.resource_id = resource.id
                observation.document_id = previous.id
                observation.change_kind = change_kind
                observation.content_hash = extracted.content_hash
            entry.status = FrontierStatus.DUPLICATE_CONTENT
            complete_task(session, task.id, lease_token)
            emit_event(
                session,
                run.id,
                "document.unchanged",
                frontier_entry_id=entry.id,
                payload={"document_id": str(previous.id), "resource_id": str(resource.id)},
            )
            session.commit()
            return {"status": "unchanged", "document_id": str(previous.id)}

        exact_duplicate = session.scalar(
            select(Document)
            .where(
                Document.content_hash == extracted.content_hash,
                Document.is_current.is_(True),
                Document.id != (previous.id if previous else uuid.uuid4()),
            )
            .order_by(Document.extracted_at)
            .limit(1)
        )
        near_duplicate = (
            None if exact_duplicate else _near_duplicate(session, run, fingerprint, bands)
        )
        cluster: DuplicateCluster | None = None
        representative = exact_duplicate or near_duplicate
        if representative is not None:
            cluster = (
                session.get(DuplicateCluster, representative.duplicate_cluster_id)
                if representative.duplicate_cluster_id
                else None
            )
            if cluster is None:
                cluster = DuplicateCluster(
                    definition_id=run.definition_id,
                    representative_document_id=representative.id,
                    member_count=1,
                )
                session.add(cluster)
                session.flush()
                representative.duplicate_cluster_id = cluster.id
            cluster.member_count += 1

        if previous is not None:
            previous.is_current = False
        document = Document(
            run_id=run.id,
            frontier_entry_id=entry.id,
            fetch_attempt_id=attempt.id,
            resource_id=resource.id,
            previous_version_id=previous.id if previous else None,
            version_number=(previous.version_number + 1) if previous else 1,
            is_current=True,
            change_kind=change_kind,
            url=attempt.final_url or entry.normalized_url,
            canonical_url=extracted.canonical_url,
            host=host_for_url(attempt.final_url or entry.normalized_url),
            title=extracted.title,
            description=extracted.description,
            language=extracted.language,
            headings=extracted.headings,
            main_text=extracted.main_text,
            text_length=len(extracted.main_text),
            content_hash=extracted.content_hash,
            simhash=encode_simhash(fingerprint),
            simhash_bands=bands,
            duplicate_cluster_id=cluster.id if cluster else None,
            duplicate_of_document_id=exact_duplicate.id if exact_duplicate else None,
            extraction_confidence=extracted.confidence,
            parser_name=extracted.parser_name,
            parser_version=extracted.parser_version,
            extraction_warnings=extracted.warnings,
        )
        session.add(document)
        session.flush()
        extraction_attempt.document_id = document.id
        extraction_attempt.promoted = True
        resource.current_document_id = document.id
        resource.last_changed_at = now
        if observation is not None:
            observation.resource_id = resource.id
            observation.document_id = document.id
            observation.change_kind = change_kind
            observation.content_hash = extracted.content_hash

        allowed_rows = list(
            session.scalars(select(AllowedDomain).where(AllowedDomain.run_id == run.id))
        )
        accepted = _discover_links(
            session,
            run=run,
            entry=entry,
            links=extracted.links,
            allowed_domains=[(item.domain, item.include_subdomains) for item in allowed_rows],
        )

        if exact_duplicate is not None:
            entry.status = FrontierStatus.DUPLICATE_CONTENT
            complete_task(session, task.id, lease_token)
        else:
            entry.status = FrontierStatus.INDEXING
            operation = IndexOperation(
                run_id=run.id,
                document_id=document.id,
                schema_version=DocumentIndex.schema_version,
                status=IndexOperationStatus.PENDING,
            )
            session.add(operation)
            session.flush()
            create_pipeline_task(
                session,
                run_id=run.id,
                frontier_entry_id=entry.id,
                task_type=PipelineTaskType.INDEX,
                generation=task.generation,
                max_attempts=max(3, run.max_retries + 1),
                payload={"operation_id": str(operation.id), "document_id": str(document.id)},
            )
            complete_task(session, task.id, lease_token)
        emit_event(
            session,
            run.id,
            "extraction.succeeded",
            frontier_entry_id=entry.id,
            payload={
                "document_id": str(document.id),
                "version": document.version_number,
                "change_kind": change_kind.value,
                "links_accepted": accepted,
            },
        )
        session.commit()
        return {"status": entry.status.value, "document_id": str(document.id)}


def _process_index(task: PipelineTask, lease_token: uuid.UUID) -> dict[str, str]:
    task_id = task.id
    with SessionLocal() as session:
        loaded_task = _load_leased_task(session, task_id, lease_token)
        if loaded_task is None:
            return {"status": "stale_lease"}
        task = loaded_task
        operation = session.get(IndexOperation, uuid.UUID(str(task.payload["operation_id"])))
        document = session.get(Document, uuid.UUID(str(task.payload["document_id"])))
        entry = session.get(FrontierEntry, task.frontier_entry_id)
        if operation is None or document is None or entry is None:
            return _record_task_failure(
                task,
                lease_token,
                error_type="missing_index_artifact",
                error_message="Index task cannot find its operation or document",
                transient=False,
            )
        operation.status = IndexOperationStatus.PROCESSING
        operation.attempts += 1
        heartbeat_task(session, task.id, lease_token, lease_seconds=settings.task_lease_seconds)
        session.commit()
        try:
            index_name = DocumentIndex(settings).index_document(document)
        except OpenSearchException as exc:
            session.refresh(task)
            next_status = fail_task(
                session,
                task,
                lease_token,
                error_type="index_error",
                error_message=str(exc),
                transient=True,
            )
            operation.status = (
                IndexOperationStatus.RETRY_SCHEDULED
                if next_status == PipelineTaskStatus.RETRY_SCHEDULED
                else IndexOperationStatus.DEAD_LETTERED
            )
            operation.last_error = str(exc)[:4000]
            entry.status = (
                FrontierStatus.INDEXING
                if next_status == PipelineTaskStatus.RETRY_SCHEDULED
                else FrontierStatus.FAILED
            )
            session.commit()
            return {"status": next_status.value, "error_type": "index_error"}

        operation.status = IndexOperationStatus.SUCCEEDED
        operation.completed_at = datetime.now(UTC)
        operation.last_error = None
        document.index_name = index_name
        document.indexed_at = datetime.now(UTC)
        entry.status = FrontierStatus.INDEXED
        complete_task(session, task.id, lease_token)
        emit_event(
            session,
            task.run_id,
            "index.succeeded",
            frontier_entry_id=entry.id,
            payload={"document_id": str(document.id), "index": index_name},
        )
        session.commit()
        return {"status": entry.status.value, "document_id": str(document.id)}


def process_pipeline_task(task_id: str, lease_token: str) -> dict[str, str]:
    parsed_task_id, parsed_token = _task_context(task_id, lease_token)
    worker_id = _worker_id()
    with SessionLocal() as session:
        task = _load_leased_task(session, parsed_task_id, parsed_token)
        if task is None:
            return {"status": "stale_lease"}
        upsert_worker_heartbeat(
            session,
            worker_id=worker_id,
            queues=["atlas-fetch", "atlas-extract", "atlas-index"],
            version="0.2.0",
            current_task_id=task.id,
        )
        session.commit()
        task_type = task.task_type
        detached_task = task
    log = logger.bind(task_id=task_id, stage=task_type.value, worker_id=worker_id)
    try:
        if task_type == PipelineTaskType.FETCH:
            result = _process_fetch(detached_task, parsed_token)
        elif task_type == PipelineTaskType.EXTRACT:
            result = _process_extract(detached_task, parsed_token)
        else:
            result = _process_index(detached_task, parsed_token)
        log.info("pipeline_task_finished", **result)
        return result
    finally:
        with SessionLocal() as session:
            upsert_worker_heartbeat(
                session,
                worker_id=worker_id,
                queues=["atlas-fetch", "atlas-extract", "atlas-index"],
                version="0.2.0",
                current_task_id=None,
            )
            session.commit()


def process_frontier_entry(entry_id: str) -> dict[str, str]:
    """Compatibility shim for RQ jobs created by the pre-hardening scheduler."""
    frontier_id = uuid.UUID(entry_id)
    with SessionLocal() as session:
        entry = session.get(FrontierEntry, frontier_id)
        if entry is None:
            return {"status": "missing"}
        run = session.get(CrawlRun, entry.run_id)
        if run is None:
            return {"status": "missing_run"}
        task = session.scalar(
            select(PipelineTask).where(
                PipelineTask.frontier_entry_id == entry.id,
                PipelineTask.task_type == PipelineTaskType.FETCH,
            )
        )
        if task is None:
            create_pipeline_task(
                session,
                run_id=run.id,
                frontier_entry_id=entry.id,
                task_type=PipelineTaskType.FETCH,
                generation=run.generation,
                max_attempts=max(1, run.max_retries + 1),
            )
            session.commit()
        return {"status": "migrated_to_pipeline"}


def run_index_build(build_id: str) -> dict[str, str | int]:
    parsed_id = uuid.UUID(build_id)
    with SessionLocal() as session:
        build = session.get(IndexBuild, parsed_id)
        if build is None:
            return {"status": "missing"}
        build.status = IndexBuildStatus.BUILDING
        build.started_at = datetime.now(UTC)
        documents = list(
            session.scalars(
                select(Document).where(
                    Document.is_current.is_(True),
                    Document.duplicate_of_document_id.is_(None),
                )
            )
        )
        build.expected_documents = len(documents)
        session.commit()
        index = DocumentIndex(settings)
        try:
            physical_index = index.create_build_index(build.id)
            build.physical_index = physical_index
            for document in documents:
                index.index_document(document, index_name=physical_index)
                build.indexed_documents += 1
                if build.indexed_documents % 100 == 0:
                    session.commit()
            build.status = IndexBuildStatus.VERIFYING
            session.commit()
            actual = index.client.count(index=physical_index)["count"]
            if actual != build.expected_documents:
                raise RuntimeError(
                    "Index verification mismatch: "
                    f"expected {build.expected_documents}, got {actual}"
                )
            index.activate_index(physical_index)
            build.status = IndexBuildStatus.SUCCEEDED
            build.finished_at = datetime.now(UTC)
            session.commit()
            return {"status": build.status.value, "indexed": build.indexed_documents}
        except Exception as exc:
            build.status = IndexBuildStatus.FAILED
            build.error_message = str(exc)[:4000]
            build.finished_at = datetime.now(UTC)
            session.commit()
            logger.exception("index_build_failed", build_id=build_id)
            return {"status": build.status.value, "indexed": build.indexed_documents}
