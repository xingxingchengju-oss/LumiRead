// Replay original recorded timestamps through the exact browser CPU model and shutter.
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
const root = fileURLToPath(new URL("../../", import.meta.url));
const req = createRequire(path.join(root, "apps/web/package.json"));
const { chromium } = req("@playwright/test");
const ts = req("typescript");
const visionDir = path.dirname(req.resolve("@mediapipe/tasks-vision"));
const sourceFiles = { sensors: "sensors.ts", localVision: "localVision.ts" };
const manifest = JSON.parse(
  await fs.readFile(path.join(root, "data/vision/gesture-recordings.json")),
);
const review = process.argv.includes("--review");
const detail = process.argv.includes("--detail");
const baseline = process.argv.includes("--baseline");
const center = process.argv.includes("--center");
const original = baseline || center || process.argv.includes("--original");
const browser = await chromium.launch({
  headless: true,
  executablePath:
    process.env.LUMIREAD_CHROME ||
    (process.platform === "darwin"
      ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
      : undefined),
  args: ["--enable-unsafe-swiftshader"],
});
try {
  const page = await browser.newPage();
  await page.route("http://localhost/**", async (route) => {
    const u = new URL(route.request().url()).pathname;
    if (u === "/")
      return route.fulfill({
        contentType: "text/html",
        body: "<!doctype html><title>LumiRead local replay</title>",
      });
    if (u.slice(1) in sourceFiles) {
      const src = await fs.readFile(
        path.join(root, "ml/vision/legacy", sourceFiles[u.slice(1)]),
        "utf8",
      );
      const out = ts
        .transpileModule(src, {
          compilerOptions: {
            target: ts.ScriptTarget.ES2022,
            module: ts.ModuleKind.ESNext,
          },
        })
        .outputText.replace(
          '"@mediapipe/tasks-vision"',
          '"/vision-runtime.mjs"',
        );
      return route.fulfill({ contentType: "text/javascript", body: out });
    }
    const clip = manifest.find((s) => u === "/video/" + s.file);
    const file = clip
      ? path.join(root, ".cache/vision", clip.file)
      : u === "/vision-runtime.mjs"
        ? path.join(visionDir, "vision_bundle.mjs")
        : u.startsWith("/vision/")
          ? path.join(root, "ml/vision/legacy/assets", u.slice("/vision/".length))
          : null;
    if (!file) return route.abort();
    const buffer = await fs.readFile(file),
      r = route
        .request()
        .headers()
        .range?.match(/^bytes=(\d+)-(\d*)$/);
    const contentType = clip
      ? file.endsWith(".webm")
        ? "video/webm"
        : "video/mp4"
      : file.endsWith(".wasm")
        ? "application/wasm"
        : file.endsWith(".task")
          ? "application/octet-stream"
          : "text/javascript";
    if (!r) return route.fulfill({ contentType, body: buffer });
    const start = Number(r[1]),
      end = r[2]
        ? Math.min(Number(r[2]), buffer.length - 1)
        : buffer.length - 1;
    return route.fulfill({
      status: 206,
      contentType,
      headers: {
        "Accept-Ranges": "bytes",
        "Content-Range": `bytes ${start}-${end}/${buffer.length}`,
      },
      body: buffer.subarray(start, end + 1),
    });
  });
  await page.goto("http://localhost/");
  const results = [];
  for (const spec of manifest.filter(
    (s) => !baseline || s.split !== "new_test",
  )) {
    const out = await page.evaluate(
      async ({ spec, review, detail, center, original }) => {
        const v = document.createElement("video");
        v.preload = "auto";
        v.muted = true;
        const ready = new Promise((resolve, reject) => {
          v.onloadedmetadata = resolve;
          v.onerror = () =>
            reject(new Error("Video decode failed " + v.error?.message));
        });
        v.src = "/video/" + spec.file;
        await ready;
        const times = review
          ? Array.from(
              { length: Math.min(18, Math.floor(v.duration)) },
              (_, i) =>
                spec.label === "writing"
                  ? spec.session === "handwriting"
                    ? 30 + i * 4
                    : 2 + i * 3.5
                  : i + 0.2,
            )
          : Array.from(
              { length: spec.count },
              (_, i) => spec.start + i * spec.step,
            );
        const c = document.createElement("canvas");
        const scale = Math.min(640 / Math.max(v.videoWidth, v.videoHeight), 1);
        c.width = Math.round(v.videoWidth * scale);
        c.height = Math.round(v.videoHeight * scale);
        const ctx = c.getContext("2d");
        const sheet = document.createElement("canvas");
        sheet.width = 600;
        sheet.height = Math.ceil(times.length / 4) * 142;
        const sc = sheet.getContext("2d");
        const model = review
          ? null
          : await (
              await import("/localVision")
            ).loadVision("environment", center);
        const shutter = review
          ? null
          : new (await import("/sensors")).VictoryShutter();
        const frames = [];
        for (let i = 0; i < times.length; i++) {
          const t = times[i];
          if (t >= v.duration)
            throw new Error("Annotated interval beyond clip " + spec.file);
          const sought = new Promise((resolve) => {
            v.onseeked = resolve;
          });
          v.currentTime = t;
          await sought;
          ctx.drawImage(v, 0, 0, c.width, c.height);
          if (review) {
            const x = (i % 4) * 150,
              y = Math.floor(i / 4) * 142;
            const roi =
              detail && spec.session === "rdne"
                ? [0.43, 0.25, 0.27, 0.48]
                : detail && spec.session === "taryn"
                  ? [0.24, 0.12, 0.55, 0.42]
                  : [0, 0, 1, 1];
            const [rx, ry, rw, rh] = roi.map(
              (n, j) => n * (j % 2 ? c.height : c.width),
            );
            const factor = Math.min(148 / rw, 117 / rh);
            sc.fillStyle = "#fff";
            sc.fillRect(x, y, 150, 142);
            sc.drawImage(c, rx, ry, rw, rh, x, y, rw * factor, rh * factor);
            sc.fillStyle = "#222";
            sc.font = "14px sans-serif";
            sc.fillText(t.toFixed(1) + " s", x, y + 135);
          } else {
            const result = model.read(c, (t + 1) * 1000, v);
            const predicted = original
              ? result.category === "Victory" && result.score >= 0.7
              : result.victory;
            const { fire } = shutter.observe(predicted, t * 1000);
            frames.push({
              time_s: +t.toFixed(3),
              expected: spec.label === "victory",
              predicted,
              shutter: fire,
              ...(!original && {
                hand_detected: result.handVisible,
                category: result.category ?? null,
                confidence: result.score,
              }),
            });
          }
        }
        model?.close();
        return review
          ? sheet.toDataURL("image/jpeg", 0.9)
          : {
              session: spec.session,
              split: spec.split,
              label: spec.label,
              frames,
            };
      },
      { spec, review, detail, center, original },
    );
    if (review) {
      await fs.writeFile(
        path.join(root, ".cache/vision", spec.session + "-review.jpg"),
        Buffer.from(out.split(",")[1], "base64"),
      );
    } else results.push(out);
  }
  if (!review) {
    const summary = {};
    for (const split of baseline
      ? ["development", "test"]
      : ["development", "test", "new_test"]) {
      const records = results.filter((r) => r.split === split),
        f = records.flatMap((r) => r.frames);
      const positives = records.filter((r) => r.label === "victory"),
        negatives = records.filter((r) => r.label === "writing");
      const shots = (r) => r.frames.filter((f) => f.shutter).length;
      summary[split] = {
        sessions: records.length,
        frames: f.length,
        positive: f.filter((f) => f.expected).length,
        true_positive: f.filter((f) => f.expected && f.predicted).length,
        false_positive: f.filter((f) => !f.expected && f.predicted).length,
        true_negative: f.filter((f) => !f.expected && !f.predicted).length,
        false_negative: f.filter((f) => f.expected && !f.predicted).length,
        held_gestures: positives.length,
        exactly_one_shutter: positives.filter((r) => shots(r) === 1).length,
        writing_s: negatives.reduce(
          (a, r) => a + r.frames.at(-1).time_s - r.frames[0].time_s,
          0,
        ),
        writing_shutters: negatives.reduce((a, r) => a + shots(r), 0),
      };
    }
    await fs.writeFile(
      path.join(
        root,
        baseline
          ? "data/vision/gesture-baseline.json"
          : center
            ? "data/vision/gesture-center-results.json"
            : original
              ? "data/vision/gesture-results.json"
              : "data/vision/gesture-landmark-results.json",
      ),
      JSON.stringify(
        {
          protocol: center
            ? "LumiRead CPU browser replay with alternating center crop v2"
            : original
              ? "LumiRead CPU browser replay v1"
              : "Full-frame MediaPipe with world-landmark corroboration of medium-confidence Victory, retrospective replay",
          summary,
          results,
        },
        null,
        2,
      ) + "\n",
    );
    console.log(JSON.stringify(summary, null, 2));
  }
} finally {
  await browser.close();
}
