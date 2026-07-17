# ADR 0001: PostgreSQL is authoritative for pipeline work

Status: accepted

## Context

RQ offers useful delivery and worker tooling, but a Redis queue cannot prove what work should exist after eviction, loss, or duplicate delivery.

## Decision

Persist every fetch, extract, and index task in PostgreSQL before publishing a notification. Claim tasks transactionally with an opaque lease token. Treat Redis as a low-latency wake-up channel and continuously recover eligible database rows.

## Consequences

Atlas can reconstruct the queue and audit transitions. The scheduler performs more database work and task-state indexes become critical. Redis throughput no longer defines correctness.
