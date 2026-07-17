import type {
  CrawlEvent,
  CrawlDefinition,
  CrawlRun,
  CrawlRunCreate,
  DocumentDetail,
  DocumentSummary,
  DomainHealth,
  FrontierEntry,
  IndexBuild,
  MetricsOverview,
  OperationalIncident,
  Page,
  PipelineTask,
  SearchResults,
  SystemStatus,
  WorkerHeartbeat,
} from "./types";

let apiBase: string | null = null;

export function configureApiBase(runtimeBaseUrl: string | null) {
  if (!runtimeBaseUrl) {
    apiBase = null;
    return;
  }
  const normalized = runtimeBaseUrl.replace(/\/$/, "");
  apiBase = normalized.endsWith("/api/v1") ? normalized : `${normalized}/api/v1`;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!apiBase) throw new ApiError("The Atlas runtime is offline", 503);
  const accessToken = sessionStorage.getItem("atlas:access-token");
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(body?.detail ?? `Atlas API returned ${response.status}`, response.status);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listRuns: () => request<CrawlRun[]>("/crawl-runs"),
  getRun: (runId: string) => request<CrawlRun>(`/crawl-runs/${runId}`),
  createRun: (payload: CrawlRunCreate) =>
    request<CrawlRun>("/crawl-runs", { method: "POST", body: JSON.stringify(payload) }),
  startRun: (runId: string) =>
    request<CrawlRun>(`/crawl-runs/${runId}/start`, { method: "POST" }),
  stopRun: (runId: string) =>
    request<CrawlRun>(`/crawl-runs/${runId}/stop`, { method: "POST" }),
  events: (runId: string) => request<CrawlEvent[]>(`/crawl-runs/${runId}/events?limit=50`),
  metrics: (runId: string) => request<MetricsOverview>(`/metrics/overview?run_id=${runId}`),
  frontier: (runId: string, search = "", status = "") => {
    const params = new URLSearchParams({ run_id: runId, page_size: "100" });
    if (search) params.set("query", search);
    if (status) params.set("status", status);
    return request<Page<FrontierEntry>>(`/frontier?${params}`);
  },
  documents: (runId: string, search = "") => {
    const params = new URLSearchParams({ run_id: runId, page_size: "100" });
    if (search) params.set("query", search);
    return request<Page<DocumentSummary>>(`/documents?${params}`);
  },
  document: (documentId: string) => request<DocumentDetail>(`/documents/${documentId}`),
  search: (query: string, runId?: string) => {
    const params = new URLSearchParams({ query, page_size: "50" });
    if (runId) params.set("run_id", runId);
    return request<SearchResults>(`/search?${params}`);
  },
  system: () => request<SystemStatus>("/system/status"),
  definitions: () => request<CrawlDefinition[]>("/crawl-definitions"),
  triggerDefinition: (definitionId: string) =>
    request<CrawlRun>(`/crawl-definitions/${definitionId}/trigger`, { method: "POST" }),
  tasks: (runId?: string) => {
    const params = new URLSearchParams();
    if (runId) params.set("run_id", runId);
    return request<PipelineTask[]>(`/operations/tasks?${params}`);
  },
  deadLetter: () => request<PipelineTask[]>("/operations/dead-letter"),
  retryTask: (taskId: string) =>
    request<PipelineTask>(`/operations/tasks/${taskId}/retry`, { method: "POST" }),
  workers: () => request<WorkerHeartbeat[]>("/operations/workers"),
  domainHealth: (runId?: string) => {
    const params = new URLSearchParams();
    if (runId) params.set("run_id", runId);
    return request<DomainHealth[]>(`/operations/domains?${params}`);
  },
  incidents: () => request<OperationalIncident[]>("/operations/incidents"),
  acknowledgeIncident: (incidentId: string) =>
    request<OperationalIncident>(`/operations/incidents/${incidentId}/acknowledge`, {
      method: "POST",
    }),
  resolveIncident: (incidentId: string) =>
    request<OperationalIncident>(`/operations/incidents/${incidentId}/resolve`, {
      method: "POST",
    }),
  indexBuilds: () => request<IndexBuild[]>("/operations/index-builds"),
  createIndexBuild: () =>
    request<IndexBuild>("/operations/index-builds", { method: "POST" }),
  documentVersions: (documentId: string) =>
    request<DocumentSummary[]>(`/documents/${documentId}/versions`),
  documentDiff: (documentId: string, againstId?: string) => {
    const params = new URLSearchParams();
    if (againstId) params.set("against_id", againstId);
    return request<Record<string, unknown>>(`/documents/${documentId}/diff?${params}`);
  },
  reparsePreview: (documentId: string) =>
    request<Record<string, unknown>>(`/documents/${documentId}/reparse-preview`, {
      method: "POST",
    }),
};
