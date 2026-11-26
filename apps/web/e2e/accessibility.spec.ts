import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function audit(page: Page) {
  const report = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(
    report.violations.map((v) => ({
      rule: v.id,
      targets: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
}

test("the weekly spread and its single-page layout pass WCAG A/AA checks", async ({
  page,
}) => {
  await page.goto("/#reports");
  const weekly = page.locator(".wr-page-week");
  const daily = page.locator(".wr-page-daily");
  await expect(
    page.getByRole("heading", { name: "小禾的用眼周报" }),
  ).toBeVisible();
  for (const width of [1360, 960, 959, 390, 320]) {
    await page.setViewportSize({ width, height: width >= 960 ? 920 : 844 });
    const left = await weekly.boundingBox();
    const right = await daily.boundingBox();
    if (width >= 960) expect(right!.y).toBeCloseTo(left!.y);
    else expect(right!.y).toBeGreaterThanOrEqual(left!.y + left!.height - 1);
    if (width === 320) await page.locator(".wr-sources summary").click();
    if ([1360, 390, 320].includes(width)) await audit(page);
  }
});

test("keyboard access and WCAG A/AA automated checks for the product page and three parent views on a narrow screen", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/showcase");
  await expect(
    page.getByRole("heading", { level: 1, name: /智能学习眼镜/ }),
  ).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "LumiRead 产品首页" }),
  ).toBeFocused();
  await audit(page);
  await page.getByRole("button", { name: "点镜片，试试三种戴法" }).click();
  await expect(
    page.getByRole("heading", { name: "三种佩戴方式" }),
  ).toBeFocused();
  await audit(page);
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "查看价格" }).click();
  await page.getByRole("link", { name: "进入学习助手" }).first().click();
  await expect(
    page.getByRole("heading", { name: "选择演示账号" }),
  ).toBeVisible();
  await audit(page);
  await page.getByRole("button", { name: "登录 B" }).click();
  await expect(
    page.getByRole("heading", { name: "六维学习画像" }),
  ).toBeVisible();
  await audit(page);
  for (const tab of ["护眼观察", "作业批改", "巩固与错题"]) {
    await page.getByRole("button", { name: tab }).click();
    await audit(page);
  }
  await page.goto("/federated");
  await expect(
    page.getByRole("heading", { name: "训练过程回放" }),
  ).toBeVisible();
  await audit(page);
});
