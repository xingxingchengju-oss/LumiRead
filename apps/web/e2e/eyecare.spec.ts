import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import type { components } from "../../../packages/contracts/types";

test("reading timeline and controls work without a licensed video", async ({
  page,
}) => {
  await page.route("**/eye-care/preview/*", (route) =>
    route.fulfill({ status: 404 }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "家庭护眼手册" }),
  ).toBeVisible();
  await expect(page.getByText(/本机尚未下载授权录像/)).toBeVisible();
  await page.getByRole("slider").focus();
  await page.keyboard.press("End");
  await expect(page.getByRole("button", { name: "重播" })).toBeVisible();
  await expect(page.locator(".ec-readout dd").last()).toHaveText("2:23");
  await page.getByRole("button", { name: "重播" }).click();
  await expect(page.getByRole("button", { name: "暂停" })).toBeVisible();
  await page.getByRole("button", { name: "暂停" }).click();
  await page.getByLabel("测试片段").selectOption({ index: 1 });
  await expect(page.getByText(/此片段提供逐秒识别时间轴/)).toBeVisible();
  await expect(page.locator(".ec-readout dd").last()).toHaveText("0:00");
  await expect(page.getByRole("row", { name: /Meta 官方模型/ })).toContainText(
    "0.782",
  );
});

test("authorized preview follows the original sequence clock, seek and pause", async ({
  page,
}) => {
  const research: components["schemas"]["Research"] = await (
    await page.request.get("/api/v1/eye-care/research")
  ).json();
  test.skip(
    !existsSync(
      "../../.cache/ritw/sequences/" + research.showcase + "/preview.mp4",
    ),
    "Acquire the licensed preview with make ritw-preview.",
  );
  await page.goto("/");
  const video = page.locator("video"),
    slider = page.getByRole("slider");
  const time = () => video.evaluate((v: HTMLVideoElement) => v.currentTime);
  await expect
    .poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState))
    .toBeGreaterThanOrEqual(2);
  const beginning = Number(await slider.getAttribute("min"));
  await expect.poll(time).toBeCloseTo(beginning, 0);
  await page.getByRole("button", { name: "播放", exact: true }).click();
  await expect.poll(time).toBeGreaterThan(beginning + 0.8);
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  await expect
    .poll(() => video.evaluate((v: HTMLVideoElement) => v.paused))
    .toBeTruthy();
  await expect
    .poll(async () =>
      Math.abs((await time()) - Number(await slider.inputValue())),
    )
    .toBeLessThan(0.6);
  await slider.focus();
  await page.keyboard.press("End");
  await expect
    .poll(time)
    .toBeCloseTo(Number(await slider.getAttribute("max")), 0);
});

test("measured alerts, simulated break and source-specific reports", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/eye-care#sensors");
  await page.getByRole("slider").focus();
  await page.keyboard.press("End");
  await expect(
    page.getByRole("status").filter({ hasText: "09:45:27" }),
  ).toContainText("09:45:37 解除");
  await page.screenshot({
    path: test.info().outputPath("sensors-mobile.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1360, height: 920 });
  await page.screenshot({
    path: test.info().outputPath("sensors-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel("手动选择场景").selectOption("computer");
  await expect(page.getByText(/截至当前读数，尚未触发提醒/)).toBeVisible();
  await page.getByRole("link", { name: "读写与休息" }).click();
  await page.getByRole("button", { name: "规则演示时间轴" }).click();
  await page.getByLabel("学习场景").selectOption("electronic");
  await page.getByRole("button", { name: "开始计时" }).click();
  await page.getByRole("button", { name: "推进 30 分钟" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "请休息" }),
  ).toContainText("30:00");
  await page.getByRole("button", { name: "开始休息" }).click();
  await page.getByRole("button", { name: "推进 10 分钟" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "已完成" }),
  ).toContainText("40:00");
  await page.getByRole("button", { name: "实际手动计时" }).click();
  await expect(page.getByRole("button", { name: "开始计时" })).toBeVisible();
  await page.getByRole("link", { name: "家长报告" }).click();
  await expect(page.getByText(/同一名成年参与者/)).toBeVisible();
  await page.getByRole("button", { name: "模拟学生周报" }).click();
  await expect(page.getByText("461:00")).toBeVisible();
  await expect(page.getByText(/虚构的七天家庭记录/)).toBeVisible();
  await page.getByLabel("趋势指标").selectOption("dim");
  await page.getByRole("button", { name: /11-16/ }).click();
  await expect(page.getByRole("heading", { name: /11-16 日报/ })).toBeVisible();
  await expect(page.getByLabel("趋势指标")).toHaveValue("dim");
  await page.getByRole("button", { name: "RitW 阅读记录" }).click();
  await expect(page.getByText(/不同参与者/)).toBeVisible();
  await page.getByLabel("报告日期").fill("2026-11-18");
  await expect(page.getByText("无记录。当天用眼情况未知。")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("a manual writing session survives reload and recognizes a ten-minute break", async ({
  page,
}) => {
  await page.clock.install();
  await page.goto("/#timer");
  await page.getByLabel("学习场景").selectOption("writing");
  await page.getByRole("button", { name: "开始计时" }).click();
  await expect(page.locator(".ec-timer")).toContainText("读写中");
  await page.clock.fastForward(40 * 60 * 1000);
  await expect(
    page.getByRole("status").filter({ hasText: "请休息" }),
  ).toContainText("40:00");
  await page.reload();
  await expect(page.getByLabel("学习场景")).toHaveValue("writing");
  await expect(
    page.getByRole("status").filter({ hasText: "请休息" }),
  ).toHaveCount(1);
  await page.getByRole("button", { name: "开始休息" }).click();
  await page.clock.fastForward(600 * 1000);
  await expect(
    page.getByRole("status").filter({ hasText: "已完成" }),
  ).toBeVisible();
  await expect(page.locator(".ec-timer strong")).toHaveText("0:00");
  await page.getByRole("button", { name: "结束本段" }).click();
  await expect(page.getByRole("button", { name: "开始新一段" })).toBeVisible();
});
