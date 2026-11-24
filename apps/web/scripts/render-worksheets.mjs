import { chromium } from "@playwright/test";
import { existsSync } from "node:fs";
import { mkdir, readFile } from "node:fs/promises";
import { dirname } from "node:path";
const [manifest] = process.argv.slice(2);
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({
  executablePath:
    process.env.LUMIREAD_CHROME || (existsSync(chrome) ? chrome : undefined),
});
try {
  const page = await browser.newPage({
    viewport: { width: 1050, height: 1000 },
    deviceScaleFactor: 1,
  });
  const sheets = JSON.parse(await readFile(manifest, "utf8"));
  for (const sheet of sheets) {
    await page.setContent(`<!doctype html><meta charset="utf-8"><style>
      *{box-sizing:border-box}body{margin:0;background:white;color:#151a22;font:25px Arial,sans-serif}main{padding:56px 65px}
      header{border-bottom:2px solid #718178;padding-bottom:18px;margin-bottom:26px}h1{font-size:36px;margin:0}ol{padding-left:38px}li{margin:0 0 24px;padding:0 0 16px 6px;border-bottom:1px solid #d5dbd8;line-height:1.32}.answer{color:#174c80;margin:7px 0 0}
    </style><main><header><h1></h1></header><ol></ol></main>`);
    await page.evaluate(({ title, items }) => {
      document.querySelector("h1").textContent = title;
      const list = document.querySelector("ol");
      for (const { question, answer } of items) {
        const li = document.createElement("li");
        li.textContent = question;
        const line = document.createElement("div");
        line.className = "answer";
        line.textContent = "My answer: " + answer;
        li.append(line);
        list.append(li);
      }
    }, sheet);
    await mkdir(dirname(sheet.path), { recursive: true });
    await page.locator("main").screenshot({ path: sheet.path });
  }
} finally {
  await browser.close();
}
