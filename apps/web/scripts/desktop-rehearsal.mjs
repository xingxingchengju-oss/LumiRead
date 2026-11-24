import { chromium, expect } from "@playwright/test";
import { existsSync } from "node:fs";
import { writeFile, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";
const root = fileURLToPath(new URL("../../../", import.meta.url));
const [baseURL, folder] = process.argv.slice(2);
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({
  executablePath:
    process.env.LUMIREAD_CHROME || (existsSync(chrome) ? chrome : undefined),
});
const ctx = await browser.newContext({
  baseURL,
  viewport: { width: 1440, height: 930 },
  recordVideo: { dir: folder, size: { width: 1440, height: 930 } },
});
const page = await ctx.newPage();
const video = page.video();
const start = Date.now();
const inspect = () => page.waitForTimeout(1400);
const report = {
  started: new Date(start).toISOString(),
  mode: "ordinary desktop · fresh isolated account database · real paid vision API",
  runs: [],
};
const button = (name) =>
  page.getByRole(
    "button",
    name.startsWith("登录 ")
      ? { name: new RegExp(name) }
      : { name, exact: true },
  );
const get = async (path) => {
  const res = await ctx.request.get("/api/v1" + path);
  assert.ok(res.ok(), path + " " + res.status());
  return res.json();
};
const profile = () => get("/demo/profile");
const homework = (sid) => get("/sessions/" + sid + "/homework");
const mastery = (lid) => get("/learners/" + lid + "/mastery");
const count = (p) => p.skills.reduce((n, s) => n + s.evidence_count, 0);
async function switchTo(key) {
  await page.getByLabel("切换账号").selectOption(key);
  await expect
    .poll(
      async () =>
        (await (await ctx.request.get("/api/v1/demo/profile")).json())
          .account_id,
    )
    .toBe(key);
  await expect(
    page.getByRole("heading", { name: "六维学习画像" }),
  ).toBeVisible();
  return profile();
}
async function replay(key, sid) {
  await button("护眼观察").click();
  const area = page.getByRole("region", { name: "公开传感器记录回放" });
  await area.getByLabel("回放速度").selectOption("10");
  await area.getByRole("button", { name: "播放", exact: true }).click();
  await area.getByRole("button", { name: "暂停", exact: true }).click();
  await area.getByRole("button", { name: "继续播放", exact: true }).click();
  await expect
    .poll(async () => (await get("/sessions/" + sid + "/clouclip")).status, {
      timeout: 15000,
    })
    .toBe("finished");
  const r = await get("/sessions/" + sid + "/clouclip");
  assert.ok(r.records.length === r.segment.total_samples);
  if (key === "A") assert.equal(r.events.length, 0);
  else {
    assert.equal(r.events.length, 1);
    assert.equal(r.events[0].metric, key === "B" ? "Dis" : "Lux");
    assert.ok(r.events[0].ended_at);
    await expect(area.getByText(/触发 · .*解除/)).toBeVisible();
  }
  return { segment: r.segment.id, samples: r.records.length, events: r.events };
}
async function upload(edition, sid, expected) {
  const file = resolve(root, "data/demo/worksheet-" + edition + ".png");
  await page.getByLabel("作业图片").setInputFiles(file);
  const receipt = page.waitForResponse(
    (r) => r.url().endsWith("/captures") && r.status() === 202,
  );
  await button("上传并批改").click();
  const { job_id, capture_id } = await (await receipt).json();
  await expect
    .poll(async () => (await get("/jobs/" + job_id)).status, {
      timeout: 140000,
      intervals: [400, 800],
    })
    .toBe("completed");
  const j = await get("/jobs/" + job_id);
  assert.equal(j.session_id, sid);
  assert.ok(["OpenAI", "DeepSeek"].includes(j.provider) && j.request_id);
  assert.deepEqual(
    j.result.map((it) => it.verdict),
    ["correct", expected],
  );
  assert.deepEqual(
    j.result.map((it) => it.student_answer.trim()),
    ["15", edition === "original" ? "8" : "5"],
  );
  const img = page.locator(
    'img[src="/api/v1/captures/' + capture_id + '/photo"]',
  );
  await img.scrollIntoViewIfNeeded();
  const article = page.locator("article.entry").filter({ has: img });
  await expect(
    article
      .getByText(expected === "incorrect" ? "× 有误" : "✓ 正确", {
        exact: true,
      })
      .first(),
  ).toBeVisible();
  const sha = createHash("sha256")
    .update(await readFile(file))
    .digest("hex");
  return {
    job: job_id,
    capture: capture_id,
    sha,
    request: j.request_id,
    provider: j.provider,
    model: j.model,
    seconds: j.latency,
    usage: j.usage,
    verdicts: j.result.map((i) => i.verdict),
    answers: j.result.map((i) => i.student_answer),
    article,
  };
}
try {
  for (let take = 1; take <= 2; take++) {
    const began = Date.now();
    await page.goto("/showcase");
    await inspect();
    await page.getByRole("button", { name: "点镜片，试试三种戴法" }).click();
    await button("夹片款").click();
    await page.getByRole("link", { name: "查看价格" }).click();
    await page.getByRole("link", { name: "进入学习助手" }).first().click();
    await button("登录 B").click();
    await expect(
      page.getByRole("heading", { name: "六维学习画像" }),
    ).toBeVisible();
    const b = await profile(),
      sid = b.session_id,
      lid = b.learner_id;
    const before = await mastery(lid),
      n = count(before);
    await inspect();
    assert.equal(before.device, "cpu");
    assert.equal(n, b.history.length);
    const care = { B: await replay("B", sid) };
    await button("作业批改").click();
    let { article: first, ...original } = await upload(
      "original",
      sid,
      "incorrect",
    );
    const mistake = first
      .locator("section")
      .filter({ has: page.locator(":scope > h4") })
      .filter({ has: button("收藏错题") })
      .first();
    await mistake.getByRole("button", { name: "小鹿分步讲解" }).click();
    await mistake
      .getByRole("button", { name: /下一步|查看解析/ })
      .first()
      .click();
    await inspect();
    await mistake.getByRole("button", { name: "收藏错题" }).click();
    const { article: second, ...revised } = await upload(
      "revised",
      sid,
      "correct",
    );
    assert.notEqual(original.request, revised.request);
    const after = await mastery(lid);
    assert.equal(count(after), n + 4);
    assert.notDeepEqual(after.skills, before.skills);
    await page.reload();
    await button("作业批改").click();
    await expect(page.locator("article.entry")).toHaveCount(2);
    assert.equal((await homework(sid)).length, 2);
    assert.equal((await get("/learners/" + lid + "/mistakes")).items.length, 1);
    first = page
      .locator("article.entry")
      .filter({
        has: page.locator(
          'img[src="/api/v1/captures/' + original.capture + '/photo"]',
        ),
      });
    const wrong = first
      .locator("section")
      .filter({ has: page.locator(":scope > h4") })
      .filter({ hasText: "× 有误" })
      .first();
    await wrong.getByRole("button", { name: "对照原图订正" }).click();
    await wrong.getByLabel("订正学生答案").fill("5");
    await wrong.getByRole("button", { name: "提交重新判分" }).click();
    await expect
      .poll(
        async () => (await get("/jobs/" + original.job)).result[1].revision,
        { timeout: 120000 },
      )
      .toBe(1);
    assert.equal(count(await mastery(lid)), n + 4);
    await button("学习概览").click();
    await expect(
      page.getByRole("heading", { name: "六维学习画像" }),
    ).toBeVisible();
    await button("巩固与错题").click();
    await expect(button("提交答案")).toHaveCount(2);
    const practice = page.locator("form.practice").first();
    await practice.getByLabel("你的答案").fill("0");
    await practice.getByRole("button", { name: "提交答案" }).click();
    await expect.poll(async () => count(await mastery(lid))).toBe(n + 5);
    for (const key of ["A", "C"]) {
      const other = await switchTo(key);
      assert.equal((await homework(other.session_id)).length, 0);
      assert.equal(
        count(await mastery(other.learner_id)),
        other.history.length,
      );
      assert.equal(
        (await ctx.request.get("/api/v1/jobs/" + original.job)).status(),
        404,
      );
      if (take === 1) care[key] = await replay(key, other.session_id);
    }
    await switchTo("B");
    assert.equal((await homework(sid)).length, 2);
    await page.getByRole("link", { name: /联邦/ }).first().click();
    await expect(
      page.getByRole("heading", { name: "联邦学习实验" }),
    ).toBeVisible();
    const fed = await get("/federated");
    await expect(page.getByLabel("回放轮次")).toHaveValue(
      String(fed.selected.round),
    );
    await button("播放回放").click();
    await button("暂停回放").click();
    await page.getByLabel("回放轮次").fill("7");
    await page.getByRole("button", { name: /加权聚合/ }).click();
    await expect(
      page.getByRole("heading", { name: "同一测试集上的模型表现" }),
    ).toBeVisible();
    await page
      .getByRole("heading", { name: "同一测试集上的模型表现" })
      .scrollIntoViewIfNeeded();
    await inspect();
    await page.goto("/app");
    await button("重置账号").click();
    await button("确认重置").click();
    await expect
      .poll(async () => {
        const current = await (
          await ctx.request.get("/api/v1/demo/profile")
        ).json();
        return current.account_id === "B" && current.session_id !== sid;
      })
      .toBe(true);
    const reset = await profile();
    assert.deepEqual(await mastery(reset.learner_id), before);
    assert.equal((await homework(reset.session_id)).length, 0);
    assert.equal(
      (await get("/sessions/" + reset.session_id + "/clouclip")).status,
      "ready",
    );
    await button("退出登录").click();
    await expect(button("登录 B")).toBeVisible();
    report.runs.push({
      take,
      seconds: (Date.now() - began) / 1000,
      original,
      revised,
      profile_updated: true,
      valid_upload_attempts: 4,
      revision_count: 1,
      practice_added: 1,
      other_accounts_isolated: ["A", "C"],
      reset_restored: true,
      cpu_model: before.model_version,
      care,
      federated_selected: fed.selected,
    });
  }
  await ctx.close();
  const dest = resolve(folder, "LumiRead_Desktop_Rehearsal.webm");
  await video.saveAs(dest);
  await video.delete();
  report.elapsed_seconds = (Date.now() - start) / 1000;
  report.video_sha256 = createHash("sha256")
    .update(await readFile(dest))
    .digest("hex");
  assert.ok(report.runs.every((r) => r.seconds <= 900));
  await writeFile(
    resolve(folder, "rehearsal.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  console.log(
    "Two real desktop rehearsals passed",
    report.runs.map((r) => r.seconds),
  );
} finally {
  await browser.close();
}
