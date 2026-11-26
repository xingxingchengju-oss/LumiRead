import { test, expect, type APIRequestContext } from "@playwright/test";

async function pairedPhone(
  parent: APIRequestContext,
  phone: APIRequestContext,
  sid: string,
) {
  const invitation = await parent.post(`/api/v1/sessions/${sid}/invites`, {
    data: { role: "glasses" },
  });
  expect(invitation.ok()).toBeTruthy();
  expect(
    (
      await phone.post(`/api/v1/sessions/${sid}/join`, {
        data: { code: (await invitation.json()).code },
      })
    ).ok(),
  ).toBeTruthy();
}

test("real product catalog, both rotatable models and device-independent same-room navigation", async ({
  page,
  browser,
}, info) => {
  const { session_id: sid } = await (
    await page.request.post("/api/v1/sessions", { data: {} })
  ).json();
  const other = await browser.newContext({ baseURL: info.project.use.baseURL });
  const requests: string[] = [],
    sockets: string[] = [];
  const requested = (url: string) => {
    if (url.includes("/api/v1/")) requests.push(new URL(url).pathname);
  };
  page.on("request", (r) => requested(r.url()));
  page.on("websocket", (s) => sockets.push(s.url()));
  try {
    await pairedPhone(page.request, other.request, sid);
    await page.goto("/showcase?legacy=1&room=" + sid);
    test.setTimeout(60000);
    const nav = page.getByRole("navigation", { name: "产品导航" });
    const surface = page.getByRole("region", { name: "交互眼镜模型" });
    const lens = page.getByRole("button", { name: "镜片热点" });
    await expect(
      page.getByRole("heading", { level: 1, name: /LumiRead.*智能学习眼镜/ }),
    ).toBeInViewport();
    await expect(surface).toHaveAttribute("data-renderer", "webgl", {
      timeout: 20000,
    });
    await expect(lens).toBeVisible();
    const position = () => lens.evaluate((el) => parseFloat(el.style.left));
    const start = await position();
    await expect
      .poll(async () => Math.abs((await position()) - start))
      .toBeGreaterThan(0.15);
    await page.getByRole("button", { name: "暂停旋转" }).click();
    await page.screenshot({
      path: info.outputPath("showcase-launch-desktop.png"),
    });
    const clickLensSurface = async () => {
      const rect = (await lens.boundingBox())!;
      // Hit the actual optical surface beyond the overlapping HTML marker.
      await page.mouse.click(
        rect.x + rect.width / 2 + 32,
        rect.y + rect.height / 2,
      );
    };
    await clickLensSurface();
    await expect(
      page.getByRole("heading", { name: "三种佩戴方式" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "无镜片", exact: true }).click();
    await expect(page.locator(".lr-stage")).toHaveAttribute(
      "data-wear",
      "open",
    );
    await page.getByRole("button", { name: "返回全貌" }).click();
    await expect(lens).toBeVisible();
    await page.emulateMedia({ reducedMotion: "reduce" });
    await clickLensSurface();
    await expect(
      page.getByRole("button", { name: "无镜片", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "夹片款", exact: true }).click();
    await expect(page.locator(".lr-stage")).toHaveAttribute(
      "data-wear",
      "clip",
    );
    await expect(surface).toHaveAttribute("data-renderer", "webgl");
    await expect(surface).toHaveAttribute("aria-busy", "false");
    await page.screenshot({ path: info.outputPath("showcase-clip.png") });
    await nav.getByRole("link", { name: "学习感知" }).click();
    await page.getByRole("button", { name: "ToF 距离传感器热点" }).click();
    await expect(
      page.getByRole("heading", { name: "ToF 距离传感器" }),
    ).toBeFocused();
    await expect(page.getByText(/模块正面的测距窗口/)).toBeVisible();
    await page.mouse.wheel(0, 650);
    await expect(
      page.getByRole("heading", { name: "ToF 距离传感器" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await nav.getByRole("link", { name: "佩戴结构" }).click();
    await expect(page.getByText("夹装模块目标重量约 13 g")).toBeVisible();
    await nav.getByRole("link", { name: "佩戴方式" }).click();
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.getByRole("button", { name: "防蓝光无度数镜片" }).click();
    await page.getByRole("button", { name: "部件目录" }).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "右镜腿" })
      .click();
    await expect(page.getByRole("heading", { name: "右镜腿" })).toBeVisible();
    await expect(surface).toHaveAttribute("aria-busy", "false");
    // The solder mask must be visible through the actual shell, including when
    // the visitor opens the right temple during the clip removal animation.
    await expect
      .poll(async () => {
        const png = await surface.screenshot({ scale: "css" });
        return page.evaluate(async (base64) => {
          const image = new Image();
          image.src = "data:image/png;base64," + base64;
          await image.decode();
          const thumbnail = document.createElement("canvas");
          thumbnail.width = 160;
          thumbnail.height = 100;
          const ctx = thumbnail.getContext("2d")!;
          ctx.drawImage(image, 0, 0, 160, 100);
          const pixels = ctx.getImageData(0, 0, 160, 100).data;
          let boardPixels = 0;
          for (let i = 0; i < pixels.length; i += 4) {
            const green = pixels[i + 1];
            if (
              green > 45 &&
              green > pixels[i] + 12 &&
              green > pixels[i + 2] + 3
            )
              boardPixels++;
          }
          return boardPixels;
        }, png.toString("base64"));
      })
      .toBeGreaterThan(50);
    const detailView = (await surface.boundingBox())!;
    await surface.click({
      position: { x: detailView.width / 2, y: detailView.height / 2 },
    });
    await expect(page.getByText(/右镜腿里的电路板/)).toBeVisible();
    await page.getByRole("button", { name: "可充电电池" }).click();
    await expect(page.getByText(/左镜腿内的电池/)).toBeVisible();
    await expect(surface).toHaveAttribute("aria-busy", "false");
    await page.screenshot({ path: info.outputPath("showcase-frame.png") });
    await nav.getByRole("link", { name: "查看价格" }).click();
    for (const value of ["¥799", "¥499", "¥198 / 年"])
      await expect(page.getByText(value, { exact: true })).toBeInViewport();
    const world = Date.now();
    const samples = [0, 3].map((t) => ({
      metric: "distance_cm",
      value: 26,
      unit: "cm",
      value_kind: "estimated",
      input_mode: "live",
      method: "qr-size-proxy-v2",
      quality: "ok",
      calibration_id: null,
      observed_at: new Date(world + t * 1000).toISOString(),
    }));
    expect(
      (
        await other.request.post(`/api/v1/sessions/${sid}/telemetry/batch`, {
          data: { samples },
        })
      ).ok(),
    ).toBeTruthy();
    expect(requests).toEqual(["/api/v1/products"]);
    expect(sockets).toEqual([]);
    const near = "离作业有点近，稍微坐远一点";
    const dim = "桌面有点暗，试试开灯或挪到亮一点的地方";
    await expect(page.getByText(near)).toHaveCount(0);
    await page.getByRole("link", { name: "进入学习助手" }).first().click();
    await expect(page).toHaveURL(new RegExp("room=" + sid));
    await expect(
      page.getByRole("region", { name: "当前护眼提醒" }).getByText(near),
    ).toBeVisible();
    await expect(
      page.locator(".reading").getByText("可能过近", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("26 cm", { exact: true })).toHaveCount(0);
    await page.screenshot({
      path: info.outputPath("parent-eye.png"),
      fullPage: true,
    });
    await page.getByText(/查看观测记录与来源/).click();
    await expect(
      page.getByRole("cell", { name: "可能过近" }).first(),
    ).toBeVisible();
    const send = async (batch: object[]) => {
      expect(
        (
          await other.request.post(`/api/v1/sessions/${sid}/telemetry/batch`, {
            data: { samples: batch },
          })
        ).ok(),
      ).toBe(true);
    };
    const timeAt = (seconds: number) =>
      new Date(world + seconds * 1000).toISOString();
    const alerts = page.getByRole("region", { name: "当前护眼提醒" });
    await send([{ ...samples[0], value: 41, observed_at: timeAt(4) }]);
    await expect(alerts.getByText(near)).toHaveCount(0);
    await expect(page.locator(".reading")).toContainText("距离合适");
    await send([
      {
        ...samples[0],
        value: null,
        quality: "missing",
        observed_at: timeAt(5),
      },
    ]);
    await expect(page.locator(".reading")).toContainText("暂时无法估计");
    const brightness = {
      ...samples[0],
      metric: "brightness",
      value: 25,
      unit: "level",
      value_kind: "measured",
      method: "center-luma-rec709-v1",
    };
    await send([6, 9].map((t) => ({ ...brightness, observed_at: timeAt(t) })));
    await expect(alerts.getByText(dim)).toBeVisible();
    await send([{ ...brightness, value: 155, observed_at: timeAt(10) }]);
    await expect(alerts.getByText(dim)).toHaveCount(0);
  } finally {
    await other.close();
  }
});

test("mobile 3D accepts horizontal drags and vertical page scrolls on the same canvas", async ({
  browser,
  baseURL,
}) => {
  const phone = await browser.newContext({
    baseURL,
    isMobile: true,
    hasTouch: true,
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  try {
    const page = await phone.newPage();
    await page.goto("/");
    await page.getByRole("link", { name: "眼镜设计" }).tap();
    const surface = page.getByRole("region", { name: "交互眼镜模型" });
    await expect(surface).toHaveAttribute("data-renderer", "webgl", {
      timeout: 20000,
    });
    await page.getByRole("button", { name: "暂停旋转" }).tap();
    const canvas = await surface.locator("canvas").elementHandle();
    const marker = page.getByRole("button", { name: "镜片热点" });
    const position = () => marker.evaluate((el) => parseFloat(el.style.left));
    const start = await position();
    const bounds = (await surface.boundingBox())!;
    const x = bounds.x + bounds.width * 0.62,
      y = bounds.y + bounds.height * 0.6;
    const touch = await phone.newCDPSession(page);
    const swipe = async (dx: number, dy: number) => {
      await touch.send("Input.dispatchTouchEvent", {
        type: "touchStart",
        touchPoints: [{ x, y }],
      });
      for (let i = 1; i <= 8; i++) {
        await touch.send("Input.dispatchTouchEvent", {
          type: "touchMove",
          touchPoints: [{ x: x + (dx * i) / 8, y: y + (dy * i) / 8 }],
        });
        await page.evaluate(
          () =>
            new Promise<void>((resolve) =>
              requestAnimationFrame(() => resolve()),
            ),
        );
      }
      await touch.send("Input.dispatchTouchEvent", {
        type: "touchEnd",
        touchPoints: [],
      });
    };
    await swipe(58, 0);
    await expect
      .poll(async () => Math.abs((await position()) - start))
      .toBeGreaterThan(1);
    expect(await page.evaluate(() => scrollY)).toBe(0);
    await swipe(0, -200);
    await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(65);
    expect(
      await canvas!.evaluate(
        (el) => el === document.querySelector(".lr-surface canvas"),
      ),
    ).toBe(true);
  } finally {
    await phone.close();
  }
});

test("failed catalog request can recover in the same product page", async ({
  page,
}) => {
  await page.route(
    "**/api/v1/products",
    (route) =>
      route.fulfill({ status: 503, json: { detail: "产品目录暂时不可用" } }),
    { times: 1 },
  );
  await page.goto("/showcase#specifications");
  await expect(page.getByRole("alert")).toHaveText("产品目录暂时不可用");
  await page.getByRole("button", { name: "重新读取产品" }).click();
  await expect(page.getByText("¥799", { exact: true })).toBeInViewport();
  await expect(
    page.getByRole("link", { name: "进入学习助手" }),
  ).toHaveAttribute("href", "/app");
});

test("narrow screen product-image fallback retains every sensor and preserves the room number", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...rest: unknown[]
    ) {
      if (
        type === "webgl" ||
        type === "webgl2" ||
        type === "experimental-webgl"
      )
        return null;
      return Reflect.apply(original, this, [type, ...rest]);
    } as typeof original;
  });
  await page.goto("/?legacy=1&room=same-room");
  const surface = page.getByRole("region", { name: "交互眼镜模型" });
  await expect(surface).toHaveAttribute("data-renderer", "poster");
  await expect(surface.getByRole("img")).toHaveAttribute(
    "src",
    "/products/frame.webp",
  );
  await expect(
    page.getByRole("heading", { level: 1, name: /智能学习眼镜/ }),
  ).toBeInViewport();
  await page.screenshot({
    path: info.outputPath("showcase-launch-mobile.png"),
  });
  await surface
    .getByRole("button", { name: "在镜圈处选择佩戴方式" })
    .last()
    .click();
  await page.getByRole("button", { name: "无镜片", exact: true }).click();
  await expect(surface.getByRole("img")).toHaveAttribute(
    "src",
    "/products/frame-open.webp",
  );
  await page.getByRole("button", { name: "夹片款", exact: true }).click();
  await expect(surface.getByRole("img")).toHaveAttribute(
    "src",
    "/products/clip.webp",
  );
  await expect(
    page.getByRole("button", { name: /继续旋转|暂停旋转/ }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "部件目录" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "环境光传感器" })
    .click();
  await expect(page.getByText(/传感器测量读写环境的明暗/)).toBeVisible();
  await page.getByRole("link", { name: "查看价格" }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("link", { name: "进入学习助手" }).first().click();
  await expect(page.getByLabel("场次编号")).toHaveValue("same-room");
});

test("saving and correcting a worksheet updates the learner's history; a telemetry event preserves the open hint", async ({
  page,
  browser,
}, info) => {
  await page.goto("/legacy-app");
  await page.getByRole("button", { name: "创建学习场次" }).click();
  await expect(
    page.getByRole("heading", { name: "学习观察手册" }),
  ).toBeVisible();
  const sid = (await (await page.request.get("/api/v1/me")).json()).session_id;
  const phone = await browser.newContext({ baseURL: info.project.use.baseURL });
  try {
    await pairedPhone(page.request, phone.request, sid);
    const photo = await phone.request.get("/__fixture__/page");
    expect(
      (
        await phone.request.post(`/api/v1/sessions/${sid}/captures`, {
          multipart: {
            photo: {
              name: "fixture.jpg",
              mimeType: "image/jpeg",
              buffer: await photo.body(),
            },
            source: "native_camera",
            phone_confirmed: "false",
            idem: "notebook-worksheet",
          },
        })
      ).ok(),
    ).toBeTruthy();
    await page.getByRole("button", { name: "今日作业" }).click();
    await page.getByRole("button", { name: "小鹿分步讲解" }).click();
    await expect(
      page.getByRole("img", { name: "一只小鹿低头看着摊开的练习本" }),
    ).toBeVisible();
    const requests: string[] = [];
    page.on("request", (r) => requests.push(r.url()));
    await phone.request.post(`/api/v1/sessions/${sid}/telemetry/batch`, {
      data: {
        samples: [
          {
            metric: "brightness",
            value: 120,
            unit: "level",
            value_kind: "measured",
            input_mode: "live",
            method: "center-luma-rec709-v1",
            quality: "ok",
            observed_at: new Date().toISOString(),
          },
        ],
      },
    });
    await page.getByRole("button", { name: "下一步" }).click();
    await expect(page.getByText("将三分之一写成六分之几？")).toBeVisible();
    expect(requests.some((r) => r.endsWith("/homework"))).toBeFalsy();
    await page.screenshot({
      path: info.outputPath("parent-fawn-guide.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "收藏错题" }).click();
    await expect(page.getByRole("button", { name: "已收藏" })).toBeDisabled();
    await page.getByRole("button", { name: "学习档案" }).click();
    await expect(
      page.getByRole("heading", { name: "六维学习画像" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "1/3 + 1/6", exact: true }),
    ).toBeVisible();
    await page.getByLabel("知识点", { exact: true }).selectOption("decimals");
    await expect(page.getByText("这个知识点还没有收藏。")).toBeVisible();
    await page.getByRole("button", { name: "今日作业" }).click();
    await page.getByRole("button", { name: "对照原图订正" }).click();
    await page.getByLabel("订正学生答案").fill("1/2");
    await page.getByRole("button", { name: "提交重新判分" }).click();
    await expect(page.getByText("✓ 正确", { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByText("✓ 正确", { exact: true })).toBeVisible();
  } finally {
    await phone.close();
  }
});

test("two answerable recommendation cards and sparse six-skill predictions (browser fixture)", async ({
  page,
}) => {
  const names = [
    "mixed_arithmetic",
    "fractions",
    "decimals",
    "equations",
    "area",
    "word_modeling",
  ];
  await page.route("**/learners/*/mastery", (r) =>
    r.fulfill({
      json: {
        model_version: "browser-fixture",
        device: "cpu",
        available: true,
        skills: names.map((skill, i) => ({
          skill,
          probability: i === 0 ? 0.43 : null,
          evidence_count: i === 0 ? 2 : 0,
        })),
      },
    }),
  );
  await page.route("**/learners/*/recommendations", (r) =>
    r.fulfill({
      json: {
        items: [
          { id: "practice-1", skill: "fractions", question: "1/4 + 1/4" },
          { id: "practice-2", skill: "equations", question: "2x = 10" },
        ],
      },
    }),
  );
  let accepted = 0;
  await page.route("**/recommendations/*/attempts", (r) => {
    const data = r.request().postDataJSON();
    expect(data.answer).toBe("1/2");
    expect(data.idem.length).toBeGreaterThan(8);
    accepted++;
    return r.fulfill({
      json: {
        question: "1/4 + 1/4",
        correct: true,
        reference_answer: "1/2",
        explanation: "同分母相加后约分。",
      },
    });
  });
  await page.goto("/legacy-app");
  await page.getByRole("button", { name: "创建学习场次" }).click();
  await page.getByRole("button", { name: "学习档案" }).click();
  await expect(page.getByText("暂无预测", { exact: true })).toHaveCount(5);
  await expect(page.getByText("43%", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "提交答案" })).toHaveCount(2);
  await page.getByLabel("你的答案").first().fill("1/2");
  await page.getByRole("button", { name: "提交答案" }).first().click();
  await expect(page.getByText("同分母相加后约分。")).toBeVisible();
  expect(accepted).toBe(1);
  await expect(page.getByRole("heading", { name: "2x = 10" })).toBeVisible();
});

test("live CPU learning API grades both exercises in one round and carries the learner into the next room", async ({
  page,
}) => {
  await page.goto("/legacy-app");
  await page.getByRole("button", { name: "创建学习场次" }).click();
  await expect(
    page.getByRole("heading", { name: "学习观察手册" }),
  ).toBeVisible();
  const original = await (await page.request.get("/api/v1/me")).json();
  const room = await (
    await page.request.get(`/api/v1/sessions/${original.session_id}/snapshot`)
  ).json();
  const profile = () =>
    page.request
      .get(`/api/v1/learners/${room.learner_id}/mastery`)
      .then((r) => r.json());
  const before = await profile();
  expect(before.available).toBe(true);
  expect(before.device).toBe("cpu");
  await page.getByRole("button", { name: "学习档案" }).click();
  await expect(
    page.getByText("模型 " + before.model_version + " · CPU"),
  ).toBeVisible();
  const initial = await (
    await page.request.get(
      `/api/v1/learners/${room.learner_id}/recommendations`,
    )
  ).json();
  expect(initial.items).toHaveLength(2);
  for (const item of initial.items) {
    const card = page.locator("form.practice").filter({
      has: page.getByRole("heading", { name: item.question, exact: true }),
    });
    await expect(card).toBeVisible();
    await card.getByLabel("你的答案").fill("0");
    const receipt = page.waitForResponse((r) =>
      r.url().endsWith(`/recommendations/${item.id}/attempts`),
    );
    await card.getByRole("button", { name: "提交答案" }).click();
    const actual = await receipt;
    expect(actual.ok()).toBe(true);
    const graded = await actual.json();
    expect(graded.question).toBe(item.question);
    await expect(
      page.getByText(graded.explanation, { exact: true }),
    ).toBeVisible();
  }
  await page.getByRole("button", { name: "开始下一组练习" }).click();
  await expect(page.getByRole("button", { name: "提交答案" })).toHaveCount(2);
  const after = await profile(),
    total = (s: { evidence_count: number }[]) =>
      s.reduce((a, v) => a + v.evidence_count, 0);
  expect(total(after.skills)).toBe(total(before.skills) + 2);
  expect(
    after.skills.map((s: { probability: number }) => s.probability),
  ).not.toEqual(
    before.skills.map((s: { probability: number }) => s.probability),
  );
  await page.getByText("开始新的学习场次", { exact: true }).click();
  await page.getByRole("button", { name: "创建并进入新场次" }).click();
  await expect(page).toHaveURL(/\/legacy-app\?room=/);
  const current = await (await page.request.get("/api/v1/me")).json();
  expect(current.session_id).not.toBe(original.session_id);
  const next = await (
    await page.request.get(`/api/v1/sessions/${current.session_id}/snapshot`)
  ).json();
  expect(next.learner_id).toBe(room.learner_id);
  await page.getByRole("button", { name: "学习档案" }).click();
  await expect(
    page.getByRole("heading", { name: "六维学习画像" }),
  ).toBeVisible();
  expect((await profile()).skills).toEqual(after.skills);
});
