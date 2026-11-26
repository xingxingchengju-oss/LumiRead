import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { existsSync } from "node:fs";
import type { components } from "../../../packages/contracts/types";

type Monitor = components["schemas"]["Monitor"];

test("two offline samples expose patch evidence even without a local MP4", async ({
  page,
}) => {
  await page.route("**/eye-care/preview/*", (route) =>
    route.fulfill({ status: 404 }),
  );
  await page.goto("/#timer");
  await expect(page).toHaveURL(/#reading$/);
  await expect(page.getByRole("heading", { name: "阅读监测" })).toBeVisible();
  await expect(
    page.getByRole("group", { name: "选择实拍录像" }).getByRole("button"),
  ).toHaveCount(2);
  await expect(page.getByRole("link", { name: "读写与休息" })).toHaveCount(0);
  await expect(page.getByText(/本机缺少这段授权录像/)).toBeVisible();
  const patches = page
    .getByRole("group", { name: "每七秒的预测和积分变化" })
    .getByRole("button");
  await patches.nth(2).click();
  await expect(patches.nth(2)).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("region", { name: "选中片段的判定依据" }),
  ).toContainText("眼动与头动投票");
  await page.getByRole("button", { name: "电子阅读", exact: true }).click();
  await expect(patches.first()).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".ec-score strong")).toContainText("0.00");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("both real videos drive seeking, evidence and scores on the source clock", async ({
  page,
}) => {
  const data: Monitor = await (
    await page.request.get("/api/v1/eye-care/monitor")
  ).json();
  test.skip(
    data.clips.some(
      (c) =>
        !existsSync("../../.cache/ritw/sequences/" + c.id + "/preview.mp4"),
    ),
    "Download both licensed previews with make ritw-preview.",
  );
  await page.goto("/#reading");
  for (const clip of data.clips) {
    await page
      .getByRole("button", {
        name: clip.kind === "paper" ? "纸质阅读" : "电子阅读",
        exact: true,
      })
      .click();
    const video = page.locator("video");
    const time = () => video.evaluate((v: HTMLVideoElement) => v.currentTime);
    await expect
      .poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState))
      .toBeGreaterThanOrEqual(2);
    await expect.poll(time).toBeCloseTo(clip.start, 0);
    await page.getByRole("button", { name: "播放", exact: true }).click();
    await expect.poll(time).toBeGreaterThan(clip.start + 0.3);
    await page.getByRole("button", { name: "暂停", exact: true }).click();
    const i = clip.patches.findIndex(
      (p) => clip.points[p.start - clip.start][2] > 0 && p.activity === "rest",
    );
    expect(i).toBeGreaterThan(-1);
    const patch = clip.patches[i];
    await page.locator(".ec-patches button").nth(i).click();
    await expect.poll(time).toBeCloseTo(patch.start, 0);
    await expect(page.locator(".ec-score strong")).toContainText(
      (clip.points[patch.start - clip.start][2] / data.ticks_per_point).toFixed(
        2,
      ),
    );
    await expect(page.locator(".ec-patch-detail")).toContainText("休息");
    await expect(page.locator(".ec-patch-detail")).toContainText(
      "阅读 " + patch.read_votes + " 票",
    );
    await page.screenshot({
      path: test.info().outputPath("monitor-" + clip.kind + ".png"),
      fullPage: true,
    });
    await page.getByRole("slider").focus();
    await page.keyboard.press("End");
    await expect.poll(time).toBeCloseTo(clip.end, 0);
  }
});

test("the offline score guide explains both verified breaks and returns keyboard focus", async ({
  page,
}) => {
  const external: string[] = [];
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") {
      external.push(url.href);
      return route.abort();
    }
    if (url.pathname.includes("/eye-care/preview/"))
      return route.fulfill({ status: 404 });
    return route.continue();
  });
  await page.goto("/#reading");
  const card = page.getByRole("button", { name: /用眼提醒积分.*了解积分/ });
  const guide = page.getByRole("dialog", { name: "了解用眼提醒积分" });
  for (const [kind, start, before, after, width] of [
    ["纸质阅读", "3:23", "3.00", "2.32", 1280],
    ["电子阅读", "3:09", "3.67", "2.99", 390],
  ] as const) {
    await page.setViewportSize({ width, height: 844 });
    await page.getByRole("button", { name: kind, exact: true }).click();
    const patch = page.getByRole("button", {
      name: new RegExp("^" + start + " 休息"),
    });
    await patch.click();
    await expect(card).toContainText(before);
    await card.focus();
    await page.keyboard.press("Enter");
    const context = guide.getByRole("region", { name: "当前片段计分" });
    await expect(context).toContainText(start);
    await expect(context).toContainText(before + " → " + after);
    await expect(context).toContainText("本段有 4 秒已过 10 秒缓冲");
    await expect(context).toContainText("每秒减 10/59 分");
    const rates = guide.getByRole("table", { name: "多久会提醒休息？" });
    await expect(
      rates.getByRole("row", { name: /平板阅读、\s*电脑阅读/ }),
    ).toContainText("+2/7 分");
    await expect(guide.locator("img")).toHaveJSProperty("naturalWidth", 1280);
    await page.screenshot({
      path: test.info().outputPath("guide-" + width + ".png"),
    });
    await guide.getByRole("button", { name: "阅读科普" }).click();
    await expect(guide.locator("summary").first()).toBeFocused();
    for (const title of ["专注看屏幕时", "什么时候抬头"]) {
      await guide.locator("summary").filter({ hasText: title }).click();
    }
    await expect(
      guide.getByRole("cell", { name: "38.40 ± 10.50" }),
    ).toBeVisible();
    await expect(guide.getByText(/20.8 次/)).toBeVisible();
    await expect(guide.getByText(/15 分钟以内/)).toBeVisible();
    await expect(guide.getByRole("link")).toHaveCount(4);
    if (width === 390) {
      await page.setViewportSize({ width: 320, height: 650 });
      expect(
        await guide.evaluate((el) =>
          Math.abs(el.getBoundingClientRect().bottom - innerHeight),
        ),
      ).toBeLessThan(2);
      expect(
        await guide
          .locator(".sg-content")
          .evaluate((el) => el.scrollWidth <= el.clientWidth),
      ).toBe(true);
      const audit = await new AxeBuilder({ page })
        .include(".ec-score-guide")
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(audit.violations.map((finding) => finding.id)).toEqual([]);
    }
    await page.keyboard.press("Escape");
    await expect(guide).toHaveCount(0);
    await expect(card).toBeFocused();
    await expect(card).toContainText(before);
    await expect(patch).toHaveAttribute("aria-pressed", "true");
  }
  expect(external).toEqual([]);
});

test("reading an article pauses a playing clip and restores its speed and source time", async ({
  page,
}) => {
  const { clips }: Monitor = await (
    await page.request.get("/api/v1/eye-care/monitor")
  ).json();
  const clip = clips[0];
  test.skip(
    !existsSync("../../.cache/ritw/sequences/" + clip.id + "/preview.mp4"),
    "Requires local preview.",
  );
  await page.goto("/#reading");
  const video = page.locator("video");
  const time = () => video.evaluate((v: HTMLVideoElement) => v.currentTime);
  await page.getByLabel("速度").selectOption("4");
  await page.getByRole("button", { name: "播放", exact: true }).click();
  await expect.poll(time).toBeGreaterThan(clip.start + 0.2);
  const card = page.getByRole("button", { name: /用眼提醒积分.*了解积分/ });
  await card.click();
  const guide = page.getByRole("dialog");
  await expect(guide).toBeVisible();
  await expect(video).toHaveJSProperty("paused", true);
  const stopped = await time();
  await guide.locator("summary").first().click();
  expect(await time()).toBe(stopped);
  await guide.getByRole("button", { name: "关闭积分说明" }).click();
  await expect(card).toBeFocused();
  await expect(video).toHaveJSProperty("playbackRate", 4);
  await expect.poll(time).toBeGreaterThan(stopped + 0.1);
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  const paused = await time();
  await card.click();
  await page.keyboard.press("Escape");
  await expect(video).toHaveJSProperty("paused", true);
  expect(await time()).toBe(paused);
});

test("weekly report opens from the handbook and reuses its published text offline", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1360, height: 920 });
  const external: string[] = [];
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).hostname === "127.0.0.1")
      return route.continue();
    external.push(route.request().url());
    return route.abort();
  });
  await page.goto("/eye-care#sensors");
  await expect(page).toHaveURL(/#reading$/);
  const nav = page.getByRole("navigation", { name: "护眼手册目录" });
  await expect(nav.getByRole("link")).toHaveCount(2);
  await nav.getByRole("link", { name: "家长报告" }).click();
  await expect(
    page.getByRole("heading", { name: "小禾的用眼周报" }),
  ).toBeVisible();
  await expect(
    page.getByText(/Meta Reading in the Wild 成人实拍/),
  ).toBeVisible();
  const totals = page.getByLabel("本周片段时长");
  for (const time of ["49分44秒", "18分31秒", "17分31秒"])
    await expect(totals).toContainText(time);
  await expect(page.getByText(/33秒\s*已识别为阅读/)).toBeVisible();
  await expect(page.getByText(/8分48秒/)).toBeVisible();
  await expect(
    page.getByRole("img", { name: /六类活动时长雷达图/ }).locator("svg"),
  ).toBeVisible();
  const days = page
    .getByRole("group", { name: "选择日期查看片段时长" })
    .getByRole("button");
  await expect(days).toHaveCount(7);
  await days.nth(2).hover();
  await expect(page.getByRole("status")).toContainText("阅读 3分22秒");
  await days.last().focus();
  await expect(page.getByRole("status")).toContainText("活动待定 4分15秒");
  const summary = await page.getByLabel("本周观察").locator("p").innerText();
  await expect(
    page.getByLabel("下周可以试试").getByRole("listitem"),
  ).toHaveCount(2);
  const sources = page.locator(".wr-sources");
  await sources.locator("summary").click();
  await expect(sources.locator("tbody tr")).toHaveCount(15);
  await page.reload();
  await expect(page.getByLabel("本周观察")).toContainText(summary);
  await expect(
    page.getByRole("heading", { name: "下周可以试试" }),
  ).toBeVisible();
  expect(external).toEqual([]);
  await page.screenshot({
    path: test.info().outputPath("weekly-desktop.png"),
    fullPage: true,
  });
});

test.describe("weekly report on a touch screen", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });
  test("tapping a day reveals its four durations", async ({ page }) => {
    await page.goto("/#reports");
    await page.getByRole("button", { name: /周日，记录/ }).tap();
    for (const duration of [
      "阅读 36秒",
      "视频 34秒",
      "暂停 1分45秒",
      "活动待定 4分15秒",
    ]) {
      await expect(page.getByRole("status")).toContainText(duration);
    }
    await expect(
      page.getByText(/Meta Reading in the Wild 成人实拍/),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "下周可以试试" }),
    ).toBeVisible();
    await expect(
      page.getByRole("img", { name: /六类活动时长雷达图/ }).locator("svg"),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: test.info().outputPath("weekly-mobile.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 320, height: 844 });
    await page.locator(".wr-sources summary").tap();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
      .toBe(320);
  });
});

test("a threshold reminder is announced once when replaying its source time", async ({
  page,
}) => {
  const data: Monitor = await (
    await page.request.get("/api/v1/eye-care/monitor")
  ).json();
  const clip = data.clips[0];
  test.skip(
    !existsSync("../../.cache/ritw/sequences/" + clip.id + "/preview.mp4"),
    "Requires local preview.",
  );
  clip.reminders = [clip.start + 2];
  for (const [i, point] of clip.points.entries()) {
    point[2] = i < 2 ? 99 * data.ticks_per_point : 100 * data.ticks_per_point;
  }
  await page.route("**/eye-care/monitor", (route) =>
    route.fulfill({ json: data }),
  );
  await page.goto("/#reading");
  await page.getByLabel("速度").selectOption("4");
  await page.getByRole("button", { name: "播放", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "提醒积分已达 100" }),
  ).toBeVisible();
  await expect(page.locator(".ec-score strong")).toContainText("100.00");
  await page.getByRole("button", { name: /用眼提醒积分.*了解积分/ }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "关闭积分说明" })
    .click();
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  await page.locator(".ec-patches button").first().click();
  await page.getByRole("button", { name: "播放", exact: true }).click();
  await expect
    .poll(() =>
      page.locator("video").evaluate((v: HTMLVideoElement) => v.currentTime),
    )
    .toBeGreaterThan(clip.start + 2.3);
  await expect(page.getByText(/提醒积分已达 100/)).toHaveCount(0);
});
