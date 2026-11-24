import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("all three federated runs match their frozen round logs and selected checkpoints", async ({
  page,
}) => {
  const lines = await readFile(
    "../../artifacts/federated/rounds.jsonl",
    "utf8",
  );
  const recorded = lines
    .trim()
    .split("\n")
    .map((s) => JSON.parse(s));
  const report = await (await page.request.get("/api/v1/federated")).json();
  await page.goto("/federated");
  const seedSelector = page.getByLabel("训练种子");
  const slider = page.getByLabel("回放轮次");
  await expect(seedSelector).toHaveValue(String(report.selected.seed));
  await expect(slider).toHaveValue(String(report.selected.round));
  let open = false;
  for (const run of report.runs) {
    await seedSelector.selectOption(String(run.seed));
    await expect(slider).toHaveValue(String(run.best_round));
    const details = page.locator("details").filter({ hasText: "查看每轮记录" });
    open = await details.evaluate((el: HTMLDetailsElement) => el.open);
    if (!open) await details.locator("summary").click();
    const rows = details.locator("tbody tr");
    await expect(rows).toHaveCount(run.rounds.length);
    const visible = await rows.evaluateAll((rs) =>
      rs.map((r) =>
        Array.from(
          r.querySelectorAll("td,th"),
          (el) => el.textContent?.trim() || "",
        ),
      ),
    );
    const reference = recorded.filter((r) => r.seed === run.seed);
    expect(reference).toHaveLength(60);
    for (const [i, r] of reference.entries()) {
      expect(Number(visible[i][1].replace(/,/g, ""))).toBe(r.client_count);
      expect(Number(visible[i][2].replace(/,/g, ""))).toBe(r.target_count);
      expect(Number(visible[i][4])).toBeCloseTo(r.validation_auc, 3);
    }
    const sample = reference[6];
    await page
      .getByRole("button", { name: "查看第 7 轮", exact: true })
      .click();
    await expect(slider).toHaveValue("7");
    const values = await page.locator(".round-values dd").allTextContents();
    expect(values.map((v) => Number(v.replace(/,/g, "")))).toEqual([
      sample.client_count,
      sample.target_count,
      sample.logical_download_bytes,
      sample.logical_upload_bytes,
    ]);
    await page.getByRole("button", { name: "从第 1 轮播放" }).click();
    await expect(slider).toHaveValue("1");
    await page.getByRole("button", { name: "暂停回放" }).click();
  }
});

test("previously shared product links enter the current three-account notebook", async ({
  page,
}) => {
  await page.goto("/showcase?room=earlier-room");
  await page.getByRole("link", { name: "查看价格" }).click();
  await page.getByRole("link", { name: "进入学习助手" }).first().click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("button", { name: "登录 B" })).toBeVisible();
});

test("notebook overview follows the account's measured alert through recovery", async ({
  page,
}) => {
  await page.goto("/app");
  await page.getByRole("button", { name: "登录 B" }).click();
  const summary = page.getByRole("region", { name: "最近护眼提醒" });
  await summary.getByRole("button", { name: "查看护眼记录" }).click();
  const replay = page.getByRole("region", { name: "公开传感器记录回放" });
  await replay.getByLabel("回放速度").selectOption("4");
  await replay.getByRole("button", { name: "重播", exact: true }).click();
  await page.getByRole("button", { name: "学习概览" }).click();
  await expect(summary).toContainText("工作距离偏近 · 提醒中", {
    timeout: 10000,
  });
  await expect(summary).toContainText("09:10:13 触发 · 16 cm");
  await expect(summary).toContainText("09:10:28 解除", { timeout: 7000 });
  await expect(summary).toContainText("工作距离偏近 · 已解除");
  await page.reload();
  await expect(summary).toContainText("09:10:28 解除");
  await page.getByLabel("切换账号").selectOption("A");
  await expect(summary).toContainText("尚未开始回放");
  await expect(summary).not.toContainText("09:10:13");
});
