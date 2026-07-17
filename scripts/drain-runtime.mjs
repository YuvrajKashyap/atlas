#!/usr/bin/env node

const apiBase = process.env.ATLAS_API_BASE_URL?.replace(/\/$/, "");
const token = process.env.ATLAS_ID_TOKEN;
if (!apiBase || !token) throw new Error("ATLAS_API_BASE_URL and ATLAS_ID_TOKEN are required");
const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

async function call(path, options = {}) {
  const response = await fetch(`${apiBase}/api/v1${path}`, {
    ...options,
    headers,
    signal: AbortSignal.timeout(20_000),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(`${path}: ${response.status} ${JSON.stringify(body)}`);
  return body;
}

const runs = await call("/crawl-runs?limit=200");
for (const run of runs.filter((item) => ["running", "stopping"].includes(item.status))) {
  if (run.status === "running") await call(`/crawl-runs/${run.id}/stop`, { method: "POST" });
}

const deadline = Date.now() + 180_000;
while (Date.now() < deadline) {
  const tasks = await call("/operations/tasks?limit=500");
  if (!tasks.some((task) => task.status === "leased")) {
    process.stdout.write("Runtime drained: no leased tasks remain\n");
    process.exit(0);
  }
  await new Promise((resolve) => setTimeout(resolve, 5_000));
}
throw new Error("Timed out waiting for leased tasks to drain");
