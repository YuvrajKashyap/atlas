#!/usr/bin/env node

import { mkdir, writeFile } from "node:fs/promises";

const apiBase = process.env.ATLAS_API_BASE_URL?.replace(/\/$/, "");
const token = process.env.ATLAS_ID_TOKEN;
if (!apiBase || !token) throw new Error("ATLAS_API_BASE_URL and ATLAS_ID_TOKEN are required");

const authHeaders = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}/api/v1${path}`, {
    ...options,
    headers: { ...authHeaders, ...options.headers },
    signal: AbortSignal.timeout(20_000),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(`${options.method ?? "GET"} ${path}: ${response.status} ${JSON.stringify(body)}`);
  return body;
}

const health = await fetch(`${apiBase}/health`, { signal: AbortSignal.timeout(10_000) });
if (!health.ok) throw new Error(`Health check failed: ${health.status}`);

const unauthorized = await fetch(`${apiBase}/api/v1/crawl-runs`, {
  signal: AbortSignal.timeout(10_000),
});
if (unauthorized.status !== 401) {
  throw new Error(`Unauthenticated API returned ${unauthorized.status}, expected 401`);
}

await request("/system/status");
const created = await request("/crawl-runs", {
  method: "POST",
  body: JSON.stringify({
    name: `release-smoke-${new Date().toISOString()}`,
    seeds: ["https://example.com/"],
    allowed_domains: [{ domain: "example.com", include_subdomains: false }],
    max_pages: 1,
    max_depth: 0,
    per_domain_delay_ms: 1000,
    max_duration_seconds: 300,
    global_concurrency: 1,
    per_domain_concurrency: 1,
  }),
});
await request(`/crawl-runs/${created.id}/start`, { method: "POST" });

const deadline = Date.now() + 300_000;
let run;
while (Date.now() < deadline) {
  run = await request(`/crawl-runs/${created.id}`);
  if (["completed", "failed", "cancelled"].includes(run.status)) break;
  await new Promise((resolve) => setTimeout(resolve, 5_000));
}
if (!run || run.status !== "completed" || run.counters.indexed !== 1) {
  throw new Error(`Controlled crawl did not complete cleanly: ${JSON.stringify(run)}`);
}

const metrics = await request(`/metrics/overview?run_id=${created.id}`);
const tasks = await request(`/operations/tasks?run_id=${created.id}`);
if (tasks.some((task) => !["succeeded", "cancelled"].includes(task.status))) {
  throw new Error(`Smoke run has non-terminal tasks: ${JSON.stringify(tasks)}`);
}

const evidence = {
  schemaVersion: 1,
  verifiedAt: new Date().toISOString(),
  gitCommit: process.env.GITHUB_SHA ?? "local",
  run,
  metrics,
  tasks,
};
await mkdir("artifacts", { recursive: true });
await writeFile("artifacts/smoke-run.json", `${JSON.stringify(evidence, null, 2)}\n`);
process.stdout.write(`${created.id}\n`);
