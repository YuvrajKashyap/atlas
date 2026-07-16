import { Filter, Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";

import { api } from "../api";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingState, StatusChip } from "../components/primitives";
import { formatDate, formatNumber } from "../lib/format";
import { useRunScope } from "../state/run-scope";
import type { FrontierStatus } from "../types";

const statusOptions: FrontierStatus[] = [
  "discovered",
  "queued",
  "fetching",
  "extracting",
  "indexing",
  "indexed",
  "retry_scheduled",
  "robots_blocked",
  "duplicate_content",
  "unsupported_content",
  "budget_exhausted",
  "failed",
];

export function Frontier() {
  const { selectedRunId, selectedRun } = useRunScope();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const deferredQuery = useDeferredValue(query);
  const frontierQuery = useQuery({
    queryKey: ["frontier", selectedRunId, deferredQuery, status],
    queryFn: () => api.frontier(selectedRunId!, deferredQuery, status),
    enabled: Boolean(selectedRunId),
    refetchInterval: selectedRun?.status === "running" ? 3_000 : 15_000,
  });

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="URL SCHEDULER"
        title="Frontier"
        description="Inspect every durable URL record and its current position in the crawl lifecycle."
      />
      {!selectedRunId ? (
        <EmptyState
          title="No active survey"
          detail="Create or select a crawl run before inspecting its frontier."
          action={{ label: "Open crawl registry", to: "/crawls" }}
        />
      ) : (
        <>
          <div className="filter-bar">
            <label className="search-field">
              <Search size={16} />
              <span className="sr-only">Filter URLs</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Filter by URL or normalized URL"
              />
            </label>
            <label className="filter-select">
              <Filter size={15} />
              <span className="sr-only">Filter by state</span>
              <select value={status} onChange={(event) => setStatus(event.target.value)}>
                <option value="">All lifecycle states</option>
                {statusOptions.map((option) => (
                  <option key={option} value={option}>{option.replaceAll("_", " ")}</option>
                ))}
              </select>
            </label>
            <span className="record-count">
              {frontierQuery.data ? `${formatNumber(frontierQuery.data.total)} records` : "— records"}
            </span>
          </div>
          {frontierQuery.isLoading ? <LoadingState label="Scanning frontier" /> : null}
          {frontierQuery.error ? <ErrorState error={frontierQuery.error} /> : null}
          {frontierQuery.data?.items.length === 0 ? (
            <EmptyState title="No frontier records match" detail="Adjust the filters or start the selected crawl run." />
          ) : null}
          {frontierQuery.data && frontierQuery.data.items.length > 0 ? (
            <div className="data-table frontier-table">
              <div className="table-header frontier-row">
                <span>URL</span>
                <span>State</span>
                <span>Depth</span>
                <span>Attempts</span>
                <span>Last activity</span>
              </div>
              {frontierQuery.data.items.map((entry) => (
                <article className="frontier-row data-row" key={entry.id}>
                  <div className="url-cell">
                    <strong>{entry.host}</strong>
                    <span title={entry.url}>{entry.url}</span>
                  </div>
                  <StatusChip status={entry.status} />
                  <span className="tabular">{entry.depth}</span>
                  <span className="tabular">
                    {entry.fetch_attempt_count}
                    {entry.retry_count ? <small> +{entry.retry_count} retry</small> : null}
                  </span>
                  <time dateTime={entry.last_crawled_at ?? entry.first_seen_at}>
                    {formatDate(entry.last_crawled_at ?? entry.first_seen_at)}
                  </time>
                </article>
              ))}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
