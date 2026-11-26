import { test, expect, type CDPSession, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const frame = ["frame-touch", "frame-board", "frame-battery", "frame-eye"];
const clip = ["clip-clamp", "clip-button", "clip-inside", "clip-charge"];
const guide = (page: Page) =>
  page.getByRole("region", { name: "佩戴结构导览" });

function distance(page: Page, id: string, fraction = 0) {
  return page.locator("#" + id).evaluate((el, f) => {
    const rect = el.getBoundingClientRect();
    return (
      rect.top -
      parseFloat(getComputedStyle(el).scrollMarginTop) +
      rect.height * f
    );
  }, fraction);
}
async function wheel(page: Page, id: string, fraction = 0) {
  await page.mouse.wheel(0, Math.round(await distance(page, id, fraction)));
}
async function expectShot(page: Page, shot: string) {
  const tour = guide(page);
  await expect(tour).toHaveAttribute("data-view", shot);
  await expect(tour).toHaveAttribute("aria-busy", "false");
  await expect(tour.locator(".lr-shot-current")).toHaveAttribute(
    "src",
    "/products/" + shot + ".webp",
  );
}
async function touchScroll(
  page: Page,
  touch: CDPSession,
  id: string,
  fraction = 0,
) {
  // Lift after a brief hold to settle the native gesture without an inertial fling.
  const { width, height } = page.viewportSize()!;
  const x = width * 0.42;
  for (let swipe = 0; swipe < 4; swipe++) {
    const left = await distance(page, id, fraction);
    if (Math.abs(left) < 8) break;
    const sign = Math.sign(left);
    const y = height * (sign > 0 ? 0.85 : 0.17);
    const travel = sign * Math.min(height * 0.68, Math.abs(left) + 15);
    await touch.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x, y }],
    });
    let end = y;
    for (let i = 1; i <= 8; i++) {
      end = y - (travel * i) / 8;
      await touch.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ x, y: end }],
      });
    }
    await page.waitForTimeout(140);
    await touch.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ x, y: end - sign }],
    });
    await touch.send("Input.dispatchTouchEvent", {
      type: "touchEnd",
      touchPoints: [],
    });
    await page.evaluate(
      () =>
        new Promise<void>((resolve) => requestAnimationFrame(() => resolve())),
    );
    if (
      id === "specifications" &&
      (await page.getByRole("heading", { name: "型号与价格" }).isVisible())
    )
      break;
  }
}

for (const [sku, views] of [
  ["frame", frame],
  ["clip", clip],
] as const) {
  test(
    sku +
      " wheel tour holds the camera, reverses every act and exits at prices",
    async ({ page }) => {
      await page.goto("/showcase#explore");
      if (sku === "clip")
        await page.getByRole("button", { name: "夹片款", exact: true }).click();
      await page.mouse.move(300, 300);
      await wheel(page, "construction", 0.01);
      await expectShot(page, views[0]);
      const locator = guide(page).locator(".lr-locator-art img");
      const fixed = await locator.boundingBox();
      let right = 0;
      for (const i of [1, 2, 3, 2, 1, 0]) {
        if (views[i] === "frame-board" || views[i] === "clip-inside") {
          await wheel(page, "construction-" + (i + 1), 0.1);
          await expectShot(page, sku + "-closed");
        }
        await wheel(page, "construction-" + (i + 1), 0.48);
        await expectShot(page, views[i]);
        await expect(guide(page)).toHaveAttribute("data-step", String(i + 1));
        expect(await locator.boundingBox()).toEqual(fixed);
        const spot = await guide(page)
          .locator(".lr-locator-target")
          .boundingBox();
        if (views[i] === "frame-board") {
          right = spot!.x;
          await expect(guide(page).locator(".lr-guide-note")).toHaveText([
            "天线",
            "处理器",
            "惯性传感器",
          ]);
        }
        if (views[i] === "frame-battery") {
          expect(spot!.x - right).toBeGreaterThan(fixed!.width * 0.4);
          await expect(guide(page).locator(".lr-guide-note")).toHaveText([
            "电池",
            "充电触点",
          ]);
        }
        if (views[i] === "clip-inside")
          await expect(guide(page).locator(".lr-guide-note")).toHaveText([
            "主板",
            "电池",
            "天线窗口",
          ]);
        if (views[i] === "frame-eye")
          await expect(
            guide(page).getByRole("link", { name: "观看研究样片" }),
          ).toHaveAttribute("href", "/#reading");
      }
      await wheel(page, "specifications");
      await expect(
        page.getByRole("heading", { name: "型号与价格" }),
      ).toBeVisible();
      await expect(guide(page)).toHaveCount(0);
    },
  );

  test(
    sku +
      " touch tour visits four acts in either direction and continues to prices",
    async ({ browser, baseURL }) => {
      test.setTimeout(60000);
      const phone = await browser.newContext({
        baseURL,
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
        deviceScaleFactor: 2,
      });
      try {
        const page = await phone.newPage();
        const touch = await phone.newCDPSession(page);
        await page.goto("/showcase#explore");
        await page
          .getByRole("button", {
            name: sku === "clip" ? "夹片款" : "无镜片",
            exact: true,
          })
          .tap();
        for (const i of [0, 1, 2, 3, 2, 1, 0, 1, 2, 3]) {
          await touchScroll(page, touch, "construction-" + (i + 1), 0.45);
          await expectShot(page, views[i]);
          await expect(
            guide(page).locator(".lr-locator-art img"),
          ).toHaveAttribute(
            "src",
            sku === "clip"
              ? "/products/clip.webp"
              : "/products/frame-open.webp",
          );
        }
        await touchScroll(page, touch, "specifications");
        await expect(
          page.getByRole("heading", { name: "型号与价格" }),
        ).toBeVisible();
      } finally {
        await phone.close();
      }
    },
  );
}

test("a slow decode holds the current photograph and cannot overwrite a later wheel destination", async ({
  page,
}) => {
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/products/frame-closed.webp", async (route) => {
    await held;
    await route.continue();
  });
  try {
    await page.goto("/showcase#construction");
    await expectShot(page, "frame-touch");
    await wheel(page, "construction-2", 0.09);
    await expect(guide(page)).toHaveAttribute("aria-busy", "true");
    await expect(
      guide(page).getByRole("heading", { name: "手指碰到哪里" }),
    ).toBeVisible();
    await expect(guide(page).locator(".lr-shot-current")).toHaveAttribute(
      "src",
      "/products/frame-touch.webp",
    );
    await wheel(page, "construction-4", 0.4);
    await expectShot(page, "frame-eye");
    const downloaded = page.waitForResponse("**/products/frame-closed.webp");
    release();
    await (await downloaded).finished();
    await expect(guide(page).locator(".lr-shot-previous")).toHaveCount(0);
    await expectShot(page, "frame-eye");
    await wheel(page, "construction-2", 0.09);
    await expectShot(page, "frame-closed");
  } finally {
    release();
  }
});

test("keyboard scrolling, reduced motion and optional details restore the exact guide position", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/showcase#construction");
  await expectShot(page, "frame-touch");
  const surface = page.getByRole("region", { name: "交互眼镜模型" });
  await expect(surface).toHaveAttribute("data-renderer", "webgl");
  await surface.focus();
  const start = await page.evaluate(() => scrollY);
  await page.keyboard.press("ArrowDown");
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(start);
  const advance = page.getByRole("link", { name: "下一幕" });
  await advance.focus();
  await page.keyboard.press("Enter");
  await expectShot(page, "frame-closed");
  const open = page.getByRole("link", { name: "查看内部" });
  await expect(open).toBeFocused();
  await page.keyboard.press("Enter");
  await expectShot(page, "frame-board");
  expect(
    await guide(page)
      .locator(".lr-shot-current")
      .evaluate((el) => el.getAnimations().length),
  ).toBe(0);
  await page.keyboard.press("Enter");
  await expectShot(page, "frame-battery");
  const bookmark = await page.evaluate(() => scrollY);
  const pin = guide(page).getByRole("button", { name: "右镜腿热点" });
  await pin.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "右镜腿" })).toBeFocused();
  await wheel(page, "construction-4", 0.4);
  await expect
    .poll(() => page.evaluate(() => scrollY))
    .toBeGreaterThan(bookmark + 50);
  await page.keyboard.press("Escape");
  await expectShot(page, "frame-battery");
  await expect(pin).toBeFocused();
  expect(await page.evaluate(() => scrollY)).toBeCloseTo(bookmark, 0);
  const picker = page.getByRole("button", { name: "部件目录" });
  await picker.focus();
  await page.keyboard.press("Enter");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "可充电电池" })
    .press("Enter");
  await expect(page.getByRole("heading", { name: "可充电电池" })).toBeFocused();
  await page.getByRole("button", { name: "返回全貌" }).press("Enter");
  await expect(picker).toBeFocused();
  await expectShot(page, "frame-battery");
  await page.getByRole("link", { name: "查看价格" }).press("Enter");
  await expect(page.getByRole("heading", { name: "型号与价格" })).toBeVisible();
});

test("both guides remain legible and navigable on a 320px screen with WebGL unavailable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const context = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (kind, ...args) {
      return kind.startsWith("webgl")
        ? null
        : Reflect.apply(context, this, [kind, ...args]);
    };
  });
  await page.goto("/showcase#construction");
  await expect(page.locator(".lr-surface")).toHaveAttribute(
    "data-renderer",
    "poster",
  );
  for (const views of [frame, clip]) {
    if (views === clip) {
      await wheel(page, "explore");
      await page.getByRole("button", { name: "夹片款", exact: true }).click();
    }
    for (const [i, view] of views.entries()) {
      await wheel(page, "construction-" + (i + 1), 0.5);
      await expectShot(page, view);
      const tour = guide(page);
      await expect(tour.getByRole("heading")).toBeInViewport({ ratio: 1 });
      await expect(tour.locator(".lr-guide-description")).toBeInViewport({
        ratio: 1,
      });
      for (const label of await tour.locator(".lr-guide-note").all())
        await expect(label).toBeInViewport({ ratio: 1 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(320);
      if (view === "frame-board" || view === "clip-inside") {
        const result = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();
        expect(
          result.violations.map((v) => ({
            id: v.id,
            targets: v.nodes.map((n) => n.target),
          })),
        ).toEqual([]);
      }
      if (view === "frame-eye") {
        for (const [width, height] of [
          [320, 480],
          [568, 320],
          [320, 568],
        ]) {
          await page.setViewportSize({ width, height });
          await wheel(page, "construction-4", 0.5);
          await expectShot(page, view);
          const sample = await tour
            .getByRole("link", { name: "观看研究样片" })
            .boundingBox();
          const footer = await page.locator(".lr-stage-foot").boundingBox();
          expect(sample!.y + sample!.height).toBeLessThanOrEqual(footer!.y);
          await expect(tour.locator(".lr-locator-art img")).toBeInViewport({
            ratio: 1,
          });
        }
      }
    }
    await wheel(page, "specifications");
    await expect(
      page.getByRole("heading", { name: "型号与价格" }),
    ).toBeVisible();
  }
});
