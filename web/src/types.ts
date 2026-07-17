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
  definition_id: string | null;
  generation: number;
  name: string;
  status: RunStatus;
  max_pages: number;
  max_depth: number;
  per_domain_delay_ms: number;
  request_timeout_seconds: number;
  max_response_bytes: number;
  max_redirects: number;
  max_retries: number;
  max_duration_seconds: number;
  global_concurrency: number;
  per_domain_concurrency: number;
  allowed_content_types: string[];
  allowed_ports: number[];
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
  resource_id: string | null;
  previous_version_id: string | null;
  version_number: number;
  is_current: boolean;
  change_kind: "initial" | "unchanged" | "metadata_only" | "minor" | "substantial";
  url: string;
  canonical_url: string;
  host: string;
  title: string | null;
  description: string | null;
  language: string | null;
  text_length: number;
  content_hash: string;
  simhash: string | null;
  simhash_bands: number[];
  duplicate_cluster_id: string | null;
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
  next_cursor?: string | null;
  facets?: Record<string, Array<{ key: string; count: number }>>;
  index_version?: number;
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
  max_duration_seconds?: number;
  global_concurrency?: number;
  per_domain_concurrency?: number;
  allowed_content_types?: string[];
  allowed_ports?: number[];
  user_agent: string;
}

export interface CrawlDefinition {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  schedule_cron: string | null;
  schedule_timezone: string;
  next_run_at: string | null;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export type PipelineTaskStatus =
  | "ready"
  | "leased"
  | "retry_scheduled"
  | "succeeded"
  | "dead_lettered"
  | "cancelled";

export interface PipelineTask {
  id: string;
  run_id: string;
  frontier_entry_id: string;
  task_type: "fetch" | "extract" | "index";
  status: PipelineTaskStatus;
  generation: number;
  attempt_count: number;
  max_attempts: number;
  available_at: string;
  lease_owner: string | null;
  lease_expires_at: string | null;
  last_heartbeat_at: string | null;
  payload: Record<string, unknown>;
  last_error_type: string | null;
  last_error_message: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkerHeartbeat {
  worker_id: string;
  queues: string[];
  version: string;
  current_task_id: string | null;
  started_at: string;
  last_seen_at: string;
  details: Record<string, unknown>;
}

export interface DomainHealth {
  run_id: string;
  host: string;
  robots_status: number | null;
  crawl_delay_ms: number | null;
  next_allowed_at: string | null;
  attempts: number;
  success_rate: number | null;
  average_latency_ms: number | null;
  consecutive_failures: number;
  last_success_at: string | null;
  last_failure_at: string | null;
}

export interface OperationalIncident {
  id: string;
  run_id: string | null;
  status: "open" | "acknowledged" | "resolved";
  severity: string;
  incident_type: string;
  title: string;
  details: Record<string, unknown>;
  acknowledged_at: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IndexBuild {
  id: string;
  status: "pending" | "building" | "verifying" | "succeeded" | "failed" | "rolled_back";
  schema_version: number;
  physical_index: string | null;
  expected_documents: number;
  indexed_documents: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}
