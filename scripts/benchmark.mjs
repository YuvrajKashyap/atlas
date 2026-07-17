#!/usr/bin/env node

import { mkdir, writeFile } from "node:fs/promises";

const apiBase = (process.env.ATLAS_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const command = process.argv[2];

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}/api/v1${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    signal: AbortSignal.timeout(30_000),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(`${options.method ?? "GET"} ${path}: ${response.status} ${JSON.stringify(body)}`);
  }
  return body;
}

if (command === "start") {
  const created = await request("/crawl-runs", {
    method: "POST",
    body: JSON.stringify({
      name: `deterministic-10000-${new Date().toISOString()}`,
      seeds: ["http://corpus/"],
      allowed_domains: [{ domain: "corpus", include_subdomains: false }],
      max_pages: 10020,
      max_depth: 0,
      per_domain_delay_ms: 250,
      request_timeout_seconds: 2,
      max_response_bytes: 2000000,
      max_redirects: 5,
      max_retries: 5,
      max_duration_seconds: 10800,
      global_concurrency: 20,
      per_domain_concurrency: 4,
      allowed_ports: [80],
    }),
  });
  await request(`/crawl-runs/${created.id}/start`, { method: "POST" });
  process.stdout.write(`${created.id}\n`);
} else if (command === "wait") {
  const runId = process.argv[3];
  if (!runId) throw new Error("benchmark.mjs wait requires a run ID");
  const deadline = Date.now() + 3 * 60 * 60 * 1000;
  let run;
  let lastPollError;
  while (Date.now() < deadline) {
    try {
      run = await request(`/crawl-runs/${runId}`);
      lastPollError = undefined;
      if (["completed", "failed", "cancelled"].includes(run.status)) break;
    } catch (error) {
      lastPollError = error;
      const message = error instanceof Error ? error.message : String(error);
      process.stderr.write(`Benchmark status poll failed; retrying: ${message}\n`);
    }
    await new Promise((resolve) => setTimeout(resolve, 10_000));
  }
  if (!run || run.status !== "completed") {
    const pollFailure =
      lastPollError instanceof Error ? `; last poll error: ${lastPollError.message}` : "";
    throw new Error(`Benchmark did not complete: ${JSON.stringify(run)}${pollFailure}`);
  }
  await mkdir("artifacts", { recursive: true });
  await writeFile("artifacts/benchmark-run.json", `${JSON.stringify(run, null, 2)}\n`);
  process.stdout.write(`${runId}\n`);
} else {
  throw new Error("usage: node scripts/benchmark.mjs [start|wait RUN_ID]");
}
