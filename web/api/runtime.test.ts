import { afterEach, describe, expect, it, vi } from "vitest";

import handler from "./runtime";

function responseRecorder() {
  const record: { status: number; body: unknown; headers: Record<string, string> } = {
    status: 0,
    body: null,
    headers: {},
  };
  const response = {
    setHeader(name: string, value: string) {
      record.headers[name] = value;
      return response;
    },
    status(value: number) {
      record.status = value;
      return response;
    },
    json(value: unknown) {
      record.body = value;
      return response;
    },
  };
  return { record, response };
}

afterEach(() => {
  delete process.env.EDGE_CONFIG;
  vi.unstubAllGlobals();
});

describe("runtime status function", () => {
  it("fails closed when Edge Config is not connected", async () => {
    const { record, response } = responseRecorder();
    await handler({} as never, response as never);

    expect(record.status).toBe(200);
    expect(record.body).toMatchObject({ state: "offline", apiBaseUrl: null });
  });

  it("unwraps and publishes a valid Edge Config runtime item", async () => {
    process.env.EDGE_CONFIG = "https://edge-config.vercel.com/ecfg_test?token=secret";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            value: {
              state: "online",
              apiBaseUrl: "https://runtime.example",
              environmentId: "showcase-1",
              lastVerifiedAt: "2026-07-16T22:00:00Z",
              demoExpiresAt: "2026-07-17T02:00:00Z",
              message: "Verified",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const { record, response } = responseRecorder();
    await handler({} as never, response as never);

    expect(record.body).toMatchObject({ state: "online", environmentId: "showcase-1" });
  });

  it("rejects an online state without an API URL", async () => {
    process.env.EDGE_CONFIG = "https://edge-config.vercel.com/ecfg_test?token=secret";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            value: {
              state: "online",
              apiBaseUrl: null,
              environmentId: null,
              lastVerifiedAt: "2026-07-16T22:00:00Z",
              demoExpiresAt: null,
              message: "Invalid",
            },
          }),
          { status: 200 },
        ),
      ),
    );
    const { record, response } = responseRecorder();
    await handler({} as never, response as never);

    expect(record.body).toMatchObject({ state: "offline", apiBaseUrl: null });
  });
});
