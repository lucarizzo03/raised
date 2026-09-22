import { expect, test, type Page } from "@playwright/test";

async function missingLogos(page: Page) {
  return page.locator('tbody tr[role="button"]').evaluateAll((rows) =>
    rows.flatMap((row) => {
      const cell = row.querySelectorAll("td")[1];
      const domain = cell.querySelector(".text-xs")?.textContent?.trim();
      if (!domain) return [];
      const image = cell.querySelector("img");
      return image?.complete && image.naturalWidth > 0 && getComputedStyle(image).opacity === "1"
        ? []
        : [domain];
    })
  );
}

test("deployed dashboard loads verified-domain logos on opening and reload", async ({ page }) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  const retiredProviderRequests: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (new URL(request.url()).hostname === "logo.clearbit.com") {
      retiredProviderRequests.push(request.url());
    }
  });

  for (let visit = 0; visit < 2; visit++) {
    if (visit === 0) await page.goto("/", { waitUntil: "domcontentloaded" });
    else await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Raised", exact: true })).toBeVisible();
    await expect(page.locator("header")).not.toContainText("Sample data");
    await expect(page.locator('tbody tr[role="button"]').first()).toBeVisible();
    await expect(page.locator("tbody img").first()).toHaveCSS("opacity", "1");
    const showAll = page.getByRole("button", { name: /^Show all/ });
    if (await showAll.count()) {
      await showAll.click();
      await expect(page.getByRole("button", { name: "Show top 25", exact: true })).toBeVisible();
    }
    await expect.poll(() => missingLogos(page), { timeout: 20000 }).toEqual([]);
  }

  expect(retiredProviderRequests).toEqual([]);
  expect(errors).toEqual([]);
});
