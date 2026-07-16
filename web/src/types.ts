export type RunStatus =
  | "draft"
  | "running"
  | "stopping"
  | "completed"
  | "failed"
  | "cancelled";

export type FrontierStatus =
  | "discovered"
  | "queued"
  | "fetching"
  | "fetched"
  | "extracting"
  | "indexing"
  | "indexed"
  | "retry_scheduled"
  | "robots_blocked"
  | "disallowed_domain"
  | "duplicate_url"
  | "duplicate_content"
  | "unsupported_content"
  | "budget_exhausted"
  | "failed";

export interface AllowedDomain {
  domain: string;
  include_subdomains: boolean;
}

export interface RunCounters {
  discovered: number;
  queued: number;
  fetching: number;
  indexed: number;
  failed: number;
  blocked: number;
  duplicates: number;
  retries: number;
  documents: number;
}

export interface CrawlRun {
  id: string;
  name: string;
  status: RunStatus;
  max_pages: number;
  max_depth: number;
  per_domain_delay_ms: number;
  request_timeout_seconds: number;
  max_response_bytes: number;
  max_redirects: number;
  max_retries: number;
  user_agent: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  stop_requested_at: string | null;
  seeds: string[];
  allowed_domains: AllowedDomain[];
  counters: RunCounters;
}

export interface CrawlEvent {
  id: number;
  run_id: string;
  frontier_entry_id: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface MetricsOverview {
  run_id: string;
  counters: RunCounters;
  throughput_per_minute: number;
  fetch_latency_p50_ms: number | null;
  fetch_latency_p95_ms: number | null;
  parser_success_rate: number | null;
  duplicate_rate: number | null;
  http_statuses: Record<string, number>;
  frontier_statuses: Record<string, number>;
  active_domains: number;
  recent_events: CrawlEvent[];
}

export interface FrontierEntry {
  id: string;
  run_id: string;
  url: string;
  normalized_url: string;
  host: string;
  status: FrontierStatus;
  priority: number;
  depth: number;
  discovered_from_id: string | null;
  first_seen_at: string;
  next_fetch_at: string | null;
  last_crawled_at: string | null;
  retry_count: number;
  fetch_attempt_count: number;
  robots_allowed: boolean | null;
  blocked_reason: string | null;
  last_error_type: string | null;
  last_error_message: string | null;
}

export interface DocumentSummary {
  id: string;
  run_id: string;
  frontier_entry_id: string;
  url: string;
  canonical_url: string;
  host: string;
  title: string | null;
  description: string | null;
  language: string | null;
  text_length: number;
  content_hash: string;
  duplicate_of_document_id: string | null;
  extraction_confidence: number;
  parser_name: string;
  parser_version: string;
  extraction_warnings: string[];
  extracted_at: string;
  indexed_at: string | null;
  index_name: string | null;
}

export interface DocumentDetail extends DocumentSummary {
  fetch_attempt_id: string;
  headings: string[];
  main_text: string;
}

export interface Page<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface SearchHit {
  document_id: string;
  run_id: string;
  url: string;
  canonical_url: string;
  host: string;
  title: string | null;
  description: string | null;
  headings: string[];
  main_text: string;
  language: string | null;
  content_hash: string;
  extraction_confidence: number;
  text_length: number;
  extracted_at: string;
  score: number | null;
  highlights: Record<string, string[]>;
}

export interface SearchResults {
  total: number;
  took_ms: number;
  page: number;
  page_size: number;
  items: SearchHit[];
}

export interface SystemStatus {
  status: "ok" | "degraded";
  postgres: string;
  redis: string;
  opensearch: Record<string, unknown>;
}

export interface CrawlRunCreate {
  name: string;
  seeds: string[];
  allowed_domains: AllowedDomain[];
  max_pages: number;
  max_depth: number;
  per_domain_delay_ms: number;
  request_timeout_seconds: number;
  max_response_bytes: number;
  max_redirects: number;
  max_retries: number;
  user_agent: string;
}
