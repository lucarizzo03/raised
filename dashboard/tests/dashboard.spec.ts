import { expect, test, type Locator } from "@playwright/test";

async function bounds(locator: Locator) {
  const rect = await locator.boundingBox();
  expect(rect).not.toBeNull();
  return rect!;
}

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

test("aligns filter controls and keeps the brand square across viewport sizes", async ({ page }) => {
  for (const width of [320, 390, 640, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const round = await bounds(page.getByRole("combobox"));
    const score = await bounds(page.getByRole("spinbutton", { name: "Min score" }));
    const review = await bounds(page.getByRole("checkbox", { name: "Needs review only" }).locator(".."));
    const count = await bounds(page.getByText(/^Showing \d+ of \d+$/));
    const mark = await bounds(page.locator("header span").filter({ hasText: /^R$/ }));
    expect(Math.abs(round.y - score.y)).toBeLessThan(1);
    expect(round.height).toBe(score.height);
    expect(review.height).toBe(round.height);
    expect(Math.abs(review.y + review.height / 2 - count.y - count.height / 2)).toBeLessThan(1);
    expect(Math.abs(mark.width - mark.height)).toBeLessThan(1);
    if (width < 768) expect(Math.abs(count.x + count.width - score.x - score.width)).toBeLessThan(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
});

test("keeps table columns in place when details are expanded and sorted", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const positions = () => page.locator("thead th").evaluateAll((cells) => cells.map((cell) => {
    const { x, width } = cell.getBoundingClientRect();
    return { x, width };
  }));
  const before = await positions();
  await page.locator('tbody tr[role="button"]').first().click();
  await expect(page.getByRole("heading", { name: "Why this score" })).toBeVisible();
  expect(await positions()).toEqual(before);
  await page.getByRole("button", { name: "Raised", exact: true }).click();
  expect(await positions()).toEqual(before);
  const sortButtons = await page.locator("thead button").evaluateAll((buttons) => buttons.map((button) => ({
    height: button.getBoundingClientRect().height,
    whitespace: getComputedStyle(button).whiteSpace,
  })));
  expect(new Set(sortButtons.map((button) => button.height)).size).toBe(1);
  expect(sortButtons.every((button) => button.whitespace === "nowrap")).toBe(true);
});

test("aligns the copy button with its heading without shifting after copying", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.evaluate(() => Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: async () => {} },
  }));
  await page.locator('tbody tr[role="button"]').first().click();
  const copy = page.getByRole("button", { name: /^(Copy|Copied)$/ });
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(copy).toBeVisible();
    const button = await bounds(copy);
    const heading = await bounds(page.getByRole("heading", { name: "Draft email", exact: true }));
    const field = await bounds(page.getByRole("combobox"));
    expect(Math.abs(button.y + button.height / 2 - heading.y - heading.height / 2)).toBeLessThan(1);
    expect(button.height).toBe(field.height);
    expect(button.x + button.width).toBeLessThanOrEqual(width);
    const sources = await page.getByRole("link", { name: "source", exact: true }).evaluateAll((links) => links.map((link) => link.getBoundingClientRect().right));
    expect(sources.length).toBeGreaterThan(0);
    expect(Math.max(...sources) - Math.min(...sources)).toBeLessThan(1);
  }
  const before = await bounds(copy);
  await copy.click();
  await expect(copy).toHaveText("Copied");
  const after = await bounds(copy);
  expect(after.width).toBe(before.width);
  expect(after.x).toBe(before.x);
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
