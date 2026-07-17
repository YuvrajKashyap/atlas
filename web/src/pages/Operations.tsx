import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Code2,
  DatabaseZap,
  Play,
  RotateCcw,
  ServerCog,
} from "lucide-react";
import { useMemo, useState } from "react";

import { api } from "../api";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingState, Panel, StatusChip } from "../components/primitives";
import { formatDate, formatNumber, formatPercent, shortId } from "../lib/format";
import { useRunScope } from "../state/run-scope";
import type { OperationalIncident, PipelineTask } from "../types";

export function CrawlDefinitions() {
  const queryClient = useQueryClient();
  const definitions = useQuery({ queryKey: ["definitions"], queryFn: api.definitions });
  const trigger = useMutation({
    mutationFn: api.triggerDefinition,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["definitions"] });
    },
  });
  return (
    <OperationsPage eyebrow="AUTOMATION / DEFINITIONS" title="Crawl definitions" description="Reusable policy and schedules. Each trigger creates a separate immutable crawl execution.">
      {definitions.isLoading ? <LoadingState label="Reading definitions" /> : null}
      {definitions.error ? <ErrorState error={definitions.error} /> : null}
      {definitions.data?.length === 0 ? <EmptyState title="No reusable definitions" detail="Definitions can be created through the authenticated API. Their executions will appear in Crawl Runs." /> : null}
      <div className="ops-card-list">
        {definitions.data?.map((definition) => (
          <article className="ops-card" key={definition.id}>
            <header><div><span className="eyebrow">{shortId(definition.id)}</span><h2>{definition.name}</h2></div><StatusChip status={definition.enabled ? "ok" : "offline"} /></header>
            <p>{definition.description ?? "No description recorded."}</p>
            <dl><div><dt>Schedule</dt><dd>{definition.schedule_cron ?? "Manual"}</dd></div><div><dt>Time zone</dt><dd>{definition.schedule_timezone}</dd></div><div><dt>Next run</dt><dd>{definition.next_run_at ? formatDate(definition.next_run_at) : "Not scheduled"}</dd></div></dl>
            <button type="button" className="compact-button" disabled={!definition.enabled || trigger.isPending} onClick={() => trigger.mutate(definition.id)}><Play size={13} /> Trigger execution</button>
          </article>
        ))}
      </div>
    </OperationsPage>
  );
}

export function TaskOperations() {
  const { selectedRunId } = useRunScope();
  const queryClient = useQueryClient();
  const tasks = useQuery({ queryKey: ["tasks", selectedRunId], queryFn: () => api.tasks(selectedRunId ?? undefined), refetchInterval: 3_000 });
  const dead = useQuery({ queryKey: ["dead-letter"], queryFn: api.deadLetter, refetchInterval: 5_000 });
  const retry = useMutation({ mutationFn: api.retryTask, onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["tasks"] }); void queryClient.invalidateQueries({ queryKey: ["dead-letter"] }); } });
  const counts = useMemo(() => groupTasks(tasks.data ?? []), [tasks.data]);
  return (
    <OperationsPage eyebrow="DURABLE EXECUTION" title="Tasks & dead letters" description="Persisted stage work, active leases, retry state, and operator-controlled recovery.">
      <section className="compact-metrics">{Object.entries(counts).map(([status, count]) => <div key={status}><span>{status.replaceAll("_", " ")}</span><strong>{formatNumber(count)}</strong></div>)}</section>
      {tasks.isLoading ? <LoadingState label="Reading task state" /> : null}
      {tasks.error ? <ErrorState error={tasks.error} /> : null}
      <Panel eyebrow="LATEST TASKS" title="Stage ledger">
        {tasks.data?.length ? <TaskTable tasks={tasks.data} /> : <EmptyState title="No tasks in scope" detail="Start a crawl execution to create durable fetch, extract, and index work." />}
      </Panel>
      <Panel eyebrow="OPERATOR QUEUE" title="Dead letters">
        {dead.error ? <ErrorState error={dead.error} /> : null}
        {dead.data?.length ? <div className="ops-table"><div className="ops-table-head"><span>Task</span><span>Stage</span><span>Attempts</span><span>Error</span><span>Action</span></div>{dead.data.map((task) => <div className="ops-table-row" key={task.id}><code>{shortId(task.id)}</code><span>{task.task_type}</span><span>{task.attempt_count} / {task.max_attempts}</span><span className="truncate">{task.last_error_type ?? "Unknown"}: {task.last_error_message ?? "No message"}</span><button type="button" className="compact-button" disabled={retry.isPending} onClick={() => retry.mutate(task.id)}><RotateCcw size={12} /> Retry</button></div>)}</div> : <EmptyState title="No dead-lettered work" detail="Tasks that exhaust their bounded retries will remain here until an administrator retries or cancels them." />}
      </Panel>
    </OperationsPage>
  );
}

function groupTasks(tasks: PipelineTask[]): Record<string, number> {
  const initial: Record<string, number> = { ready: 0, leased: 0, retry_scheduled: 0, succeeded: 0, dead_lettered: 0 };
  for (const task of tasks) initial[task.status] = (initial[task.status] ?? 0) + 1;
  return initial;
}

function TaskTable({ tasks }: { tasks: PipelineTask[] }) {
  return <div className="ops-table"><div className="ops-table-head"><span>Task</span><span>Stage</span><span>Status</span><span>Lease owner</span><span>Updated</span></div>{tasks.map((task) => <div className="ops-table-row" key={task.id}><code>{shortId(task.id)}</code><span>{task.task_type} / g{task.generation}</span><span className={`plain-status plain-${task.status}`}>{task.status.replaceAll("_", " ")}</span><span className="truncate">{task.lease_owner ?? "—"}</span><time>{formatDate(task.updated_at)}</time></div>)}</div>;
}

export function WorkerFleet() {
  const workers = useQuery({ queryKey: ["workers"], queryFn: api.workers, refetchInterval: 3_000 });
  const now = workers.dataUpdatedAt;
  return (
    <OperationsPage eyebrow="EXECUTION / FLEET" title="Worker heartbeats" description="Workers are disposable. Their current assignment and last database heartbeat are not.">
      {workers.isLoading ? <LoadingState label="Locating workers" /> : null}
      {workers.error ? <ErrorState error={workers.error} /> : null}
      {workers.data?.length ? <div className="worker-grid">{workers.data.map((worker) => { const age = Math.max(0, Math.floor((now - Date.parse(worker.last_seen_at)) / 1000)); const healthy = age < 30; return <article className="worker-card" key={worker.worker_id}><header><ServerCog size={20} /><StatusChip status={healthy ? "ok" : "degraded"} /></header><h2>{worker.worker_id}</h2><p>{worker.queues.join(" · ")}</p><dl><div><dt>Heartbeat age</dt><dd>{age}s</dd></div><div><dt>Current task</dt><dd>{worker.current_task_id ? shortId(worker.current_task_id) : "Idle"}</dd></div><div><dt>Build</dt><dd>{worker.version}</dd></div></dl></article>; })}</div> : <EmptyState title="No worker heartbeats" detail="The fleet may be scaled to zero or the runtime may still be starting." />}
    </OperationsPage>
  );
}

export function DomainHealthPage() {
  const { selectedRunId } = useRunScope();
  const domains = useQuery({ queryKey: ["domain-health", selectedRunId], queryFn: () => api.domainHealth(selectedRunId ?? undefined), refetchInterval: 10_000 });
  return (
    <OperationsPage eyebrow="POLICY / DOMAINS" title="Domain health" description="Robots decisions, configured crawl delay, request outcomes, latency, and consecutive failures by host.">
      {domains.isLoading ? <LoadingState label="Reading domain policy" /> : null}
      {domains.error ? <ErrorState error={domains.error} /> : null}
      {domains.data?.length ? <div className="ops-table domain-table"><div className="ops-table-head"><span>Host</span><span>Robots</span><span>Attempts</span><span>Success</span><span>Latency</span></div>{domains.data.map((domain) => <div className="ops-table-row" key={`${domain.run_id}-${domain.host}`}><strong>{domain.host}</strong><span>{domain.robots_status ?? "—"} / {domain.crawl_delay_ms ?? 0}ms</span><span>{formatNumber(domain.attempts)} <small>{domain.consecutive_failures} consecutive failures</small></span><span>{formatPercent(domain.success_rate)}</span><span>{domain.average_latency_ms === null ? "—" : `${domain.average_latency_ms.toFixed(0)}ms`}</span></div>)}</div> : <EmptyState title="No domain state" detail="Robots and politeness telemetry appears after a run reaches its first host." />}
    </OperationsPage>
  );
}

export function IndexFreshnessPage() {
  const queryClient = useQueryClient();
  const builds = useQuery({ queryKey: ["index-builds"], queryFn: api.indexBuilds, refetchInterval: 5_000 });
  const create = useMutation({ mutationFn: api.createIndexBuild, onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["index-builds"] }) });
  return (
    <OperationsPage eyebrow="SEARCH / INDEX" title="Index & freshness" description="Versioned index builds are populated, verified, and atomically promoted behind the search alias." actions={<button type="button" className="primary-button" onClick={() => create.mutate()} disabled={create.isPending}><DatabaseZap size={14} /> Rebuild index</button>}>
      {builds.isLoading ? <LoadingState label="Reading index history" /> : null}
      {builds.error ? <ErrorState error={builds.error} /> : null}
      {builds.data?.length ? <div className="ops-card-list">{builds.data.map((build) => <article className="ops-card index-build-card" key={build.id}><header><div><span className="eyebrow">SCHEMA V{build.schema_version}</span><h2>{build.physical_index ?? shortId(build.id)}</h2></div><span className={`plain-status plain-${build.status}`}>{build.status}</span></header><div className="build-progress"><span style={{ width: `${build.expected_documents ? Math.min(100, (build.indexed_documents / build.expected_documents) * 100) : 0}%` }} /></div><p>{formatNumber(build.indexed_documents)} / {formatNumber(build.expected_documents)} documents</p>{build.error_message ? <p className="ops-error">{build.error_message}</p> : null}<time>{formatDate(build.created_at)}</time></article>)}</div> : <EmptyState title="No index builds" detail="The first explicit rebuild will create a versioned physical index and verify its document count before promotion." />}
    </OperationsPage>
  );
}

export function IncidentsPage() {
  const queryClient = useQueryClient();
  const incidents = useQuery({ queryKey: ["incidents"], queryFn: api.incidents, refetchInterval: 5_000 });
  const transition = useMutation({ mutationFn: ({ incident, action }: { incident: OperationalIncident; action: "acknowledge" | "resolve" }) => action === "acknowledge" ? api.acknowledgeIncident(incident.id) : api.resolveIncident(incident.id), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["incidents"] }) });
  return (
    <OperationsPage eyebrow="RELIABILITY / INCIDENTS" title="Operational incidents" description="Persisted incidents turn recovery conditions into inspectable, auditable operator work.">
      {incidents.isLoading ? <LoadingState label="Reading incidents" /> : null}
      {incidents.error ? <ErrorState error={incidents.error} /> : null}
      {incidents.data?.length ? <div className="incident-list">{incidents.data.map((incident) => <article key={incident.id}><span className={`severity severity-${incident.severity}`}>{incident.severity}</span><div><span className="eyebrow">{incident.incident_type}</span><h2>{incident.title}</h2><p>{Object.keys(incident.details).length ? JSON.stringify(incident.details) : "No additional details."}</p><time>{formatDate(incident.created_at)}</time></div><div className="incident-actions">{incident.status === "open" ? <button type="button" className="compact-button" onClick={() => transition.mutate({ incident, action: "acknowledge" })}>Acknowledge</button> : null}{incident.status !== "resolved" ? <button type="button" className="compact-button" onClick={() => transition.mutate({ incident, action: "resolve" })}>Resolve</button> : <CheckCircle2 size={18} />}</div></article>)}</div> : <EmptyState title="No incidents recorded" detail="Detected lease, dependency, policy, and consistency failures will remain here through acknowledgment and resolution." />}
    </OperationsPage>
  );
}

export function ParserDebugger() {
  const { selectedRunId } = useRunScope();
  const documents = useQuery({ queryKey: ["documents", selectedRunId, "parser"], queryFn: () => api.documents(selectedRunId!, ""), enabled: Boolean(selectedRunId) });
  const [selectedId, setSelectedId] = useState<string>("");
  const effectiveId = selectedId || documents.data?.items[0]?.id || "";
  const versions = useQuery({ queryKey: ["versions", effectiveId], queryFn: () => api.documentVersions(effectiveId), enabled: Boolean(effectiveId) });
  const preview = useMutation({ mutationFn: () => api.reparsePreview(effectiveId) });
  return (
    <OperationsPage eyebrow="EXTRACTION / PARSERS" title="Parser debugger" description="Compare persisted versions and re-run the current parser against archived source HTML without touching the network.">
      {documents.isLoading ? <LoadingState label="Locating parser inputs" /> : null}
      {documents.error ? <ErrorState error={documents.error} /> : null}
      {documents.data?.items.length ? <><div className="parser-toolbar"><label htmlFor="parser-document">DOCUMENT</label><select id="parser-document" value={effectiveId} onChange={(event) => { setSelectedId(event.target.value); preview.reset(); }}>{documents.data.items.map((document) => <option key={document.id} value={document.id}>v{document.version_number} · {document.title ?? document.url}</option>)}</select><button type="button" className="primary-button" onClick={() => preview.mutate()} disabled={preview.isPending}><Code2 size={14} /> Run parser preview</button></div><section className="parser-grid"><Panel eyebrow="VERSION HISTORY" title={`${versions.data?.length ?? 0} persisted versions`}>{versions.data?.map((version) => <div className="version-row" key={version.id}><span>v{version.version_number}</span><div><strong>{version.change_kind.replaceAll("_", " ")}</strong><small>{formatDate(version.extracted_at)}</small></div><code>{version.content_hash.slice(0, 12)}</code></div>)}</Panel><Panel eyebrow="PREVIEW OUTPUT" title="Current parser">{preview.isPending ? <LoadingState label="Reprocessing archived HTML" /> : null}{preview.error ? <ErrorState error={preview.error} /> : null}{preview.data ? <pre className="json-preview">{JSON.stringify(preview.data, null, 2)}</pre> : <EmptyState title="No preview executed" detail="This operation reads the encrypted raw object and does not refetch the page." />}</Panel></section></> : <EmptyState title="No parser inputs" detail="Extracted documents with archived HTML are required for reprocessing." />}
    </OperationsPage>
  );
}

function OperationsPage({ eyebrow, title, description, actions, children }: { eyebrow: string; title: string; description: string; actions?: React.ReactNode; children: React.ReactNode }) {
  return <div className="page-stack"><PageHeader eyebrow={eyebrow} title={title} description={description} actions={actions} />{children}</div>;
}
