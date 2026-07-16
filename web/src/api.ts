import type {
  CrawlEvent,
  CrawlRun,
  CrawlRunCreate,
  DocumentDetail,
  DocumentSummary,
  FrontierEntry,
  MetricsOverview,
  Page,
  SearchResults,
  SystemStatus,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ??
  "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
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
};
