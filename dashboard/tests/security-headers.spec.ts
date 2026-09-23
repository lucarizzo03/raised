import { expect, test } from "@playwright/test";

test("sends security headers on pages and API routes", async ({ request }) => {
  for (const path of ["/", "/api/logo?domain=example.com"]) {
    const response = await request.get(path);
    const headers = response.headers();
    expect(headers["content-security-policy"], path).toContain("frame-ancestors 'none'");
    expect(headers["content-security-policy"], path).toContain("object-src 'none'");
    expect(headers["x-frame-options"], path).toBe("DENY");
    expect(headers["x-content-type-options"], path).toBe("nosniff");
    expect(headers["referrer-policy"], path).toBe("strict-origin-when-cross-origin");
    expect(headers["x-powered-by"], path).toBeUndefined();
  }
});

test("the page renders without Content-Security-Policy violations", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && /Content Security Policy/i.test(message.text())) {
      violations.push(message.text());
    }
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Raised", exact: true })).toBeVisible();
  await page.locator('tbody tr[role="button"]').first().click();
  expect(violations).toEqual([]);
});
