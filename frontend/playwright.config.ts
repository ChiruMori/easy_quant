import { fileURLToPath } from "node:url"

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
      command:
        "uv run --project . flask --app tests.e2e_app:create_e2e_app run --no-reload --host 127.0.0.1 --port 5100",
      cwd: fileURLToPath(new URL("../backend", import.meta.url)),
      env: { FLASK_SKIP_DOTENV: "1" },
      url: "http://127.0.0.1:5100/api/v1/health",
      reuseExistingServer: false,
    },
    {
      command: "pnpm dev --host 127.0.0.1 --port 5174 --strictPort",
      env: { EASY_QUANT_API_PROXY_TARGET: "http://127.0.0.1:5100" },
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
    },
  ],
})
