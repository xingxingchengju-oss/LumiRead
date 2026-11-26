import { test, expect } from "@playwright/test";

test("the inward eye module opens on both the physical model and its projected poster", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const renderer of ["webgl", "poster"]) {
    if (renderer === "poster") {
      await page.goto("about:blank");
      await page.route("**/products/frame.glb", (r) => r.abort());
    }
    await page.goto("/showcase#construction");
    const stage = page.getByRole("region", { name: "交互眼镜模型" });
    await expect(stage).toHaveAttribute("data-renderer", renderer);
    await stage.getByRole("button", { name: "内向眼动模组热点" }).click();
    await expect(
      page.getByRole("heading", { name: "内向眼动模组" }),
    ).toBeFocused();
    await expect(
      page.getByRole("link", { name: "观看研究样片" }),
    ).toHaveAttribute("href", "/#reading");
    await expect(page.getByText(/Meta RitW 成人研究录像/)).toBeVisible();
    if (renderer === "poster")
      await expect(stage.getByRole("img")).toHaveAttribute(
        "src",
        "/products/frame-eye.webp",
      );
    await page.keyboard.press("Escape");
    await expect(
      stage.getByRole("button", { name: "内向眼动模组热点" }),
    ).toBeFocused();
  }
});

test("the clip has an independent cutaway, parts directory and capability column", async ({
  page,
}) => {
  const models: string[] = [];
  page.on("request", (r) => {
    const url = new URL(r.url());
    if (url.pathname.endsWith(".glb")) models.push(url.pathname);
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/showcase");
  const stage = page.getByRole("region", { name: "交互眼镜模型" });
  await expect(stage).toHaveAttribute("data-renderer", "webgl");
  expect(models).toEqual(["/products/frame.glb"]);
  const before = await stage.boundingBox();
  await page.getByRole("link", { name: "佩戴方式", exact: true }).click();
  await expect
    .poll(() =>
      stage
        .locator(".lr-poster-art img")
        .evaluate((el) => (el as HTMLImageElement).naturalWidth),
    )
    .toBeGreaterThan(0);
  // Hold both new assets. The previously decoded product must still be available.
  let release!: () => void;
  const waiting = new Promise<void>((done) => {
    release = done;
  });
  await page.route(/\/products\/clip\.(glb|webp)$/, async (route) => {
    await waiting;
    await route.continue();
  });
  try {
    await page.getByRole("button", { name: "夹片款", exact: true }).click();
    await expect(stage).toHaveAttribute("data-renderer", "loading");
    await expect(stage).toHaveAttribute("aria-busy", "true");
    const heroImage = stage.getByRole("img");
    await expect(heroImage).toBeVisible();
    expect(
      await heroImage.evaluate((el) => (el as HTMLImageElement).naturalWidth),
    ).toBeGreaterThan(0);
  } finally {
    release();
  }
  await expect(stage).toHaveAttribute("data-renderer", "webgl");
  expect(models).toContain("/products/clip.glb");
  await page
    .getByRole("navigation", { name: "产品导航" })
    .getByRole("link", { name: "佩戴结构" })
    .click();
  expect(await stage.boundingBox()).toEqual(before);
  await stage.getByRole("button", { name: "夹片内部热点" }).click();
  await expect(page.getByRole("heading", { name: "夹片内部" })).toBeFocused();
  await page.getByRole("button", { name: "部件目录" }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("button", { name: "内向眼动模组" }),
  ).toHaveCount(0);
  await expect(
    dialog.getByRole("button", { name: "六轴惯性传感器" }),
  ).toHaveCount(0);
  await expect(
    dialog.getByRole("button", { name: "顶部功能按键" }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "充电触点" }).click();
  await expect(page.getByText(/夹片底部的金属触点/)).toBeVisible();
  await page.getByRole("link", { name: "查看价格" }).click();
  const table = page.getByRole("table", { name: "两款眼镜功能对照" });
  await expect(
    table.getByRole("columnheader", { name: "智能夹片" }),
  ).toBeVisible();
  const reading = table.getByRole("row", { name: /阅读识别设计/ });
  await expect(reading.getByRole("cell").first()).toHaveText("眼动与头动");
  await expect(reading.getByRole("cell").last()).toHaveText("—");
});

test("mobile chapter navigation reaches the light and capture demonstrations", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/showcase");
  const nav = page.getByRole("navigation", { name: "产品导航" });
  const toggle = nav.getByRole("button", { name: /浏览章节/ });
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await page.mouse.click(12, 68);
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await nav.getByRole("link", { name: "学习感知" }).click();
  await expect(toggle).toHaveAccessibleName("浏览章节，当前为学习感知");
  await page.getByRole("button", { name: "环境光传感器", exact: true }).click();
  await page.getByRole("button", { name: "调暗光线" }).click();
  await expect(page.getByText("佩戴处偏暗 · 示意")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "作业摄像头", exact: true }).click();
  await page.getByRole("button", { name: "模拟拍摄" }).click();
  await expect(page.getByText("拍摄指示灯亮起")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "进入学习助手" }),
  ).toHaveAttribute("href", "/app");
  await nav.getByRole("link", { name: "查看价格" }).click();
  await expect(page.getByRole("link", { name: "进入学习助手" })).toBeInViewport(
    { ratio: 0.95 },
  );
});
