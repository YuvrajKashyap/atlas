#!/usr/bin/env node

import { mkdir, writeFile } from "node:fs/promises";

const apiBase = process.env.ATLAS_API_BASE_URL?.replace(/\/$/, "");
const token = process.env.ATLAS_ID_TOKEN;
if (!apiBase || !token) throw new Error("ATLAS_API_BASE_URL and ATLAS_ID_TOKEN are required");
const headers = { Authorization: `Bearer ${token}`, Accept: "application/json" };

async function read(path) {
  const response = await fetch(`${apiBase}/api/v1${path}`, {
    headers,
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

const runs = await read("/crawl-runs?limit=200");
const details = [];
for (const run of runs) {
  details.push({
    run,
    metrics: await read(`/metrics/overview?run_id=${run.id}`),
    tasks: await read(`/operations/tasks?run_id=${run.id}&limit=500`),
    events: await read(`/crawl-runs/${run.id}/events?limit=500`),
  });
}
const report = {
  schemaVersion: 1,
  exportedAt: new Date().toISOString(),
  environmentId: process.env.ATLAS_ENVIRONMENT_ID ?? null,
  gitCommit: process.env.GITHUB_SHA ?? "local",
  system: await read("/system/status"),
  incidents: await read("/operations/incidents?limit=500"),
  workers: await read("/operations/workers"),
  indexBuilds: await read("/operations/index-builds?limit=200"),
  runs: details,
};
await mkdir("artifacts", { recursive: true });
await writeFile("artifacts/runtime-report.json", `${JSON.stringify(report, null, 2)}\n`);
