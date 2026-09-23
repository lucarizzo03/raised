import { defineConfig } from "@playwright/test";

const deploymentUrl = process.env.PLAYWRIGHT_BASE_URL;

export default defineConfig({
  testDir: "./tests",
  testMatch: deploymentUrl
    ? ["**/dashboard.spec.ts", "**/deployed-logos.spec.ts", "**/security-headers.spec.ts"]
    : ["**/dashboard.spec.ts", "**/company-logo.spec.ts", "**/logo-route.spec.ts", "**/security-headers.spec.ts", "**/map.spec.ts"],
  fullyParallel: true,
  workers: 2,
  use: {
    baseURL: deploymentUrl ?? "http://127.0.0.1:3100",
    browserName: "chromium",
  },
  webServer: deploymentUrl ? undefined : {
    command: "npm run build && npm run start -- --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
    timeout: 120000,
    env: { SUPABASE_URL: "", SUPABASE_ANON_KEY: "" },
  },
});
