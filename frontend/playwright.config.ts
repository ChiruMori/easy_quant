import { defineConfig } from "@playwright/test"

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5174",
    channel: "chrome",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "powershell -NoProfile -ExecutionPolicy Bypass -File ../tools/start-e2e-backend.ps1",
      url: "http://127.0.0.1:5100/api/v1/health",
      reuseExistingServer: false,
    },
    {
      command:
        "powershell -NoProfile -ExecutionPolicy Bypass -File ../tools/start-e2e-frontend.ps1",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
    },
  ],
})
