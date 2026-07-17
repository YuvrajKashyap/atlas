# Atlas deterministic corpus

`benchmark/corpus` serves 10,000 deterministic HTML documents, ten sitemap shards, exact and near duplicates, malformed markup, conditional responses, redirects, transient failures, a slow response, an oversized response, unsupported content, and a robots-excluded route.

Start it with `docker compose --profile benchmark up -d corpus`, then inspect `http://localhost:8090/manifest.json`. The corpus is an input fixture, not benchmark evidence. Only the recovery harness may write a public benchmark artifact after every database and search invariant passes.
