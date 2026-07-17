import { ArrowUpRight, Gauge, Network, ShieldCheck, TimerReset } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingState, Panel, StatusChip } from "../components/primitives";
import { formatDate, formatDuration, formatNumber, formatPercent, shortId } from "../lib/format";
import { useRunScope } from "../state/run-scope";

export function CommandCenter() {
  const { selectedRun, selectedRunId, isLoading, error } = useRunScope();
  const metricsQuery = useQuery({
    queryKey: ["metrics", selectedRunId],
    queryFn: () => api.metrics(selectedRunId!),
    enabled: Boolean(selectedRunId),
    refetchInterval: selectedRun?.status === "running" ? 3_000 : 10_000,
  });
  const systemQuery = useQuery({
    queryKey: ["system"],
    queryFn: api.system,
    refetchInterval: 10_000,
    retry: false,
  });

  if (isLoading) return <LoadingState label="Locating crawl runs" />;
  if (error) return <ErrorState error={error} />;

  if (!selectedRun) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="OPERATIONS / 00"
          title="Command center"
          description="Live crawl telemetry, resource health, and recent system events."
        />
        <EmptyState
          title="No survey has been commissioned"
          detail="Create a crawl run to establish a durable frontier and begin collecting telemetry."
          action={{ label: "Create the first crawl", to: "/console/crawls" }}
        />
      </div>
    );
  }

  const metrics = metricsQuery.data;
  const systemStatus = systemQuery.isError ? "offline" : (systemQuery.data?.status ?? "degraded");
  const statusEntries = metrics ? Object.entries(metrics.frontier_statuses) : [];
  const frontierTotal = statusEntries.reduce((sum, [, value]) => sum + value, 0);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={`OPERATIONS / ${shortId(selectedRun.id).toUpperCase()}`}
        title="Command center"
        description={`Observing ${selectedRun.name}. Every figure below is computed from persisted crawl records.`}
        actions={
          <div className="header-signal">
            <span>SYSTEM</span>
            <StatusChip status={systemStatus} />
          </div>
        }
      />

      {metricsQuery.isLoading ? <LoadingState /> : null}
      {metricsQuery.error ? <ErrorState error={metricsQuery.error} /> : null}
      {metrics ? (
        <>
          <section className="metric-grid" aria-label="Run metrics">
            <MetricCard
              index="01"
              label="URLs observed"
              value={formatNumber(metrics.counters.discovered)}
              detail={`${formatNumber(metrics.counters.queued + metrics.counters.fetching)} in flight`}
              icon={<Network size={18} />}
            />
            <MetricCard
              index="02"
              label="Documents indexed"
              value={formatNumber(metrics.counters.indexed)}
              detail={`${formatNumber(metrics.counters.documents)} extracted`}
              icon={<Gauge size={18} />}
            />
            <MetricCard
              index="03"
              label="Fetch velocity"
              value={`${metrics.throughput_per_minute.toFixed(1)}/m`}
              detail={`p95 ${formatDuration(metrics.fetch_latency_p95_ms)}`}
              icon={<TimerReset size={18} />}
            />
            <MetricCard
              index="04"
              label="Policy decisions"
              value={formatNumber(metrics.counters.blocked)}
              detail={`${formatNumber(metrics.active_domains)} active domains`}
              icon={<ShieldCheck size={18} />}
            />
          </section>

          <section className="command-grid">
            <Panel
              eyebrow="FRONTIER COMPOSITION"
              title="URL lifecycle"
              className="frontier-composition"
              action={
                <Link className="icon-link" to="/console/frontier" aria-label="Open frontier">
                  <ArrowUpRight size={17} />
                </Link>
              }
            >
              {frontierTotal === 0 ? (
                <EmptyState
                  title="Frontier is empty"
                  detail="Start this draft run to release its seed URLs to the scheduler."
                />
              ) : (
                <div className="status-bars">
                  {statusEntries
                    .sort(([, a], [, b]) => b - a)
                    .map(([status, count]) => (
                      <div className="status-bar-row" key={status}>
                        <div className="bar-label">
                          <span>{status.replaceAll("_", " ")}</span>
                          <strong>{formatNumber(count)}</strong>
                        </div>
                        <div className="bar-track">
                          <span style={{ width: `${Math.max((count / frontierTotal) * 100, 1)}%` }} />
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </Panel>

            <Panel eyebrow="PARSER QUALITY" title="Extraction signal">
              <div className="quality-readout">
                <div className="quality-value">{formatPercent(metrics.parser_success_rate)}</div>
                <p>documents containing extracted main text</p>
              </div>
              <dl className="definition-grid">
                <div>
                  <dt>Duplicate rate</dt>
                  <dd>{formatPercent(metrics.duplicate_rate)}</dd>
                </div>
                <div>
                  <dt>Median fetch</dt>
                  <dd>{formatDuration(metrics.fetch_latency_p50_ms)}</dd>
                </div>
                <div>
                  <dt>Retries queued</dt>
                  <dd>{formatNumber(metrics.counters.retries)}</dd>
                </div>
                <div>
                  <dt>Failures</dt>
                  <dd>{formatNumber(metrics.counters.failed)}</dd>
                </div>
              </dl>
            </Panel>
          </section>

          <Panel eyebrow="EVENT STREAM" title="Recent crawl events">
            {metrics.recent_events.length === 0 ? (
              <EmptyState title="No events recorded" detail="Lifecycle events appear here as the run advances." />
            ) : (
              <ol className="event-stream">
                {metrics.recent_events.map((event) => (
                  <li key={event.id}>
                    <span className="event-node" aria-hidden="true" />
                    <time dateTime={event.created_at}>{formatDate(event.created_at)}</time>
                    <strong>{event.event_type.replaceAll("_", " ")}</strong>
                    <code>{event.frontier_entry_id ? shortId(event.frontier_entry_id) : "RUN"}</code>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </>
      ) : null}
    </div>
  );
}

function MetricCard({
  index,
  label,
  value,
  detail,
  icon,
}: {
  index: string;
  label: string;
  value: string;
  detail: string;
  icon: React.ReactNode;
}) {
  return (
    <article className="metric-card">
      <div className="metric-card-top">
        <span>{index}</span>
        {icon}
      </div>
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}
