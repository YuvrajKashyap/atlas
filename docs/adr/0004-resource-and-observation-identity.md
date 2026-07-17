# ADR 0004: Separate resources, observations, and document versions

Status: accepted

## Context

A URL is not a document, and revisiting an unchanged URL should not create a new current document. Canonical declarations also cannot safely erase the identity of the fetched URL.

## Decision

Use `WebResource` for stable normalized URL identity, `CrawlObservation` for each run’s outcome, and `Document` for extracted content versions. Preserve predecessor links, canonical aliases, exact hashes, SimHash bands, and a single current version.

## Consequences

Change history and conditional requests become first-class. Queries are more explicit and migration constraints must guard current-version uniqueness.
