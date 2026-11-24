export type View = "environment" | "user";
export type Point = { x: number; y: number };
export const VICTORY_SCORE = 0.7;

type WorldPoint = Point & { z: number };
function span(a: WorldPoint, b: WorldPoint) {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
}

// Only corroborate the recognizer's own Victory prediction. World landmarks
// keep the finger lengths independent of the phone's orientation and distance.
export function confirmedVictory(
  label: string | undefined,
  score: number,
  hand?: WorldPoint[],
) {
  if (label !== "Victory" || !Number.isFinite(score) || score < 0.5)
    return false;
  if (score >= VICTORY_SCORE) return true;
  if (hand?.length !== 21) return false;
  const palm = span(hand[5], hand[17]);
  if (palm <= 0 || span(hand[8], hand[12]) < palm * 0.5) return false;
  const straightness = (base: number) => {
    const [a, b, c, d] = hand.slice(base, base + 4);
    return span(a, d) / (span(a, b) + span(b, c) + span(c, d));
  };
  return (
    straightness(5) >= 0.9 &&
    straightness(9) >= 0.9 &&
    straightness(13) <= 0.85 &&
    straightness(17) <= 0.85
  );
}

// An observation gap cannot count toward either the hold or the release.
export class VictoryShutter {
  private since: number | null = null;
  private away: number | null = null;
  private last = -Infinity;
  locked = false;

  observe(victory: boolean, now: number) {
    if (now - this.last > 550 || now <= this.last) {
      this.since = null;
      this.away = null;
    }
    this.last = now;
    if (!victory) {
      this.since = null;
      this.away ??= now;
      if (now - this.away >= 450) this.locked = false;
      return { fire: false, progress: 0 };
    }
    this.away = null;
    this.since ??= now;
    const progress = Math.min(1, (now - this.since) / 1500);
    const fire = progress === 1 && !this.locked;
    if (fire) this.locked = true;
    return { fire, progress };
  }
}

export function eyeTilt(
  a: Point | undefined,
  b: Point | undefined,
  width: number,
  height: number,
) {
  if (!a || !b || !width || !height) return null;
  const dx = (a.x - b.x) * width,
    dy = (a.y - b.y) * height;
  if (Math.hypot(dx, dy) < 16) return null;
  const deg = (Math.atan2(dy, dx) * 180) / Math.PI;
  return Math.round((((deg + 270) % 180) - 90) * 10) / 10;
}

