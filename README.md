# Atlas

Atlas is a production-style, domain-restricted crawl, extraction, indexing, and observability platform. It safely turns an allowlisted portion of the public web into an inspectable, searchable corpus.

Atlas is not a scraper script. The system models crawl runs as first-class entities and records the complete lifecycle of every URL: discovery, policy decisions, scheduling, fetching, extraction, deduplication, and indexing.

## System shape

```text
React/Vite operator console
            |
        FastAPI API
            |
   PostgreSQL system of record
       |              |
 frontier scheduler   metrics/events
       |
    Redis/RQ
       |
 crawl worker -> HTML extraction -> link discovery -> OpenSearch
```

PostgreSQL is authoritative. Redis transports ephemeral jobs; it is never the only place crawl state exists.

## Current MVP surfaces

- Create and start isolated crawl runs with seed URLs, domain allowlists, depth limits, page budgets, and politeness delays.
- Persistent URL frontier with explicit states and retry scheduling.
- Public-network validation, redirect revalidation, response limits, robots.txt enforcement, and per-domain scheduling.
- Fetch attempt history, structured crawl events, main-content extraction, link discovery, and content-hash deduplication.
- Versioned OpenSearch document index with BM25 search, highlighting, filters, and stable aliases.
- Operator console with Command Center, Crawls, Frontier, Documents, and Search.
- Real metrics derived from persisted crawl records—no fixtures or decorative chart data.

## Safety boundary

Atlas only crawls public `http` and `https` pages on explicitly allowlisted domains. It rejects localhost, private networks, credentials in URLs, unsupported schemes, cross-boundary redirects, oversized responses, and non-HTML content. It does not bypass authentication, paywalls, CAPTCHAs, or anti-bot systems.

## Local prerequisites

- Docker Desktop with at least 6 GB available to containers
- Node.js 24 LTS and pnpm 10 for host-side frontend development
- Python 3.13 and uv for host-side backend development

Copy `.env.example` to `.env`, then start the complete stack:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

The services are exposed at:

- Operator console: <http://localhost:4173>
- FastAPI: <http://localhost:8000>
- API documentation: <http://localhost:8000/docs>
- OpenSearch API: <https://localhost:9200> (self-signed locally)

Host-side development commands are documented in [docs/development.md](docs/development.md).

## Architecture decisions

Atlas intentionally starts as a modular monolith with separate runtime processes rather than premature microservices. See [docs/architecture.md](docs/architecture.md), [docs/tradeoffs.md](docs/tradeoffs.md), and [docs/safety.md](docs/safety.md).
