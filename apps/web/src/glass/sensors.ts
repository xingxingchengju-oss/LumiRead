export type Point = { x: number; y: number };
export const MARKER = "LumiRead:paper:v1:50mm";
export function qrScale(corners: Point[], width: number, height: number) {
  if (
    corners.length !== 4 ||
    !Number.isFinite(width) ||
    width <= 0 ||
    !Number.isFinite(height) ||
    height <= 0 ||
    corners.some(
      ({ x, y }) =>
        !Number.isFinite(x) ||
        !Number.isFinite(y) ||
        x < 0 ||
        x > width ||
        y < 0 ||
        y > height,
    )
  )
    return null;
  const sides = corners.map((a, i) => {
    const b = corners[(i + 1) % 4];
    return Math.hypot(a.x - b.x, a.y - b.y);
  });
  if (Math.min(...sides) < 22 || Math.min(...sides) / Math.max(...sides) < 0.85)
    return null;
  const center = corners.reduce(
    (p, q) => ({ x: p.x + q.x / 4, y: p.y + q.y / 4 }),
    { x: 0, y: 0 },
  );
  if (
    Math.abs(center.x / width - 0.5) > 0.32 ||
    Math.abs(center.y / height - 0.5) > 0.32
  )
    return null;
  const d1 = Math.hypot(
    corners[0].x - corners[2].x,
    corners[0].y - corners[2].y,
  );
  const d2 = Math.hypot(
    corners[1].x - corners[3].x,
    corners[1].y - corners[3].y,
  );
  if (Math.min(d1, d2) / Math.max(d1, d2) < 0.88) return null;
  return sides.reduce((a, b) => a + b, 0) / (4 * Math.max(width, height));
}

type TrackOptics = {
  width?: number;
  height?: number;
  zoom?: number;
  horizontalFieldOfView?: number;
  verticalFieldOfView?: number;
  diagonalFieldOfView?: number;
};
export function distanceCm(
  scale: number | null,
  width: number,
  height: number,
  optics: TrackOptics = {},
) {
  if (
    !scale ||
    !Number.isFinite(scale) ||
    scale <= 0 ||
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  )
    return null;
  // A reported horizontal/vertical FOV applies to the track axes. Rotated
  // video frames swap those axes. A capabilities range is not a measured FOV.
  const rotated =
    optics.width &&
    optics.height &&
    optics.width > optics.height !== width > height;
  const diagonal = Math.hypot(width, height);
  let focalPx: number | undefined;
  for (const [pixels, degrees] of [
    [rotated ? height : width, optics.horizontalFieldOfView],
    [rotated ? width : height, optics.verticalFieldOfView],
    [diagonal, optics.diagonalFieldOfView],
  ] as const) {
    if (
      degrees !== undefined &&
      Number.isFinite(degrees) &&
      degrees > 0 &&
      degrees < 179
    ) {
      focalPx = pixels / (2 * Math.tan((degrees * Math.PI) / 360));
      break;
    }
  }
  const long = Math.max(width, height),
    short = Math.min(width, height);
  if (focalPx === undefined) {
    // Apple lists the iPhone 16 Pro Max 1× Fusion main camera at 24 mm
    // full-frame equivalent. Assume a central crop of a native 4:3 frame,
    // no stabilization crop, and a fronto-parallel paper marker. The 35 mm
    // reference diagonal is hypot(36,24) mm. Digital zoom breaks this proxy.
    if (
      optics.zoom !== undefined &&
      (!Number.isFinite(optics.zoom) || Math.abs(optics.zoom - 1) > 0.02)
    )
      return null;
    const nativeDiagonal = 5 * Math.max(long / 4, short / 3);
    focalPx = (24 * nativeDiagonal) / Math.hypot(36, 24);
  }
  const blackSidePx = scale * long;
  return Math.round((10 * 5 * focalPx) / blackSidePx) / 10;
}

// Rec.709 luma of the central 50% of the frame, sampled on a regular grid.
export function centerLuma(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
) {
  let sum = 0,
    n = 0;
  for (let y = Math.floor(height / 4); y < (3 * height) / 4; y += 4) {
    for (let x = Math.floor(width / 4); x < (3 * width) / 4; x += 4) {
      const i = 4 * (width * y + x);
      sum +=
        0.2126 * pixels[i] + 0.7152 * pixels[i + 1] + 0.0722 * pixels[i + 2];
      n++;
    }
  }
  return n ? Math.round(sum / n) : null;
}

const specifications = {
  distance_cm: ["cm", "estimated", "qr-size-proxy-v2"],
  brightness: ["level", "measured", "center-luma-rec709-v1"],
  reading_seconds: ["s", "measured", "foreground-reading-clock-v1"],
} as const;

export type Metric = keyof typeof specifications;
export function sample(
  metric: Metric,
  value: number | null,
  simulated = false,
) {
  const [unit, kind, method] = specifications[metric];
  return {
    metric,
    value,
    unit,
    value_kind: simulated ? "simulated" : kind,
    input_mode: simulated ? "accelerated" : "live",
    method: simulated ? "demo-clock-300x-v1" : method,
    quality: value === null ? "missing" : "ok",
    observed_at: Date.now() / 1000,
    calibration_id: null,
  };
}
export type Sample = ReturnType<typeof sample>;
export function clockText(seconds: number) {
  return Math.floor(seconds / 60) + " 分 " + (Math.floor(seconds) % 60) + " 秒";
}
