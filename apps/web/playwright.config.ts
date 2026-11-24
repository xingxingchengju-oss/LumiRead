import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
const systemChrome =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 30000,
  reporter: "list",
  outputDir: "../../var/qa/browser",
  use: {
    baseURL: "http://127.0.0.1:8749",
    headless: true,
    trace: "retain-on-failure",
    launchOptions: {
      args: [
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
      ],
      executablePath:
        process.env.LUMIREAD_CHROME ||
        (existsSync(systemChrome) ? systemChrome : undefined),
    },
  },
  webServer: {
    command: "../../.venv/bin/python ../../tests/browser_host.py",
    url: "http://127.0.0.1:8749/api/v1/health/ready",
    reuseExistingServer: false,
  },
});
