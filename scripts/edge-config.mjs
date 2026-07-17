#!/usr/bin/env node

const required = ["VERCEL_API_TOKEN", "VERCEL_TEAM_ID", "EDGE_CONFIG_ID"];
for (const name of required) {
  if (!process.env[name]) throw new Error(`${name} is required`);
}

const [, , command, ...args] = process.argv;
const endpoint = `https://api.vercel.com/v1/edge-config/${process.env.EDGE_CONFIG_ID}`;
const headers = {
  Authorization: `Bearer ${process.env.VERCEL_API_TOKEN}`,
  "Content-Type": "application/json",
};

if (command === "get") {
  const response = await fetch(`${endpoint}/item/runtime?teamId=${process.env.VERCEL_TEAM_ID}`, {
    headers,
  });
  if (!response.ok) throw new Error(`Edge Config read failed: ${response.status}`);
  const body = await response.json();
  process.stdout.write(`${JSON.stringify(body.value ?? body)}\n`);
} else if (command === "set") {
  const [state, apiBaseUrl = "", environmentId = "", expiresAt = "", ...messageParts] = args;
  const allowed = new Set(["offline", "starting", "online", "degraded", "stopping"]);
  if (!allowed.has(state)) throw new Error(`Invalid runtime state: ${state}`);
  if (state === "online" && !apiBaseUrl.startsWith("https://")) {
    throw new Error("Online state requires an HTTPS API URL");
  }
  const runtime = {
    state,
    apiBaseUrl: apiBaseUrl || null,
    environmentId: environmentId || null,
    lastVerifiedAt: new Date().toISOString(),
    demoExpiresAt: expiresAt || null,
    message:
      messageParts.join(" ") ||
      (state === "offline"
        ? "The live crawler is parked. The permanent project record remains available."
        : `Atlas runtime is ${state}.`),
  };
  const response = await fetch(`${endpoint}/items?teamId=${process.env.VERCEL_TEAM_ID}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ items: [{ operation: "upsert", key: "runtime", value: runtime }] }),
  });
  if (!response.ok) throw new Error(`Edge Config update failed: ${response.status}`);
  process.stdout.write(`${JSON.stringify(runtime)}\n`);
} else {
  throw new Error("usage: edge-config.mjs get | set <state> [apiUrl envId expiresAt message]");
}
