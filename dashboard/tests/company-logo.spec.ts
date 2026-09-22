import { expect, test, type Page } from "@playwright/test";

const primary = "/api/logo?domain=acme.com";
const direct = "https://acme.com/favicon.ico";
const companyCell = (page: Page) => page.locator("tbody tr").first().locator("td").nth(1);

async function mockImages(page: Page, sizes: Record<string, number | Promise<number>>) {
  const session = await page.context().newCDPSession(page);
  const requests: string[] = [];
  const pending: Promise<void>[] = [];
  session.on("Fetch.requestPaused", ({ requestId, request }) => {
    requests.push(request.url);
    pending.push((async () => {
      const url = new URL(request.url);
      const size = await (sizes[request.url] ?? sizes[`${url.pathname}${url.search}`] ?? 0);
      if (!size) {
        await session.send("Fetch.failRequest", { requestId, errorReason: "Failed" });
        return;
      }
      await session.send("Fetch.fulfillRequest", {
        requestId,
        responseCode: 200,
        responseHeaders: [{ name: "Content-Type", value: "image/svg+xml" }],
        body: Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}"><rect width="100%" height="100%" fill="orange"/></svg>`).toString("base64"),
      });
    })());
  });
  await session.send("Fetch.enable", { patterns: [{ urlPattern: "*", resourceType: "Image" }] });
  return { requests, settle: () => Promise.all(pending) };
}

async function expectLoaded(page: Page, src: string) {
  const image = companyCell(page).locator("img");
  await expect(image).toHaveAttribute("src", src);
  await expect(image).toHaveCSS("opacity", "1");
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
}

test("loads logos on opening, reload and row expansion without Clearbit", async ({ page }) => {
  const { requests } = await mockImages(page, { [primary]: 128 });
  await page.goto("/");
  await expectLoaded(page, primary);
  await page.reload();
  await expectLoaded(page, primary);
  await page.getByRole("button", { name: "Acme Data, score 100", exact: true }).click();
  await expect(page.locator("tbody img")).toHaveCount(2);
  await expect(page.locator("tbody img").last()).toHaveCSS("opacity", "1");
  expect(requests.filter((url) => url.includes("logo.clearbit.com"))).toEqual([]);
});

test("keeps a valid 16px favicon", async ({ page }) => {
  await mockImages(page, { [primary]: 16 });
  await page.goto("/");
  await expectLoaded(page, primary);
});

test("shows initials while loading", async ({ page }) => {
  let release!: (size: number) => void;
  const pending = new Promise<number>((resolve) => { release = resolve; });
  const { settle } = await mockImages(page, { [primary]: pending });
  try {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(companyCell(page).getByText("AD", { exact: true })).toBeVisible();
    await expect(companyCell(page).locator("img")).toHaveCSS("opacity", "0");
  } finally {
    release(128);
    await settle();
  }
  await expectLoaded(page, primary);
});

test("waits for a slow logo response within the server timeout budget", async ({ page }) => {
  let release!: (size: number) => void;
  const pending = new Promise<number>((resolve) => { release = resolve; });
  const { settle } = await mockImages(page, { [primary]: pending, [direct]: 32 });
  try {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(6500);
    expect(await companyCell(page).locator("img").getAttribute("src")).toBe(primary);
  } finally {
    release(128);
    await settle();
  }
  await expectLoaded(page, primary);
});

test("uses the company favicon when the logo endpoint fails", async ({ page }) => {
  await mockImages(page, { [direct]: 32 });
  await page.goto("/");
  await expectLoaded(page, direct);
});

test("shows initials without broken images when both sources fail", async ({ page }) => {
  await mockImages(page, {});
  await page.goto("/");
  await expect(companyCell(page).getByText("AD", { exact: true })).toBeVisible();
  await expect(companyCell(page).locator("img")).toHaveCount(0);
});

test("times out a stalled provider and ignores its late response", async ({ page }) => {
  let release!: (size: number) => void;
  const pending = new Promise<number>((resolve) => { release = resolve; });
  const { settle } = await mockImages(page, { [primary]: pending, [direct]: 32 });
  try {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(companyCell(page).locator("img")).toHaveAttribute("src", direct, { timeout: 15000 });
    await expectLoaded(page, direct);
  } finally {
    release(128);
    await settle();
  }
  await expectLoaded(page, direct);
});
