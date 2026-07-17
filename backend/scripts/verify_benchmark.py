import json
import os
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
from sqlalchemy import func, select

from atlas.config import get_settings
from atlas.db import SessionLocal
from atlas.enums import TERMINAL_FRONTIER_STATUSES, PipelineTaskStatus
from atlas.indexer import DocumentIndex
from atlas.models import (
    CrawlRun,
    Document,
    FetchAttempt,
    FrontierEntry,
    IndexOperation,
    PipelineTask,
)
from atlas.services.runs import get_run_counters


def _fail(failures: list[str], condition: bool, message: str) -> None:
    if condition:
        failures.append(message)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: verify_benchmark.py RUN_ID")
    run_id = uuid.UUID(sys.argv[1])
    corpus_url = os.getenv("ATLAS_CORPUS_URL", "http://localhost:8090").rstrip("/")
    manifest = cast(
        dict[str, Any],
        httpx.get(f"{corpus_url}/manifest.json", timeout=10).raise_for_status().json(),
    )
    expected_targets = int(manifest["crawlTargetCount"])
    failures: list[str] = []

    with SessionLocal() as session:
        run = session.get(CrawlRun, run_id)
        if run is None:
            raise SystemExit(f"Benchmark run does not exist: {run_id}")
        _fail(failures, run.status.value != "completed", f"run ended as {run.status.value}")

        frontier = list(
            session.scalars(
                select(FrontierEntry)
                .where(FrontierEntry.run_id == run_id)
                .order_by(FrontierEntry.created_at)
            )
        )
        terminal = [entry for entry in frontier if entry.status in TERMINAL_FRONTIER_STATUSES]
        _fail(
            failures,
            len(terminal) != len(frontier),
            f"{len(frontier) - len(terminal)} frontier records are non-terminal",
        )
        _fail(
            failures,
            len(frontier) < expected_targets,
            f"frontier has {len(frontier)} records, expected at least {expected_targets}",
        )

        active_tasks = (
            session.scalar(
                select(func.count())
                .select_from(PipelineTask)
                .where(
                    PipelineTask.run_id == run_id,
                    PipelineTask.status.in_(
                        [
                            PipelineTaskStatus.READY,
                            PipelineTaskStatus.LEASED,
                            PipelineTaskStatus.RETRY_SCHEDULED,
                        ]
                    ),
                )
            )
            or 0
        )
        _fail(failures, active_tasks > 0, f"{active_tasks} pipeline tasks remain active")
        stale_leases = [entry for entry in frontier if entry.lease_expires_at is not None]
        _fail(failures, bool(stale_leases), f"{len(stale_leases)} frontier leases remain set")

        duplicate_current_versions = list(
            session.execute(
                select(Document.resource_id, func.count())
                .where(
                    Document.run_id == run_id,
                    Document.is_current.is_(True),
                    Document.resource_id.is_not(None),
                )
                .group_by(Document.resource_id)
                .having(func.count() > 1)
            )
        )
        _fail(
            failures,
            bool(duplicate_current_versions),
            f"{len(duplicate_current_versions)} resources have multiple current versions",
        )

        incomplete_index_operations = (
            session.scalar(
                select(func.count())
                .select_from(IndexOperation)
                .where(IndexOperation.run_id == run_id, IndexOperation.status != "succeeded")
            )
            or 0
        )
        _fail(
            failures,
            incomplete_index_operations > 0,
            f"{incomplete_index_operations} index operations are incomplete",
        )

        expected_index_documents = (
            session.scalar(
                select(func.count())
                .select_from(Document)
                .where(
                    Document.run_id == run_id,
                    Document.is_current.is_(True),
                    Document.duplicate_of_document_id.is_(None),
                )
            )
            or 0
        )
        index = DocumentIndex(get_settings())
        indexed_documents = int(
            cast(
                dict[str, Any],
                index.client.count(
                    index=index.read_alias,
                    body={
                        "query": {
                            "bool": {
                                "filter": [
                                    {"term": {"run_id": str(run_id)}},
                                    {"term": {"is_current": True}},
                                ]
                            }
                        }
                    },
                ),
            )["count"]
        )
        _fail(
            failures,
            indexed_documents != expected_index_documents,
            f"index has {indexed_documents} documents, expected {expected_index_documents}",
        )

        attempts = list(
            session.scalars(
                select(FetchAttempt)
                .where(FetchAttempt.run_id == run_id)
                .order_by(FetchAttempt.started_at)
            )
        )
        by_host: dict[str, list[datetime]] = defaultdict(list)
        for attempt in attempts:
            if attempt.final_url:
                host = urlsplit(attempt.final_url).hostname
                if host:
                    by_host[host].append(attempt.started_at)
        politeness_violations = 0
        minimum_gap = max(0, run.per_domain_delay_ms - 25) / 1000
        for timestamps in by_host.values():
            for previous, current in pairwise(timestamps):
                if (current - previous).total_seconds() < minimum_gap:
                    politeness_violations += 1
        _fail(
            failures,
            politeness_violations > 0,
            f"{politeness_violations} per-domain delay violations detected",
        )

        counters = get_run_counters(session, run_id)
        _fail(
            failures,
            counters.discovered != len(frontier),
            f"stored counters report {counters.discovered} discovered, recomputed {len(frontier)}",
        )
        terminal_counts: dict[str, int] = defaultdict(int)
        for entry in terminal:
            terminal_counts[entry.status.value] += 1

    if failures:
        raise SystemExit("Benchmark verification failed:\n- " + "\n- ".join(failures))

    report = {
        "schemaVersion": 1,
        "verifiedAt": datetime.now(UTC).isoformat(),
        "gitCommit": os.getenv("GITHUB_SHA", "local"),
        "runId": str(run_id),
        "elapsedSeconds": (
            round((run.finished_at - run.started_at).total_seconds(), 3)
            if run.finished_at is not None and run.started_at is not None
            else None
        ),
        "corpusVersion": manifest["corpusVersion"],
        "corpusSize": manifest["pageCount"],
        "crawlTargetCount": expected_targets,
        "frontierCount": len(frontier),
        "indexedDocuments": indexed_documents,
        "terminalStates": dict(sorted(terminal_counts.items())),
        "faultScenarios": sorted(
            item.strip()
            for item in os.getenv("ATLAS_FAULT_SCENARIOS", "").split(",")
            if item.strip()
        ),
        "invariants": {
            "allEligibleUrlsTerminal": True,
            "noStaleLeases": True,
            "oneCurrentVersionPerResource": True,
            "indexMatchesPostgres": True,
            "politenessRespected": True,
            "countersConsistent": True,
        },
    }
    output = Path(os.getenv("ATLAS_BENCHMARK_OUTPUT", "../web/public/benchmarks/latest.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
