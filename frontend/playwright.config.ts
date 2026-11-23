import { defineConfig } from "@playwright/test";

// End-to-end-tests draaien tegen een aparte backend met een tijdelijke, synthetische datamap
// (poort 3100), volledig gescheiden van de productiedatabase.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:3100", trace: "off", viewport: { width: 1440, height: 900 } },
  webServer: { command: "node e2e/server.mjs", url: "http://127.0.0.1:3100/api/health", timeout: 60_000, reuseExistingServer: false },
});
