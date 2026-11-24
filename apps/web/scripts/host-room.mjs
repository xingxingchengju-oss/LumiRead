import { chromium } from "@playwright/test";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const state = path.join(
  root,
  "var",
  process.argv.includes("--field") ? "field-room" : "host-room",
);
await mkdir(state, { recursive: true, mode: 0o700 });
const installedChrome =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const context = await chromium.launchPersistentContext(
  path.join(state, "browser"),
  {
    headless: false,
    executablePath:
      process.env.LUMIREAD_CHROME ||
      (existsSync(installedChrome) ? installedChrome : undefined),
    viewport: null,
  },
);
try {
  const page = context.pages()[0] || (await context.newPage());
  await page.goto("http://127.0.0.1:8742/app");
  if (process.argv.includes("--resume")) {
    const response = await page.request.get("http://127.0.0.1:8742/api/v1/me");
    if (!response.ok())
      throw new Error("No paired parent in this browser profile.");
    const { session_id, role } = await response.json();
    if (role !== "parent")
      throw new Error("The saved profile is not a parent.");
    await page.getByRole("heading", { name: "学习观察手册" }).waitFor();
    console.log("Reopened paired parent display", session_id);
  } else {
    await page
      .getByRole("button", { name: /创建学习场次|生成配对码|更新配对码/ })
      .first()
      .waitFor();
    const create = page.getByRole("button", { name: "创建学习场次" });
    if (await create.isVisible()) await create.click();
    const renew = page.getByRole("button", { name: /生成配对码|更新配对码/ });
    await renew.waitFor();
    const membership = await page.request.get(
      "http://127.0.0.1:8742/api/v1/me",
    );
    if (!membership.ok()) throw new Error("Parent session is unavailable.");
    const { session_id } = await membership.json();
    const setup = await page.request.get(
      `http://127.0.0.1:8742/api/v1/sessions/${session_id}/phone-setup`,
    );
    if (!setup.ok()) throw new Error("Phone setup is unavailable.");
    if ((await setup.json()).mode !== "public") await renew.click();
    const qr = page.getByRole("img", { name: "虚拟眼镜配对二维码" });
    await qr.waitFor();
    const resource = await page.request.get(
      new URL(await qr.getAttribute("src"), page.url()).href,
    );
    if (!resource.ok())
      throw new Error("Could not retrieve the paired room QR.");
    await writeFile(path.join(state, "camera-qr.png"), await resource.body(), {
      mode: 0o600,
    });
    console.log("Parent display open. Production session", session_id);
    console.log("Camera pairing image:", path.join(state, "camera-qr.png"));
  }
  await new Promise((resolve) => context.once("close", resolve));
} finally {
  await context.close().catch(() => {});
}
