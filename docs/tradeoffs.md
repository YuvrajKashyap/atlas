# Tradeoffs

## PostgreSQL frontier instead of a Redis-only queue

The frontier needs durable state, rich filtering, run isolation, retries, provenance, and inspection. PostgreSQL provides those properties and transactional leases. Redis remains useful for low-latency job delivery but is not authoritative.

## RQ instead of Celery

Atlas implements domain-specific scheduling in PostgreSQL. RQ supplies the worker process and queue without introducing workflow features the MVP does not need. Celery becomes reasonable if the project later needs complex task graphs, multiple brokers, or a much larger operational surface.

## One staged worker job instead of separate fetch/parse/index queues

The MVP uses one job with explicit persisted stages. This keeps the end-to-end failure model understandable while still separating fetcher, extractor, discovery, and indexer modules. Independent stage queues are an upgrade when measurements show a need to scale them differently.

## Vite instead of Next.js

Atlas is an interactive operator console over a separate API. A static Vite application keeps the frontend/backend boundary explicit and avoids adding a second server runtime, server-component rules, and frontend caching semantics.

## OpenSearch instead of PostgreSQL full-text search

PostgreSQL full-text search would reduce local resource use, but OpenSearch gives Atlas a real index schema, BM25 scoring, highlighting, aliases, and rebuild workflow. The search index remains rebuildable from PostgreSQL.

