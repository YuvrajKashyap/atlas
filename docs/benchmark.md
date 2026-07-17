# Deterministic benchmark methodology

The release benchmark serves a generated 10,000-page HTTP corpus with a known link graph and oracle. It contains canonical pages, exact duplicates, near duplicates, conditional responses, sitemap entries, redirects, malformed markup, robots exclusions, slow responses, unsupported media, and oversized bodies.

During a run the harness injects:

- duplicate notification delivery
- worker termination and expired leases
- a complete Redis data loss and scheduler republish
- temporary OpenSearch unavailability
- PostgreSQL connection interruption
- redirect policy failures and DNS-rebinding candidates
- robots fetch failures and malformed documents

The release gate queries PostgreSQL and OpenSearch after recovery. It requires:

1. Every eligible URL is in a documented terminal state.
2. No lease is stale.
3. No resource has multiple current document versions.
4. Every current indexable document has one search document at the active schema version.
5. Domain request intervals respect configured concurrency and delay.
6. Run counters equal independently recomputed counts.
7. Replayed notifications do not create duplicate stage generations or fetch attempts.

The harness writes `web/public/benchmarks/latest.json` only after all invariants pass. The file includes the Git commit, verification timestamp, corpus size, elapsed time, counts, and named fault scenarios. Hand-authored benchmark numbers are prohibited.

Run the manual `deterministic benchmark` GitHub workflow to execute the full suite. Locally, `docker compose --profile benchmark up -d corpus` starts only the fixture; that command does not produce or publish evidence. `scripts/benchmark.mjs` creates or waits for a run, and `backend/scripts/verify_benchmark.py` is the only writer for the public report.
