import { expect, test } from "@playwright/test";

test("permanent project record renders without browser errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /the web changes/i })).toBeVisible();
  await expect(page.getByText("PostgreSQL is authoritative")).toBeVisible();
  await expect(page.locator(".vite-error-overlay")).toHaveCount(0);
  await page.screenshot({ path: "test-results/permanent-home.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("public navigation exposes architecture and verified-evidence policy", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Architecture", exact: true }).click();
  await expect(page).toHaveURL(/\/architecture$/);
  await expect(page.getByRole("heading", { name: /the database remembers/i })).toBeVisible();

  await page.getByRole("link", { name: "Benchmarks", exact: true }).click();
  await expect(page).toHaveURL(/\/benchmarks$/);
  await expect(page.getByText(/no release benchmark has been published yet/i)).toBeVisible();
});

test("offline console fails closed and sends no crawler API request", async ({ page }) => {
  const crawlerRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/")) crawlerRequests.push(request.url());
  });

  await page.goto("/console");
  await expect(page.getByRole("heading", { name: /the live console is parked/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /view runtime status/i })).toBeVisible();
  expect(crawlerRequests).toEqual([]);
});

test("mobile project navigation remains operable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("link", { name: "Documentation", exact: true }).click();
  await expect(page).toHaveURL(/\/docs$/);
  await expect(page.getByRole("heading", { name: /operate atlas from a clean checkout/i })).toBeVisible();
});
