import { test, expect, type Page, type Response } from "@playwright/test";

async function realSourceResponse(page: Page, response: Response) {
  if (
    response.status() === 503 &&
    (await response.json()).code === "UPSTREAM_RATE_LIMIT"
  ) {
    test.setTimeout(180000);
    await expect(page.getByRole("alert")).toContainText(/一分钟后重试/);
    console.info(
      "Real provider quota reached; respecting the minute window before one UI retry.",
    );
    await page.waitForTimeout(61000);
    const retry = page.waitForResponse(
      (r) =>
        r.url() === response.url() &&
        r.request().method() === response.request().method(),
      { timeout: 15000 },
    );
    await page.getByRole("button", { name: "重新尝试", exact: true }).click();
    response = await retry;
  }
  expect(response.status(), await response.text()).toBe(200);
  return response;
}

async function recommend(page: Page, name = "什么都行，直接看看") {
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/recommendations") &&
      r.request().method() === "POST",
    { timeout: 15000 },
  );
  await page.getByRole("button", { name, exact: true }).click();
  const received = await realSourceResponse(page, await response);
  const data = await received.json();
  expect(["live", "cached"]).toContain(data.data_mode);
  expect(
    data.candidates.every((c: any) => c.movie.movie_id.startsWith("itunes:")),
  ).toBe(true);
  await expect(page.locator(".candidate-grid > article")).toHaveCount(
    data.candidates.length,
  );
  return { data, body: received.request().postDataJSON() };
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("audit: reroll remains usable after navigation and cancellation", async ({
  page,
}) => {
  const first = await recommend(page);
  await page.getByRole("link", { name: "偏好与隐私", exact: true }).click();
  await page.getByRole("link", { name: "回选片室", exact: true }).click();
  const second = await recommend(page, "换一组真实电影");
  const oldIds = first.data.candidates.map((c: any) => c.movie.movie_id);
  expect(second.body.constraints.exclude_movie_ids).toEqual(
    expect.arrayContaining(oldIds),
  );
  expect(
    second.data.candidates.every(
      (c: any) => !oldIds.includes(c.movie.movie_id),
    ),
  ).toBe(true);

  let release!: () => void;
  await page.route(
    "**/api/recommendations",
    async (route) => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      await route.abort().catch(() => {});
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "看看候选电影", exact: true }).click();
  await expect.poll(() => Boolean(release)).toBe(true);
  await page.getByRole("button", { name: "取消本次请求", exact: true }).click();
  release();
  const third = await recommend(page, "换一组真实电影");
  const secondIds = second.data.candidates.map((c: any) => c.movie.movie_id);
  expect(third.body.constraints.exclude_movie_ids).toEqual(
    expect.arrayContaining(secondIds),
  );
  expect(
    third.data.candidates.every(
      (c: any) => !secondIds.includes(c.movie.movie_id),
    ),
  ).toBe(true);
});

test("audit: editing a pending search cancels it and never offers stale identities", async ({
  page,
}) => {
  const { data } = await recommend(page);
  const film = data.candidates[0].movie;
  await page.getByRole("tab", { name: "已知道片名", exact: true }).click();
  const title = page.getByLabel("影片名称", { exact: true });
  await title.fill(film.title);
  const actual = await page.request.get(
    `/api/movies?query=${encodeURIComponent(film.title)}`,
  );
  expect(actual.status()).toBe(200);
  const actualBody = await actual.text();
  let release!: () => void;
  await page.route(
    "**/api/movies?**",
    async (route) => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      await route
        .fulfill({ contentType: "application/json", body: actualBody })
        .catch(() => {});
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "查找影片", exact: true }).click();
  await expect.poll(() => Boolean(release)).toBe(true);
  await title.fill("zzzz-no-such-movie-20261022");
  await expect(
    page.getByRole("button", { name: "查找影片", exact: true }),
  ).toBeEnabled();
  release();
  await expect(page.locator(".lookup-item")).toHaveCount(0);
  const response = page.waitForResponse((r) =>
    r.url().includes("/api/movies?"),
  );
  await title.press("Enter");
  await realSourceResponse(page, await response);
  await expect(page.locator(".lookup-results")).toContainText("没有找到影片");
});

test("audit: zero input really clears era and ordering constraints", async ({
  page,
}) => {
  await page
    .getByRole("group", { name: "想看哪个年代？" })
    .getByRole("button", { name: "2000 年以前", exact: true })
    .click();
  await page
    .getByRole("group", { name: "怎么安排候选？" })
    .getByRole("button", { name: "榜单顺序", exact: true })
    .click();
  const { body } = await recommend(page);
  expect(body.constraints.era).toBe("any");
  expect(body.constraints.sort_by).toBe("balanced");
  await expect(
    page.getByRole("button", { name: "不限年代", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("audit: Enter respects invalid search year and empty search uses honest guidance", async ({
  page,
}) => {
  await page.getByRole("tab", { name: "已知道片名", exact: true }).click();
  const title = page.getByLabel("影片名称", { exact: true });
  const year = page.getByLabel("年份（可选）", { exact: true });
  await expect(title).not.toHaveAttribute("placeholder", /春日来信|远星航线/);
  let requests = 0;
  page.on("request", (r) => {
    if (r.url().includes("/api/movies?")) requests += 1;
  });
  await title.fill("zzzz-no-such-movie-20261022");
  await year.fill("1800");
  await expect(
    page.getByRole("button", { name: "查找影片", exact: true }),
  ).toBeDisabled();
  await title.press("Enter");
  await expect(year).toHaveAttribute("aria-invalid", "true");
  expect(requests).toBe(0);
  await year.fill("");
  const response = page.waitForResponse((r) =>
    r.url().includes("/api/movies?"),
  );
  await title.press("Enter");
  await realSourceResponse(page, await response);
  await expect(page.locator(".lookup-results")).toContainText("没有找到影片");
  await expect(page.locator(".lookup-results")).not.toContainText(
    /春日来信|远星航线/,
  );
});

test("audit: collection, comparison, limits, undo and clear controls work", async ({
  page,
}) => {
  const { data } = await recommend(page);
  const first = page.locator(".candidate-grid > article").first();
  await first
    .getByRole("button", { name: "加入本次片单", exact: true })
    .click();
  await first
    .getByRole("button", { name: "移出本次片单", exact: true })
    .click();
  await page.getByRole("button", { name: "撤销", exact: true }).click();
  await expect(
    first.getByRole("button", { name: "移出本次片单", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭提示", exact: true }).click();
  await expect(page.locator(".toast")).toHaveCount(0);
  for (const check of await page
    .locator(".candidate-grid")
    .getByRole("checkbox")
    .all())
    await check.check();
  await expect(page.locator(".compare-tray")).toContainText("已选 3/3 部");
  await recommend(page, "换一组真实电影");
  const fourth = page.locator(".candidate-grid").getByRole("checkbox").first();
  await fourth.click();
  await expect(fourth).not.toBeChecked();
  await expect(page.locator(".toast")).toContainText("最多对比 3 部");
  await page
    .locator(".compare-tray")
    .getByRole("button", { name: "清空", exact: true })
    .click();
  await expect(page.locator(".compare-tray")).toHaveCount(0);
  await page.getByRole("button", { name: "撤销", exact: true }).click();
  await expect(page.locator(".compare-tray")).toContainText("已选 3/3 部");
  await page.getByRole("link", { name: "开始对比", exact: true }).click();
  await expect(page.getByRole("table")).toBeVisible();
  for (let i = 0; i < 2; i++) {
    await page
      .getByRole("button", { name: /^移除对比 / })
      .first()
      .click();
    if (i === 0) await expect(page.getByRole("columnheader")).toHaveCount(3);
  }
  await expect(
    page.getByRole("heading", { name: "选好两部，就可以对比", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "去本次片单", exact: true }).click();
  await expect(page.locator(".movie-grid > article")).toHaveCount(1);
  await page
    .getByRole("button", { name: "从这些电影中选", exact: true })
    .click();
  await expect(
    page.getByRole("tab", { name: "从片单中选", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  const onlySaved = await recommend(page, "看看候选电影");
  expect(onlySaved.data.candidates.map((c: any) => c.movie.movie_id)).toEqual([
    data.candidates[0].movie.movie_id,
  ]);
  await page.getByRole("link", { name: "偏好与隐私", exact: true }).click();
  await page
    .getByRole("button", { name: "清空本次片单与对比", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "清空本次片单与对比", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "撤销", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "清空本次片单与对比", exact: true }),
  ).toBeEnabled();
  await page.getByRole("link", { name: /本次片单/, exact: true }).click();
  await expect(page.locator(".movie-grid > article")).toHaveCount(1);
});

test("audit: exclusion recovery and optional known-film/watchlist text", async ({
  page,
}) => {
  const { data } = await recommend(page);
  for (let i = 0; i < data.candidates.length; i++)
    await page
      .getByRole("button", { name: "这次不想看", exact: true })
      .first()
      .click();
  await expect(
    page.getByRole("heading", { name: "本次候选已隐藏", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "恢复显示", exact: true }).click();
  await expect(page.locator(".candidate-grid > article")).toHaveCount(3);
  const film = data.candidates[0].movie;
  await page.getByRole("tab", { name: "已知道片名", exact: true }).click();
  await page.getByRole("button", { name: "看看候选电影", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("请先查找并确认影片");
  await page.getByLabel("影片名称", { exact: true }).fill(film.title);
  await page
    .getByLabel("年份（可选）", { exact: true })
    .fill(String(film.year));
  await page.getByRole("button", { name: "查找影片", exact: true }).click();
  await page
    .locator(".lookup-item")
    .filter({ hasText: film.title })
    .getByRole("button", { name: "确认这部", exact: true })
    .first()
    .click();
  await page
    .getByRole("textbox", { name: "关于这部电影，你在意什么？", exact: true })
    .fill("");
  const known = await recommend(page, "看看候选电影");
  expect(known.data.candidates.map((c: any) => c.movie.movie_id)).toEqual([
    film.movie_id,
  ]);
  await page
    .locator(".candidate-grid")
    .getByRole("button", { name: "加入本次片单", exact: true })
    .click();
  await page.getByRole("tab", { name: "从片单中选", exact: true }).click();
  await page
    .getByRole("textbox", { name: "补充备注（暂不参与匹配）", exact: true })
    .fill("");
  expect(
    (await recommend(page, "看看候选电影")).data.candidates[0].movie.movie_id,
  ).toBe(film.movie_id);
});

const scenes = [
  {
    name: /^松弛一点 /,
    mood: "轻松解压",
    genre: "喜剧",
    company: "",
    runtime: 90,
  },
  {
    name: /^约会之夜 /,
    mood: "浪漫心动",
    genre: "爱情",
    company: "两个人",
    runtime: null,
  },
  {
    name: /^换个世界 /,
    mood: "惊奇冒险",
    genre: "科幻与奇幻",
    company: "",
    runtime: null,
  },
  {
    name: /^烧脑之夜 /,
    mood: "烧脑过瘾",
    genre: "惊悚",
    company: "",
    runtime: null,
  },
  {
    name: /^全家一起 /,
    mood: "温暖治愈",
    genre: "动画",
    company: "和家人",
    runtime: 120,
  },
  {
    name: /^留点余味 /,
    mood: "感动一下",
    genre: "剧情",
    company: "一个人",
    runtime: null,
  },
];
for (const scene of scenes)
  test(`audit: quick scene ${scene.mood} sends and applies its real constraints`, async ({
    page,
  }) => {
    await page
      .getByRole("group", { name: "想看哪个年代？" })
      .getByRole("button", { name: "2000 年以前", exact: true })
      .click();
    const response = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/recommendations") &&
        r.request().method() === "POST",
    );
    await page.getByRole("button", { name: scene.name }).click();
    const actual = await realSourceResponse(page, await response);
    expect(actual.request().postDataJSON().constraints).toMatchObject({
      moods: [scene.mood],
      genres: [scene.genre],
      company: scene.company,
      max_runtime_minutes: scene.runtime,
      era: "any",
      sort_by: "balanced",
    });
    const data = await actual.json();
    expect(["live", "cached"]).toContain(data.data_mode);
    for (const c of data.candidates) {
      expect(c.movie.movie_id).toMatch(/^itunes:/);
      expect(c.movie.genres).toContain(scene.genre);
      if (scene.runtime)
        expect(c.movie.runtime_minutes).toBeLessThanOrEqual(scene.runtime);
    }
    await expect(page.locator(".candidate-grid > article")).toHaveCount(
      data.candidates.length,
    );
    if (!data.candidates.length)
      await expect(
        page.getByRole("button", { name: "清空筛选条件", exact: true }),
      ).toBeVisible();
  });

test("audit: every structured choice toggles and is sent to the real service", async ({
  page,
}) => {
  const groups = [
    {
      name: "想要什么感觉？",
      values: [
        "轻松解压",
        "温暖治愈",
        "烧脑过瘾",
        "浪漫心动",
        "惊奇冒险",
        "感动一下",
      ],
      field: "moods",
    },
    {
      name: "想看哪种故事？",
      values: [
        "喜剧",
        "科幻与奇幻",
        "惊悚",
        "动作",
        "爱情",
        "动画",
        "剧情",
        "家庭",
        "纪录片",
        "恐怖",
      ],
      field: "genres",
    },
    {
      name: "和谁一起看？（家人会筛选家庭/动画）",
      values: ["一个人", "两个人", "和朋友", "和家人"],
      field: "company",
    },
  ];
  for (const group of groups) {
    for (const value of group.values) {
      await page.getByRole("button", { name: "清空选择", exact: true }).click();
      const button = page
        .getByRole("group", { name: group.name })
        .getByRole("button", { name: value, exact: true });
      await button.click();
      await expect(button).toHaveAttribute("aria-pressed", "true");
      const { data, body } = await recommend(page, "看看候选电影");
      expect(body.constraints[group.field]).toEqual(
        group.field === "company" ? value : [value],
      );
      if (group.field === "genres")
        for (const c of data.candidates)
          expect(c.movie.genres).toContain(value);
      if (value === "和家人")
        for (const c of data.candidates)
          expect(
            c.movie.genres.some((g: string) => ["家庭", "动画"].includes(g)),
          ).toBe(true);
    }
  }
  for (const minutes of [90, 120, 150]) {
    await page.getByRole("button", { name: "清空选择", exact: true }).click();
    await page
      .getByRole("group", { name: "今晚有多少时间？" })
      .getByRole("button", { name: `${minutes} 分钟内`, exact: true })
      .click();
    const { data, body } = await recommend(page, "看看候选电影");
    expect(body.constraints.max_runtime_minutes).toBe(minutes);
    for (const c of data.candidates)
      expect(c.movie.runtime_minutes).toBeLessThanOrEqual(minutes);
  }
});

test("audit: search, detail, comparison and health retries recover against real endpoints", async ({
  page,
}) => {
  const { data } = await recommend(page);
  const film = data.candidates[0].movie;
  await page.route(
    "**/api/movies?**",
    (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: '{"detail":"source temporarily unavailable"}',
      }),
    { times: 1 },
  );
  await page.getByRole("tab", { name: "已知道片名", exact: true }).click();
  await page.getByLabel("影片名称", { exact: true }).fill(film.title);
  await page.getByRole("button", { name: "查找影片", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "重新尝试", exact: true }).click();
  await expect(page.locator(".lookup-item").first()).toBeVisible();
  let failDetail = true;
  await page.route("**/api/movies/*", (route) =>
    failDetail
      ? route.fulfill({
          status: 503,
          contentType: "application/json",
          body: '{"detail":"source temporarily unavailable"}',
        })
      : route.continue(),
  );
  await page.goto(`/film/${encodeURIComponent(film.movie_id)}`);
  await expect(page.getByRole("alert")).toBeVisible();
  failDetail = false;
  await page.getByRole("button", { name: "重新尝试", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: film.title, exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "回选片室", exact: true }).click();
  await recommend(page);
  const checks = page.locator(".candidate-grid").getByRole("checkbox");
  await checks.nth(0).check();
  await checks.nth(1).check();
  let failComparison = true;
  await page.route("**/api/comparisons", (route) =>
    failComparison
      ? route.fulfill({
          status: 503,
          contentType: "application/json",
          body: '{"detail":"source temporarily unavailable"}',
        })
      : route.continue(),
  );
  await page.getByRole("link", { name: "开始对比", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  failComparison = false;
  await page.getByRole("button", { name: "重新尝试", exact: true }).click();
  await expect(page.getByRole("table")).toBeVisible();
  let failHealth = true;
  await page.route("**/api/health", (route) =>
    failHealth
      ? route.fulfill({
          status: 503,
          contentType: "application/json",
          body: '{"detail":"source temporarily unavailable"}',
        })
      : route.continue(),
  );
  await page.getByRole("link", { name: "查看接入状态", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  failHealth = false;
  await page.getByRole("button", { name: "重新尝试", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "当前服务声明", exact: true }),
  ).toBeVisible();
});
