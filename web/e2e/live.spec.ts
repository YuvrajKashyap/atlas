import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

import { expect, test } from "@playwright/test";

const idToken = process.env.ATLAS_E2E_ID_TOKEN;
const expectedEnvironment = process.env.ATLAS_E2E_EXPECTED_ENVIRONMENT;

test.describe("authenticated live console", () => {
  test.skip(!idToken || !expectedEnvironment, "Live Cognito credentials and an environment ID are required");

  test("verified runtime exposes persisted crawl operations", async ({ page, request }) => {
    const browserErrors: string[] = [];
    const apiResponses: Array<{ status: number; url: string }> = [];
    page.on("console", (message) => {
      if (message.type() === "error") browserErrors.push(message.text());
    });
    page.on("pageerror", (error) => browserErrors.push(error.message));
    page.on("response", (response) => {
      if (response.url().includes("/api/v1/")) {
        apiResponses.push({ status: response.status(), url: response.url() });
      }
    });

    let runtime: Record<string, unknown> = {};
    await expect
      .poll(
        async () => {
          const response = await request.get("/api/runtime", {
            headers: { "Cache-Control": "no-cache" },
          });
          if (!response.ok()) return `http-${response.status()}`;
          runtime = (await response.json()) as Record<string, unknown>;
          return runtime.state;
        },
        { timeout: 45_000, intervals: [1_000, 2_000, 5_000] },
      )
      .toBe("online");
    expect(runtime.environmentId).toBe(expectedEnvironment);

    await page.addInitScript(
      ({ token, expiresAt }) => {
        sessionStorage.setItem("atlas:access-token", token);
        sessionStorage.setItem("atlas:access-token-expiry", expiresAt);
      },
      { token: idToken!, expiresAt: String(Date.now() + 15 * 60_000) },
    );

    await page.goto("/console");
    await expect(page.getByRole("heading", { name: "Command center" })).toBeVisible({
      timeout: 45_000,
    });
    await expect(page.locator("#run-scope option", { hasText: /release-smoke-/ }).first()).toBeAttached();
    await expect(page.getByRole("alert")).toHaveCount(0);

    const screenshotPath = resolve(
      process.cwd(),
      process.env.ATLAS_E2E_SCREENSHOT_PATH ?? "test-results/live-console.png",
    );
    await mkdir(dirname(screenshotPath), { recursive: true });
    await page.screenshot({ path: screenshotPath, fullPage: true });

    const journeys = [
      { link: "Crawl runs", heading: "Crawl runs" },
      { link: "Frontier", heading: "Frontier" },
      { link: "Documents", heading: "Document explorer" },
      { link: "Tasks & dead letters", heading: "Tasks & dead letters" },
      { link: "Index & freshness", heading: "Index & freshness" },
    ];
    for (const journey of journeys) {
      await page.getByRole("link", { name: journey.link, exact: true }).click();
      await expect(page.getByRole("heading", { name: journey.heading, exact: true })).toBeVisible();
      await expect(page.getByRole("alert")).toHaveCount(0);
    }

    expect(apiResponses.length).toBeGreaterThan(0);
    expect(apiResponses.filter((response) => response.status >= 400)).toEqual([]);
    expect(browserErrors).toEqual([]);

    const evidencePath = resolve(
      process.cwd(),
      process.env.ATLAS_E2E_EVIDENCE_PATH ?? "test-results/live-console.json",
    );
    await mkdir(dirname(evidencePath), { recursive: true });
    await writeFile(
      evidencePath,
      `${JSON.stringify(
        {
          schemaVersion: 1,
          verifiedAt: new Date().toISOString(),
          gitCommit: process.env.GITHUB_SHA ?? "local",
          environmentId: expectedEnvironment,
          pagesVerified: ["/console", "/console/crawls", "/console/frontier", "/console/documents", "/console/tasks", "/console/index"],
          apiResponseCount: apiResponses.length,
          failedApiResponseCount: 0,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  });
});
