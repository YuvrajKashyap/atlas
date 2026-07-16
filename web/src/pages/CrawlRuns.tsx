import { CircleStop, Play, Plus, X } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "../api";
import { PageHeader } from "../components/PageHeader";
import { EmptyState, ErrorState, LoadingState, StatusChip } from "../components/primitives";
import { formatDate, formatNumber, shortId } from "../lib/format";
import { useRunScope } from "../state/run-scope";
import type { CrawlRunCreate } from "../types";

const DEFAULT_USER_AGENT = "AtlasBot/0.1 (+https://github.com/atlas-crawler)";

export function CrawlRuns() {
  const [showForm, setShowForm] = useState(false);
  const { runs, isLoading, error, setSelectedRunId } = useRunScope();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["runs"] });
  const startMutation = useMutation({ mutationFn: api.startRun, onSuccess: refresh });
  const stopMutation = useMutation({ mutationFn: api.stopRun, onSuccess: refresh });

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="SURVEY REGISTRY"
        title="Crawl runs"
        description="Each crawl is an isolated, durable execution with its own policy, frontier, counters, and history."
        actions={
          <button className="primary-button" type="button" onClick={() => setShowForm(true)}>
            <Plus size={16} /> New crawl
          </button>
        }
      />

      {isLoading ? <LoadingState label="Reading run registry" /> : null}
      {error ? <ErrorState error={error} /> : null}
      {!isLoading && !error && runs.length === 0 ? (
        <EmptyState
          title="No crawl runs"
          detail="Commission a bounded survey with one or more seed URLs and an explicit domain allowlist."
        />
      ) : null}

      {runs.length > 0 ? (
        <div className="run-list">
          <div className="table-header run-row">
            <span>Survey</span>
            <span>Status</span>
            <span>Observed</span>
            <span>Indexed</span>
            <span>Created</span>
            <span aria-label="Actions" />
          </div>
          {runs.map((run) => {
            const pending = startMutation.isPending || stopMutation.isPending;
            return (
              <article className="run-row data-row" key={run.id}>
                <button
                  className="run-identity"
                  type="button"
                  onClick={() => setSelectedRunId(run.id)}
                >
                  <strong>{run.name}</strong>
                  <span>{shortId(run.id)} · {run.seeds[0]}</span>
                </button>
                <StatusChip status={run.status} />
                <span className="tabular">{formatNumber(run.counters.discovered)}</span>
                <span className="tabular">{formatNumber(run.counters.indexed)}</span>
                <time dateTime={run.created_at}>{formatDate(run.created_at)}</time>
                <div className="row-actions">
                  {run.status === "draft" ? (
                    <button
                      className="compact-button"
                      type="button"
                      disabled={pending}
                      onClick={() => startMutation.mutate(run.id)}
                    >
                      <Play size={14} /> Start
                    </button>
                  ) : null}
                  {run.status === "running" ? (
                    <button
                      className="compact-button danger-button"
                      type="button"
                      disabled={pending}
                      onClick={() => stopMutation.mutate(run.id)}
                    >
                      <CircleStop size={14} /> Stop
                    </button>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      ) : null}

      {startMutation.error ? <ErrorState error={startMutation.error} /> : null}
      {stopMutation.error ? <ErrorState error={stopMutation.error} /> : null}
      {showForm ? <CreateRunDialog onClose={() => setShowForm(false)} /> : null}
    </div>
  );
}

function CreateRunDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { setSelectedRunId } = useRunScope();
  const [formError, setFormError] = useState<string | null>(null);
  const createMutation = useMutation({
    mutationFn: api.createRun,
    onSuccess: async (run) => {
      setSelectedRunId(run.id);
      await queryClient.invalidateQueries({ queryKey: ["runs"] });
      onClose();
    },
  });

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    const data = new FormData(event.currentTarget);
    const seeds = String(data.get("seeds") ?? "")
      .split(/[\n,]/)
      .map((value) => value.trim())
      .filter(Boolean);
    const domains = String(data.get("domains") ?? "")
      .split(/[\n,]/)
      .map((value) => value.trim())
      .filter(Boolean);
    if (seeds.length === 0 || domains.length === 0) {
      setFormError("At least one seed URL and one allowed domain are required.");
      return;
    }
    const payload: CrawlRunCreate = {
      name: String(data.get("name") ?? "").trim(),
      seeds,
      allowed_domains: domains.map((domain) => ({ domain, include_subdomains: true })),
      max_pages: Number(data.get("max_pages")),
      max_depth: Number(data.get("max_depth")),
      per_domain_delay_ms: Number(data.get("per_domain_delay_ms")),
      request_timeout_seconds: 15,
      max_response_bytes: 2_000_000,
      max_redirects: 5,
      max_retries: 3,
      user_agent: DEFAULT_USER_AGENT,
    };
    createMutation.mutate(payload);
  };

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-run-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="dialog-header">
          <div>
            <span className="eyebrow">NEW SURVEY</span>
            <h2 id="create-run-title">Commission crawl run</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close dialog">
            <X size={18} />
          </button>
        </header>
        <form className="crawl-form" onSubmit={handleSubmit}>
          <label>
            Run name
            <input name="name" required maxLength={120} placeholder="Public docs survey" autoFocus />
          </label>
          <label>
            Seed URLs
            <textarea name="seeds" required rows={3} placeholder="https://docs.example.com/" />
            <small>One URL per line. Every seed must match the allowlist.</small>
          </label>
          <label>
            Allowed domains
            <textarea name="domains" required rows={2} placeholder="docs.example.com" />
            <small>Subdomains are included. Redirects are checked against this boundary.</small>
          </label>
          <div className="form-grid">
            <label>
              Page budget
              <input name="max_pages" type="number" min="1" max="10000" defaultValue="100" />
            </label>
            <label>
              Max depth
              <input name="max_depth" type="number" min="0" max="10" defaultValue="2" />
            </label>
            <label>
              Domain delay (ms)
              <input
                name="per_domain_delay_ms"
                type="number"
                min="250"
                max="60000"
                defaultValue="1000"
              />
            </label>
          </div>
          {formError ? <p className="form-error">{formError}</p> : null}
          {createMutation.error ? <p className="form-error">{createMutation.error.message}</p> : null}
          <footer className="dialog-actions">
            <button className="secondary-button" type="button" onClick={onClose}>Cancel</button>
            <button className="primary-button" type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Creating…" : "Create draft"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
