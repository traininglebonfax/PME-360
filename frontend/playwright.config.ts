import { defineConfig } from "@playwright/test";

/**
 * Tests de bout en bout du parcours critique (Document 2, § 11), sur la seed de démonstration.
 * Prérequis : `docker compose up -d` (infra), API sur :8010 avec `seed_demo`, frontend sur :3010.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3010",
    channel: process.env.E2E_BROWSER_CHANNEL ?? "chrome",
    locale: "fr-FR",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3010/connexion",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
