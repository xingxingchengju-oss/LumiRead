import { test, expect, type BrowserContext } from "@playwright/test";

async function useRearCameraFixture(context: BrowserContext) {
  // Chromium's generated test video track has no physical facingMode metadata.
  await context.addInitScript(() => {
    const open = navigator.mediaDevices.getUserMedia.bind(
      navigator.mediaDevices,
    );
    navigator.mediaDevices.getUserMedia = async (constraints = {}) => {
      const video = constraints.video;
      if (!video || typeof video !== "object")
        throw Error("Expected rear-camera constraints");
      const requested = video.facingMode;
      if (
        requested !== "environment" &&
        !(
          requested &&
          typeof requested === "object" &&
          (("exact" in requested && requested.exact === "environment") ||
            ("ideal" in requested && requested.ideal === "environment"))
        )
      ) {
        throw Error("The glasses must request the environment camera");
      }
      const { facingMode, ...fixture } = video;
      return open({ ...constraints, video: fixture });
    };
  });
}

test("isolated browser fixture · pair, upload, receive, inspect hints and reload", async ({
  browser,
  page,
  request,
}, info) => {
  let seenReceipts = 0;
  page.on("response", (response) => {
    if (
      new URL(response.url()).pathname.endsWith("/seen") &&
      response.status() === 204
    )
      seenReceipts++;
  });
  await page.goto("/legacy-app");
  await page.getByRole("button", { name: "创建学习场次" }).click();
  await page.getByRole("button", { name: "生成配对码" }).click();
  const link = await page
    .getByRole("link", { name: "打开手机配对链接" })
    .getAttribute("href");
  const device = await browser.newContext({
    viewport: { width: 440, height: 956 },
    isMobile: true,
  });
  const phone = await device.newPage();
  try {
    await phone.goto(link!);
    await expect(
      phone.getByRole("heading", { name: "作业取景" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "开启静音" }).click();
    await expect(
      phone.getByRole("button", { name: "开启摄像头" }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "解除静音" }).click();
    await expect(
      phone.getByRole("button", { name: "开启摄像头" }),
    ).toBeEnabled();
    const image = await request.get("/__fixture__/page");
    await phone.locator("input[type=file]").setInputFiles({
      name: "fixture.jpg",
      mimeType: "image/jpeg",
      buffer: await image.body(),
    });
    await phone.getByRole("button", { name: "上传并批改" }).click();
    await expect(phone.getByRole("status")).toContainText("照片已送达");
    await expect(page.getByText("× 有误")).toBeVisible();
    const original = page.getByRole("img", { name: "本次上传的作业原图" });
    await expect(original).toBeVisible();
    await expect
      .poll(() =>
        original.evaluate((img) => (img as HTMLImageElement).naturalWidth),
      )
      .toBeGreaterThan(0);
    await page
      .getByText("Browser fixture", { exact: false })
      .scrollIntoViewIfNeeded();
    await expect.poll(() => seenReceipts).toBe(1);
    await page.getByRole("button", { name: "放大原图" }).click();
    await expect(
      page.getByRole("button", { name: "缩小原图" }),
    ).toHaveAttribute("aria-expanded", "true");
    await page.getByRole("button", { name: "缩小原图" }).click();
    await page.getByRole("button", { name: "小鹿分步讲解" }).click();
    await expect(page.getByText("先找到这两个分母的公倍数。")).toBeVisible();
    await page.getByRole("button", { name: "下一步" }).click();
    await page.getByRole("button", { name: "查看解析" }).click();
    await expect(
      page.getByText("三分之一是六分之二，加六分之一得到二分之一。"),
    ).toBeVisible();
    const photoRoute = "**/captures/*/photo";
    await page.route(photoRoute, (route) =>
      route.fulfill({ status: 503, body: "test fixture image unavailable" }),
    );
    await page.reload();
    await expect(page.getByText("× 有误")).toBeVisible();
    await expect(page.getByText("原图未能载入。")).toBeVisible();
    await page
      .getByText("Browser fixture", { exact: false })
      .scrollIntoViewIfNeeded();
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );
    expect(seenReceipts).toBe(1);
    await page.unroute(photoRoute);
    await page.getByRole("button", { name: "重新载入原图" }).click();
    await expect
      .poll(() =>
        original.evaluate((img) => (img as HTMLImageElement).naturalWidth),
      )
      .toBeGreaterThan(0);
    await page
      .getByText("Browser fixture", { exact: false })
      .scrollIntoViewIfNeeded();
    await expect.poll(() => seenReceipts).toBe(2);
    await page.screenshot({
      path: info.outputPath("parent-fixture.png"),
      fullPage: true,
    });
    await phone.screenshot({
      path: info.outputPath("phone-fixture.png"),
      fullPage: true,
    });
  } finally {
    await device.close();
  }
});

test("simulated camera · capture, retake and stop a live video track in silent mode", async ({
  browser,
  page,
}) => {
  await page.goto("/legacy-app");
  await page.getByRole("button", { name: "创建学习场次" }).click();
  await page.getByRole("button", { name: "生成配对码" }).click();
  const link = await page
    .getByRole("link", { name: "打开手机配对链接" })
    .getAttribute("href");
  const context = await browser.newContext({ permissions: ["camera"] });
  await useRearCameraFixture(context);
  const phone = await context.newPage();
  try {
    await phone.goto(link!);
    await phone.getByRole("button", { name: "开启摄像头" }).click();
    await expect(phone.locator("video")).toBeVisible();
    await phone.waitForFunction(
      () => !!document.querySelector("video")?.videoWidth,
    );
    await phone.getByRole("button", { name: "拍下作业" }).click();
    await expect(
      phone.getByRole("img", { name: "待上传的作业照片" }),
    ).toBeVisible();
    await phone.getByRole("button", { name: "重拍" }).click();
    await expect(phone.locator("video")).toBeVisible();
    const track = await phone.evaluateHandle(
      () =>
        (
          document.querySelector("video")!.srcObject as MediaStream
        ).getVideoTracks()[0],
    );
    await page.getByRole("button", { name: "开启静音" }).click();
    await expect(
      phone.getByRole("button", { name: "开启摄像头" }),
    ).toBeDisabled();
    expect(await track.evaluate((t) => t.readyState)).toBe("ended");
    await track.dispose();
  } finally {
    await context.close();
  }
});

test("five touch double taps create five distinct graded pages; a single tap and quiet mode create none", async ({
  browser,
  page,
}) => {
  const parent = page.context().request;
  const sid = (
    await (await parent.post("/api/v1/sessions", { data: {} })).json()
  ).session_id;
  const room = "/api/v1/sessions/" + sid;
  const invite = await (
    await parent.post(room + "/invites", { data: { role: "glasses" } })
  ).json();
  await page.goto("/legacy-app");
  const context = await browser.newContext({
    hasTouch: true,
    isMobile: true,
    viewport: { width: 440, height: 956 },
    permissions: ["camera"],
  });
  await useRearCameraFixture(context);
  try {
    const phone = await context.newPage();
    const uploads: string[] = [];
    phone.on("request", (r) => {
      if (r.method() === "POST" && r.url().endsWith("/captures"))
        uploads.push(r.url());
    });
    await phone.goto(invite.url);
    await phone.getByRole("button", { name: "开启摄像头" }).click();
    await expect(phone.locator("video")).toBeVisible();
    const finder = phone.locator(".viewfinder");
    await finder.scrollIntoViewIfNeeded();
    const box = (await finder.boundingBox())!;
    const position = async (side: "left" | "right") => {
      const region = (await finder
        .locator('[data-tap-side="' + side + '"]')
        .boundingBox())!;
      return {
        x: region.x + region.width / 2,
        y: region.y + region.height / 2,
      };
    };
    const left = await position("left"),
      right = await position("right");
    const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    const tap = (p: { x: number; y: number }) =>
      phone.touchscreen.tap(p.x, p.y);
    await tap(left);
    await phone.waitForTimeout(650);
    await tap(left);
    await tap(right);
    await tap(center);
    await tap(center);
    await phone.waitForTimeout(650);
    expect(uploads.length).toBe(0);
    const jobs = new Set<string>();
    for (let i = 0; i < 5; i++) {
      const response = phone.waitForResponse(
        (r) => r.url().endsWith("/captures") && r.status() === 202,
      );
      const side = i % 2 === 0 ? "left" : "right",
        p = side === "left" ? left : right;
      await tap(p);
      await tap(p);
      const accepted = await response;
      const receipt = await accepted.json();
      expect(receipt.tap_side).toBe(side);
      jobs.add(receipt.job_id);
      await expect(phone.getByRole("status")).toContainText("已送达");
      await phone.waitForTimeout(700);
      expect(uploads.length).toBe(i + 1);
    }
    expect(jobs.size).toBe(5);
    await expect
      .poll(async () => {
        const homework = await (await parent.get(room + "/homework")).json();
        return homework.filter(
          (j: { id: string; status: string }) =>
            jobs.has(j.id) && j.status === "completed",
        ).length;
      })
      .toBe(5);
    await page.getByRole("button", { name: "今日作业" }).click();
    await expect(
      page.getByRole("img", { name: "本次上传的作业原图" }).first(),
    ).toBeVisible();
    await parent.patch(room + "/settings", { data: { silent: true } });
    await expect(
      phone.getByRole("button", { name: "开启摄像头" }),
    ).toBeDisabled();
    await tap(left);
    await tap(left);
    await phone.waitForTimeout(650);
    expect(uploads.length).toBe(5);
    expect((await (await parent.get(room + "/homework")).json()).length).toBe(
      5,
    );
  } finally {
    await context.close();
  }
});

test("pairing instructions reflect the active phone transport after a restart", async ({
  page,
}) => {
  let publicMode = true;
  await page.route("**/phone-setup", (route) =>
    route.fulfill({
      json: {
        mode: publicMode ? "public" : "lan",
        public_unavailable: !publicMode,
        certificate: publicMode
          ? null
          : "http://192.0.2.1:8744/lumiread-ca.cer",
        fingerprint: publicMode ? null : "TEST ONLY",
      },
    }),
  );
  await page.goto("/legacy-app");
  await page.getByRole("button", { name: "创建学习场次" }).click();
  await page.getByText("首次连接 iPhone").click();
  await expect(
    page.getByText("公网拍摄入口已开启。", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "虚拟眼镜配对二维码" }),
  ).toBeVisible();
  await expect(
    page.getByText("LumiRead Local Demo CA", { exact: false }),
  ).toHaveCount(0);
  publicMode = false;
  await page.reload();
  await expect(
    page.getByText("公网隧道未连通", { exact: false }),
  ).toBeVisible();
  await page.getByText("首次连接 iPhone").click();
  await expect(
    page.getByRole("link", { name: /lumiread-ca.cer/ }),
  ).toBeVisible();
});
