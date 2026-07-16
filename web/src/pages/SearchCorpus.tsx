import { ExternalLink, Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "../api";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/primitives";
import { formatNumber, formatPercent } from "../lib/format";
import { useRunScope } from "../state/run-scope";

export function SearchCorpus() {
  const { selectedRunId } = useRunScope();
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const searchQuery = useQuery({
    queryKey: ["search", selectedRunId, query],
    queryFn: () => api.search(query, selectedRunId ?? undefined),
    enabled: query.length > 0,
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = input.trim();
    if (normalized) setQuery(normalized);
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="OPENSEARCH / BM25"
        title="Corpus search"
        description="Query extracted text with title, heading, and description relevance boosts."
      />
      <form className="corpus-search" onSubmit={submit}>
        <Search size={21} />
        <label className="sr-only" htmlFor="corpus-query">Search extracted documents</label>
        <input
          id="corpus-query"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Search the indexed corpus"
          autoComplete="off"
        />
        <button className="primary-button" type="submit">Search</button>
      </form>

      {!query ? (
        <EmptyState title="Awaiting a query" detail="Results are scoped to the active survey and ranked by OpenSearch." />
      ) : null}
      {searchQuery.isLoading ? <LoadingState label="Searching corpus" /> : null}
      {searchQuery.error ? <ErrorState error={searchQuery.error} /> : null}
      {searchQuery.data ? (
        <section className="search-results">
          <header>
            <span>{formatNumber(searchQuery.data.total)} matches</span>
            <span>{searchQuery.data.took_ms} ms</span>
          </header>
          {searchQuery.data.items.length === 0 ? (
            <EmptyState title="No matches" detail={`No indexed document matched “${query}”.`} />
          ) : (
            <ol>
              {searchQuery.data.items.map((result) => (
                <li key={result.document_id}>
                  <div className="result-rank">{String(result.score?.toFixed(2) ?? "—").padStart(4, "0")}</div>
                  <article>
                    <div className="result-meta">
                      <span>{result.host}</span>
                      <span>{formatPercent(result.extraction_confidence)}</span>
                    </div>
                    <h2>{result.title ?? "Untitled document"}</h2>
                    <p>{result.description ?? result.main_text.slice(0, 240)}</p>
                    <a href={result.url} target="_blank" rel="noreferrer">
                      {result.url} <ExternalLink size={12} />
                    </a>
                  </article>
                </li>
              ))}
            </ol>
          )}
        </section>
      ) : null}
    </div>
  );
}
