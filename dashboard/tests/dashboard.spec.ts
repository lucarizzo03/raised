import { expect, test } from "@playwright/test";

const runtimeErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  runtimeErrors.length = 0;
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Raised", exact: true })).toBeVisible();
  if (process.env.PLAYWRIGHT_BASE_URL) {
    await expect(page.locator("header")).not.toContainText("Sample data");
  }
});

test.afterEach(() => { expect(runtimeErrors).toEqual([]); });

test("filters, sorts, and restores the company list", async ({ page }) => {
  const rows = page.locator('tbody tr[role="button"]');
  await expect(rows.first()).toBeVisible();
  await page.getByRole("combobox").selectOption("Seed");
  await expect.poll(async () => rows.evaluateAll((items) => items.every((row) => row.querySelectorAll("td")[3].textContent === "Seed"))).toBe(true);
  await expect(rows.first()).toBeVisible();
  await page.getByRole("spinbutton", { name: "Min score" }).fill("1000");
  await expect(page.getByText("No companies match these filters.")).toBeVisible();
  await expect(rows).toHaveCount(0);
  await page.getByRole("spinbutton", { name: "Min score" }).fill("0");
  await page.getByRole("combobox").selectOption("");
  await expect(rows.first()).toBeVisible();
  await page.getByRole("button", { name: "Score", exact: true }).click();
  const scores = await rows.evaluateAll((items) => items.map((row) => Number(row.querySelectorAll("td")[2].textContent)));
  expect(scores).toEqual([...scores].sort((a, b) => a - b));
  await page.getByRole("button", { name: "Score", exact: true }).click();
  const descending = await rows.evaluateAll((items) => items.map((row) => Number(row.querySelectorAll("td")[2].textContent)));
  expect(descending).toEqual([...descending].sort((a, b) => b - a));
  await page.getByRole("checkbox", { name: "Needs review only" }).check();
  if (await rows.count()) {
    await rows.first().click();
    await expect(page.getByRole("heading", { name: "Why this score" })).toBeVisible();
    await expect(page.getByText("review", { exact: true }).first()).toBeVisible();
  } else {
    await expect(page.getByText("No companies match these filters.")).toBeVisible();
  }
  await page.getByRole("checkbox", { name: "Needs review only" }).uncheck();
  await expect(rows.first()).toBeVisible();
});

test("expands evidence, copies the draft, and toggles show all", async ({ page }) => {
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (text: string) => { document.body.dataset.copiedDraft = text; } },
    });
  });
  const rows = page.locator('tbody tr[role="button"]');
  await rows.first().click();
  await expect(page.getByRole("heading", { name: "Why this score" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Investigation" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Draft email" })).toBeVisible();
  await page.getByRole("button", { name: "Copy", exact: true }).click();
  await expect(page.getByRole("button", { name: "Copied", exact: true })).toBeVisible();
  expect(await page.locator("body").getAttribute("data-copied-draft")).toContain("Hi there,");
  await rows.first().press("Enter");
  await expect(page.getByRole("heading", { name: "Why this score" })).toBeHidden();
  const count = await rows.count();
  const showAll = page.getByRole("button", { name: /^Show all/ });
  if (await showAll.count()) {
    await showAll.click();
    await expect.poll(() => rows.count()).toBeGreaterThan(count);
    await page.getByRole("button", { name: "Show top 25", exact: true }).click();
    await expect(rows).toHaveCount(count);
  }
});

test("remains usable on a narrow mobile viewport and after reload", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole("combobox")).toBeVisible();
  await expect(page.getByRole("spinbutton", { name: "Min score" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.locator('tbody tr[role="button"]').first().press("Enter");
  await expect(page.getByRole("heading", { name: "Why this score" })).toBeVisible();
});
