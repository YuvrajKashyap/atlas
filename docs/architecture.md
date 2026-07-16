# Architecture

## Runtime topology

Atlas uses one Python package with separate entrypoints:

1. **API** — validates commands and exposes run, frontier, document, metrics, and search resources.
2. **Scheduler** — leases eligible frontier entries from PostgreSQL and enqueues idempotent RQ jobs.
3. **Worker** — performs robots decisions, bounded HTTP fetching, extraction, discovery, deduplication, and indexing.
4. **Web** — a statically built React application that consumes the FastAPI contract.

The components are separate processes but not separate source repositories. This preserves independently scalable execution without duplicating models or introducing unnecessary internal network APIs.

## Data authority

- PostgreSQL owns crawl-run configuration, frontier states, fetch attempts, extracted documents, discovered-link provenance, and crawl events.
- Redis is an ephemeral delivery mechanism. A lost job is recoverable from an expired PostgreSQL lease.
- OpenSearch is a rebuildable search projection. PostgreSQL remains authoritative if the index is unavailable.
- Raw response bodies live behind a blob-store interface. The local implementation writes gzip-compressed bodies to a mounted volume.

## Delivery semantics

RQ provides at-least-once delivery. A worker can receive the same frontier entry more than once, so every job checks the persisted frontier state and uses stable identifiers before performing work. Leases prevent healthy workers from processing the same entry concurrently; expired leases are returned to an eligible state by the scheduler.

## Crawl-run isolation

Every seed, allowlist entry, frontier record, fetch attempt, document, link, event, and metric belongs to a crawl run. URL uniqueness is enforced within a run, allowing two runs to crawl the same normalized URL without mixing histories.

