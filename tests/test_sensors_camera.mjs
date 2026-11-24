// Real browser pointer input and JPEG capture, isolated rear-camera stream and HTTP fixture.
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";
const root = fileURLToPath(new URL("../", import.meta.url));
const require = createRequire(path.join(root, "apps/web/package.json"));
const { chromium, webkit, expect } = require("@playwright/test");
const safari = process.argv.includes("--webkit");
const { build } = createRequire(require.resolve("vite"))("esbuild");
const bundle = await build({
  stdin: {
    contents: `import React from "react";import {createRoot} from "react-dom/client";import {Camera} from "./src/Camera";
  const root=createRoot(document.querySelector("#root"));window.muteTest=silent=>root.render(<Camera sid="isolated" silent={silent}/>);window.muteTest(false);`,
    loader: "tsx",
    resolveDir: path.join(root, "apps/web"),
  },
  bundle: true,
  platform: "browser",
  format: "esm",
  jsx: "automatic",
  write: false,
  loader: { ".css": "empty" },
  define: { "process.env.NODE_ENV": '"production"' },
  metafile: true,
});
assert.ok(
  !Object.keys(bundle.metafile.inputs).some(
    (file) => file.includes("mediapipe") || file.endsWith("localVision.ts"),
  ),
);
const css = (
  await Promise.all(
    ["style.css", "glass/glass.css"].map((f) =>
      fs.readFile(path.join(root, "apps/web/src", f), "utf8"),
    ),
  )
).join("\n");
const marker = await fs.readFile(
  path.join(root, "apps/web/public/vision/paper-marker.svg"),
);
const browser = safari
  ? await webkit.launch()
  : await chromium.launch({
      headless: true,
      executablePath:
        process.env.LUMIREAD_CHROME ||
        (process.platform === "darwin"
          ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
          : undefined),
      args: ["--autoplay-policy=no-user-gesture-required"],
    });
try {
  const page = await browser.newPage({
    hasTouch: true,
    isMobile: true,
    viewport: { width: 420, height: 900 },
  });
  const uploads = [],
    batches = [],
    seen = new Set(),
    pageErrors = [],
    unexpected = [];
  let failNext = false,
    release;
  const fixtureDanger = new Map(),
    fixtureAlerts = new Map();
  await page.route("http://localhost/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()).pathname;
    if (url === "/")
      return route.fulfill({
        contentType: "text/html",
        body: '<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><div id="root"></div><link rel="stylesheet" href="/style.css"><script type="module" src="/app.js"></script>',
      });
    if (url === "/style.css")
      return route.fulfill({ contentType: "text/css", body: css });
    if (url === "/app.js")
      return route.fulfill({
        contentType: "text/javascript",
        body: Buffer.from(bundle.outputFiles[0].contents),
      });
    if (url === "/vision/paper-marker.svg")
      return route.fulfill({ contentType: "image/svg+xml", body: marker });
    if (url.endsWith("/captures")) {
      const data = await new Response(req.postDataBuffer(), {
        headers: { "content-type": req.headers()["content-type"] },
      }).formData();
      const bytes = Buffer.from(await data.get("photo").arrayBuffer());
      const entry = {
        source: data.get("source"),
        side: data.get("tap_side"),
        key: data.get("idem"),
        phone: data.get("phone_confirmed"),
        sha: createHash("sha256").update(bytes).digest("hex"),
      };
      uploads.push(entry);
      seen.add(entry.key);
      if (failNext) {
        failNext = false;
        await new Promise((resolve) => {
          release = resolve;
        });
        return route.fulfill({ status: 503, json: { detail: "回执测试" } });
      }
      return route.fulfill({
        status: 202,
        json: { capture_id: entry.key, job_id: "fixture" },
      });
    }
    if (url.endsWith("/alerts")) return route.fulfill({ json: { alerts: [] } });
    if (url.endsWith("/telemetry/batch")) {
      const samples = req.postDataJSON().samples;
      batches.push(...samples);
      for (const v of samples) {
        if (!["distance_cm", "brightness"].includes(v.metric)) continue;
        const unsafe =
          v.value !== null && v.value < (v.metric === "distance_cm" ? 33 : 65);
        if (!unsafe) {
          fixtureDanger.delete(v.metric);
          fixtureAlerts.delete(v.metric);
          continue;
        }
        if (!fixtureDanger.has(v.metric))
          fixtureDanger.set(v.metric, v.observed_at);
        if (v.observed_at - fixtureDanger.get(v.metric) >= 2)
          fixtureAlerts.set(v.metric, {
            ...v,
            id: "fixture-" + v.metric,
            ended_at: null,
          });
      }
      return route.fulfill({
        json: {
          accepted: samples.length,
          active_alerts: [...fixtureAlerts.values()],
        },
      });
    }
    if (url === "/favicon.ico") return route.fulfill({ status: 204, body: "" });
    unexpected.push(url);
    return route.abort();
  });
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await page.goto("http://localhost/");
  await page.evaluate(async () => {
    const m = new Image();
    m.src = "/vision/paper-marker.svg";
    await m.decode();
    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = 480;
    const ctx = canvas.getContext("2d");
    window.paper = { width: 84, brightness: 230 };
    function draw() {
      const { width, brightness } = window.paper;
      ctx.fillStyle =
        "rgb(" + [brightness, brightness, brightness].join(",") + ")";
      ctx.fillRect(0, 0, 640, 480);
      if (width > 0) {
        const h = (width * 80) / 70;
        ctx.drawImage(m, (640 - width) / 2, (480 - h) / 2, width, h);
      }
    }
    draw();
    setInterval(draw, 80);
    Object.defineProperty(MediaDevices.prototype, "getUserMedia", {
      configurable: true,
      value: async (constraints) => {
        window.testConstraints = constraints;
        const stream = canvas.captureStream(10);
        window.testTrack = stream.getVideoTracks()[0];
        return stream;
      },
    });
  });
  const finder = page.locator(".viewfinder");
  const status = page.getByRole("status");
  await page.getByRole("button", { name: "开启摄像头" }).click();
  await expect(finder.locator('[data-tap-side="left"]')).toBeVisible();
  await expect(finder.locator('[data-tap-side="right"]')).toBeVisible();
  assert.deepEqual(
    await page.evaluate(() => window.testConstraints.video.facingMode),
    { exact: "environment" },
  );
  await page.getByRole("checkbox", { name: /iPhone 16 Pro Max/ }).check();
  async function point(side = "left") {
    await finder.scrollIntoViewIfNeeded();
    const target =
      side === "center"
        ? finder
        : finder.locator('[data-tap-side="' + side + '"]');
    const box = await target.boundingBox();
    if (side !== "center") assert.ok(box.width >= 44 && box.height >= 44);
    return {
      x: Math.round(box.x + box.width / 2),
      y: Math.round(box.y + box.height / 2),
    };
  }
  async function single(side = "left") {
    const { x, y } = await point(side);
    await page.touchscreen.tap(x, y);
  }
  async function pair(side = "left") {
    await pairAt(await point(side));
  }
  async function pairAt({ x, y }) {
    await page.touchscreen.tap(x, y);
    await page.touchscreen.tap(x + 2, y + 1);
  }
  await single();
  await page.waitForTimeout(450);
  await single("left");
  await single("right");
  await pair("center");
  await page.waitForTimeout(450);
  assert.equal(uploads.length, 0);
  if (!safari) {
    const cdp = await page.context().newCDPSession(page);
    const p = await point(),
      finger = { id: 1, ...p };
    const dispatch = (type, points) =>
      cdp.send("Input.dispatchTouchEvent", { type, touchPoints: points });
    // Scroll/drag and long press each interrupt a waiting first tap.
    await single();
    await dispatch("touchStart", [finger]);
    await dispatch("touchMove", [{ ...finger, x: p.x + 28 }]);
    await dispatch("touchEnd", []);
    await single();
    await dispatch("touchStart", [finger]);
    await page.waitForTimeout(340);
    await dispatch("touchEnd", []);
    await single();
    await dispatch("touchStart", [finger]);
    await dispatch("touchStart", [finger, { ...finger, id: 2, x: p.x + 20 }]);
    await dispatch("touchEnd", []);
    await page.waitForTimeout(450);
    assert.equal(uploads.length, 0);
    await cdp.detach();
  }
  const sides = [
    "left",
    "right",
    "left",
    "right",
    "left",
    "right",
    "left",
    "right",
    "left",
    "right",
  ];
  for (const [i, side] of sides.entries()) {
    if (i === sides.length - 1) failNext = true;
    await pair(side);
    await expect.poll(() => uploads.length).toBe(i + 1);
    if (i < sides.length - 1) await expect(status).toContainText("照片已送达");
  }
  await expect(status).toContainText("正在上传");
  await pair("left");
  assert.equal(uploads.length, 10);
  release();
  await expect(status).toContainText("照片上传失败");
  await page.getByRole("button", { name: "重试上传" }).click();
  await expect(status).toContainText("照片已送达");
  assert.equal(uploads.length, 11);
  assert.equal(seen.size, 10);
  assert.deepEqual(uploads[10], uploads[9]);
  assert.deepEqual(
    uploads.slice(0, 10).map((x) => x.side),
    sides,
  );
  assert.ok(
    uploads.every(
      (x) => x.source === "double_tap" && x.phone === "true" && x.key,
    ),
  );
  const setPaper = (props) =>
    page.evaluate((p) => Object.assign(window.paper, p), props);
  const nearNotice = "离作业有点近，稍微坐远一点",
    darkNotice = "桌面有点暗，试试开灯或挪到亮一点的地方";
  await expect(page.getByText("距离合适", { exact: true })).toBeVisible();
  assert.ok(
    batches.some(
      (s) =>
        s.metric === "distance_cm" &&
        s.value >= 35 &&
        s.method === "qr-size-proxy-v2" &&
        s.calibration_id === null &&
        s.value_kind === "estimated",
    ),
  );
  assert.ok(batches.some((s) => s.metric === "brightness" && s.value > 75));
  await setPaper({ width: 155 });
  await expect(page.getByText("可能过近", { exact: true })).toBeVisible();
  await expect(page.getByText(nearNotice, { exact: false })).toBeVisible({
    timeout: 7000,
  });
  await setPaper({ width: 84 });
  await expect(page.getByText("距离合适", { exact: true })).toBeVisible();
  await expect(
    page.locator(".glass-alert").filter({ hasText: nearNotice }),
  ).toHaveCount(0);
  await setPaper({ width: 0 });
  await expect(page.getByText("暂时无法估计", { exact: true })).toBeVisible();
  assert.ok(
    batches.some(
      (s) =>
        s.metric === "distance_cm" &&
        s.value === null &&
        s.quality === "missing",
    ),
  );
  await setPaper({ brightness: 22 });
  await expect(page.getByText(darkNotice, { exact: false })).toBeVisible({
    timeout: 7000,
  });
  await setPaper({ width: 84, brightness: 230 });
  await expect(
    page.locator(".glass-alert").filter({ hasText: darkNotice }),
  ).toHaveCount(0);
  await expect(page.getByText("距离合适", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "模拟 45 分钟提醒" }).click();
  await expect
    .poll(
      () =>
        batches.some((s) => s.input_mode === "accelerated" && s.value === 2700),
      { timeout: 16000 },
    )
    .toBe(true);
  assert.ok(
    batches.some(
      (s) =>
        s.metric === "reading_seconds" &&
        s.input_mode === "live" &&
        s.value > 0 &&
        s.value < 100,
    ),
  );
  await page.getByRole("button", { name: "结束模拟" }).click();
  await expect
    .poll(() =>
      batches.some((s) => s.input_mode === "accelerated" && s.value === null),
    )
    .toBe(true);
  const left = await point("left"),
    right = await point("right");
  await page.getByRole("button", { name: "拍下作业" }).click();
  await expect(
    page.getByRole("img", { name: "待上传的作业照片" }),
  ).toBeVisible();
  await finder.scrollIntoViewIfNeeded();
  await pairAt(left);
  await pairAt(right);
  assert.equal(uploads.length, 11);
  await page.getByRole("button", { name: "重拍" }).click();
  await page.getByRole("button", { name: "拍下作业" }).click();
  await page.getByRole("button", { name: "上传并批改" }).click();
  await expect(status).toContainText("照片已送达");
  assert.equal(uploads.at(-1).source, "camera");
  assert.equal(uploads.at(-1).side, null);
  const jpg = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    return canvas.toDataURL("image/jpeg").split(",")[1];
  });
  await page.locator('input[type="file"]').setInputFiles({
    name: "system.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from(jpg, "base64"),
  });
  await page.getByRole("button", { name: "上传并批改" }).click();
  await expect(status).toContainText("照片已送达");
  assert.equal(uploads.at(-1).source, "native_camera");
  assert.equal(uploads.at(-1).side, null);
  await single();
  await page.evaluate(() => window.muteTest(true));
  await expect(page.getByRole("button", { name: "开启摄像头" })).toBeDisabled();
  assert.equal(await page.evaluate(() => window.testTrack.readyState), "ended");
  const before = uploads.length;
  await finder.scrollIntoViewIfNeeded();
  await pairAt(left);
  await pairAt(right);
  await page.waitForTimeout(400);
  const n = batches.length;
  await page.waitForTimeout(1250);
  assert.equal(uploads.length, before);
  assert.equal(batches.length, n);
  assert.ok(
    batches.every((s) =>
      ["distance_cm", "brightness", "reading_seconds"].includes(s.metric),
    ),
  );
  assert.deepEqual(unexpected, []);
  assert.deepEqual(pageErrors, []);
  console.log(
    "PASS " +
      (safari ? "WebKit" : "Chromium") +
      " · 5 left and 5 right pairs / 10 unique uploads, cross-side, center, single and silent taps 0, same-key same-side retry, automatic 50 mm paper estimate, near and dark alerts/recovery, missing marker, manual/native, clocks and track release",
  );
} finally {
  await browser.close();
}
