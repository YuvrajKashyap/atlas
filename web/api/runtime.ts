import type { VercelRequest, VercelResponse } from "@vercel/node";

const states = new Set(["offline", "starting", "online", "degraded", "stopping"]);

type RuntimeRecord = {
  state: string;
  apiBaseUrl: string | null;
  environmentId: string | null;
  lastVerifiedAt: string;
  demoExpiresAt: string | null;
  message: string;
};

const offline = (message: string): RuntimeRecord => ({
  state: "offline",
  apiBaseUrl: null,
  environmentId: null,
  lastVerifiedAt: "1970-01-01T00:00:00.000Z",
  demoExpiresAt: null,
  message,
});

function validTimestamp(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}

function parseRuntime(value: unknown): RuntimeRecord | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Partial<RuntimeRecord>;
  if (
    typeof record.state !== "string" ||
    !states.has(record.state) ||
    !validTimestamp(record.lastVerifiedAt) ||
    typeof record.message !== "string" ||
    (record.apiBaseUrl !== null && typeof record.apiBaseUrl !== "string") ||
    (record.environmentId !== null && typeof record.environmentId !== "string") ||
    (record.demoExpiresAt !== null && !validTimestamp(record.demoExpiresAt))
  ) {
    return null;
  }
  if (record.state === "online" && !record.apiBaseUrl) return null;
  return record as RuntimeRecord;
}

export default async function handler(_request: VercelRequest, response: VercelResponse) {
  response.setHeader("Cache-Control", "public, s-maxage=5, stale-while-revalidate=15");
  const connection = process.env.EDGE_CONFIG;
  if (!connection) {
    return response
      .status(200)
      .json(offline("The live crawler is parked. The permanent project record remains available."));
  }

  try {
    const edgeConfigUrl = new URL(connection);
    edgeConfigUrl.pathname = `${edgeConfigUrl.pathname.replace(/\/$/, "")}/item/runtime`;
    const edgeConfigResponse = await fetch(edgeConfigUrl, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(3_000),
    });
    const payload = edgeConfigResponse.ok ? await edgeConfigResponse.json() : null;
    const runtime = parseRuntime(
      payload && typeof payload === "object" && "value" in payload
        ? (payload as { value: unknown }).value
        : payload,
    );
    return response.status(200).json(
      runtime ?? offline("Runtime configuration is invalid, so Atlas has failed closed."),
    );
  } catch {
    return response
      .status(200)
      .json(offline("Runtime configuration is unavailable, so Atlas has failed closed."));
  }
}
