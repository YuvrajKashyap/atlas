# ADR 0003: Search indexing uses a durable outbox

Status: accepted

## Context

Combining fetch, extraction, and search writes in one retry unit causes an OpenSearch outage to repeat network traffic and parser work.

## Decision

Commit the document version and `IndexOperation` together. Index workers retry only the idempotent search write. Use stable document IDs and versioned physical indexes behind aliases.

## Consequences

Search may be temporarily behind PostgreSQL, but the lag is observable and repairable. Rebuilds can be verified and promoted without pausing crawls.
