import { strict as assert } from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { test } from "node:test";
const root = fileURLToPath(new URL("../", import.meta.url));
const require = createRequire(path.join(root, "apps/web/package.json"));
const ts = require("typescript");
async function load(name) {
  const source = fs.readFileSync(
    path.join(root, "apps/web/src/glass", name + ".ts"),
    "utf8",
  );
  const js = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
    },
  }).outputText;
  return import(
    "data:text/javascript;base64," + Buffer.from(js).toString("base64")
  );
}
const { centerLuma, qrScale, distanceCm, sample, MARKER } =
  await load("sensors");
const { DoubleTap } = await load("doubleTap");
const pointer = (t, extra = {}) => ({
  pointerId: 1,
  pointerType: "touch",
  isPrimary: true,
  clientX: 32,
  clientY: 32,
  timeStamp: t,
  button: 0,
  ...extra,
});
function tap(g, t, extra = {}, hold = 40, side = "left") {
  g.begin(side, pointer(t, extra));
  return g.end(side, pointer(t + hold, extra));
}
test("two completed taps fire once, five pairs create five photos", () => {
  const g = new DoubleTap();
  for (let i = 0; i < 5; i++) {
    const side = i % 2 ? "right" : "left";
    assert.equal(tap(g, i * 500, {}, 40, side), false);
    assert.equal(tap(g, i * 500 + 135, { pointerId: 2 }, 40, side), true);
  }
  assert.equal(g.end("left", pointer(2500)), false);
  assert.equal(tap(g, 3000, { pointerType: "mouse" }), false);
  assert.equal(tap(g, 3150, { pointerType: "mouse" }), true);
});
test("distant taps, different tools, long presses, pointer cancellation and drag out-and-back cannot trigger", () => {
  for (const invalid of [
    (g) => tap(g, 200, {}, 40, "right"),
    (g) => tap(g, 200, { clientX: 75 }),
    (g) => tap(g, 200, { pointerType: "mouse" }),
    (g) => tap(g, 550),
    (g) => tap(g, 140, {}, 300),
    (g) => {
      g.begin("left", pointer(140));
      g.move(pointer(160, { clientY: 60 }));
      return g.end("left", pointer(190));
    },
    (g) => {
      g.begin("left", pointer(140));
      g.lost(1);
      return g.end("left", pointer(190));
    },
    (g) => {
      g.reset();
      return tap(g, 150);
    },
    (g) => {
      g.begin("left", pointer(140));
      g.begin("left", pointer(160, { pointerId: 2, isPrimary: false }));
      return g.end("left", pointer(190));
    },
    (g) => tap(g, 160, { pointerType: "mouse", button: 2 }),
  ]) {
    const g = new DoubleTap();
    assert.equal(tap(g, 0), false);
    assert.equal(invalid(g), false);
  }
});
test("decode the printable artwork, reject unrelated, skewed or distant markers", () => {
  const svg = fs.readFileSync(
    path.join(root, "apps/web/public/vision/paper-marker.svg"),
    "utf8",
  );
  const points = [...svg.matchAll(/M(\d+),(\d+)h1v1h-1z/g)].map((m) =>
    m.slice(1).map(Number),
  );
  const n = Math.max(...points.flat()) + 1,
    px = 6,
    size = (n + 8) * px;
  const pixels = new Uint8ClampedArray(size * size * 4).fill(255);
  for (const [x, y] of points)
    for (let j = 0; j < px; j++)
      for (let i = 0; i < px; i++) {
        const offset = (size * ((y + 4) * px + j) + (x + 4) * px + i) * 4;
        pixels.fill(0, offset, offset + 3);
      }
  assert.equal(require("jsqr")(pixels, size, size).data, MARKER);
  const marker = (x, y, w, h) => [
    { x, y },
    { x: x + w, y },
    { x: x + w, y: y + h },
    { x, y: y + h },
  ];
  const sw = qrScale(marker(120, 80, 80, 80), 320, 240);
  // 5 cm * 24/43.27 * native diagonal 400 px / marker side 80 px.
  assert.equal(distanceCm(sw, 320, 240), 13.9);
  assert.equal(distanceCm(sw, 240, 320), 13.9);
  assert.equal(distanceCm(sw, 320, 180), 13.9);
  assert.equal(distanceCm(sw, 320, 240, { zoom: 2 }), null);
  // 90° horizontal FOV at width 320 -> f=160 px -> 10 cm.
  const reported = {
    width: 320,
    height: 240,
    horizontalFieldOfView: 90,
    zoom: 2,
  };
  assert.equal(distanceCm(sw, 320, 240, reported), 10);
  assert.equal(distanceCm(sw, 240, 320, reported), 10);
  assert.equal(qrScale(marker(60, 90, 90, 45), 320, 240), null);
  assert.equal(qrScale(marker(5, 0, 30, 30), 320, 240), null);
  assert.equal(qrScale(marker(NaN, 80, 80, 80), 320, 240), null);
  assert.equal(qrScale(marker(120, 80, 80, 80), 320, Infinity), null);
  assert.equal(distanceCm(null, 320, 240), null);
});
test("brightness uses the measured central frame", () => {
  const red = new Uint8ClampedArray(64 * 64 * 4);
  for (let i = 0; i < red.length; i += 4) red[i] = red[i + 3] = 255;
  assert.equal(centerLuma(red, 64, 64), 54);
});
test("simulated observation, real clock and missing data retain source identity", () => {
  assert.equal(sample("reading_seconds", 2700, true).input_mode, "accelerated");
  assert.equal(sample("reading_seconds", 120).value_kind, "measured");
  assert.equal(sample("brightness", null).quality, "missing");
  assert.equal(sample("distance_cm", 31).calibration_id, null);
  assert.equal(sample("distance_cm", 31).method, "qr-size-proxy-v2");
});
