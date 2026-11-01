import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const screenshots =
  process.env.ACCEPTANCE_SCREENSHOT_DIR ?? "../../docs/frontend/screenshots";
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  // A page can hide left-clipped content without increasing its scrollWidth.
  // Keep reasons, ratings, sources and actions inside each candidate card.
  expect(
    await page.locator(".candidate-grid > article").evaluateAll((cards) =>
      cards.every((card) => {
        const bounds = card.getBoundingClientRect();
        return Array.from(card.querySelectorAll(".movie-body > *")).every(
          (element) => {
            const content = element.getBoundingClientRect();
            return (
              content.height === 0 ||
              (content.left >= bounds.left && content.right <= bounds.right)
            );
          },
        );
      }),
    ),
  ).toBe(true);
}
async function accessible(page: Page) {
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
}
async function submit(page: Page, name: string | RegExp = "看看候选电影") {
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/recommendations") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name, exact: typeof name === "string" })
    .click();
  const r = await response;
  expect(r.status()).toBe(200);
  const data = await r.json();
  expect(["live", "cached"]).toContain(data.data_mode);
  expect(
    data.candidates.every(
      (c: any) =>
        c.movie.movie_id.startsWith("itunes:") && c.movie.ratings.length === 0,
    ),
  ).toBe(true);
  await expect(page.locator(".candidate-grid > article")).toHaveCount(
    data.candidates.length,
  );
  return data;
}
test.beforeEach(async ({ page }) => {
  expect(
    (await (await page.request.get("/api/health")).json()).synthetic_fallback,
  ).toBe(false);
  await page.goto("/");
  // A cold real catalog can load until the client's 45-second request timeout.
  await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false", {
    timeout: 50000,
  });
  await page.getByRole("button", { name: "我有一点想法", exact: true }).click();
});
test("real catalog, artwork, sources, watchlist and comparison", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await accessible(page);
  await noOverflow(page);
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-home.png`,
    fullPage: true,
  });
  const data = await submit(page, "什么都行，直接看看");
  expect(data.catalog_size).toBeGreaterThan(3);
  expect(data.candidates).toHaveLength(3);
  for (const img of await page.locator(".candidate-grid .poster img").all()) {
    await img.scrollIntoViewIfNeeded();
    await expect
      .poll(
        () =>
          img.evaluate(
            (el: HTMLImageElement) => el.complete && el.naturalWidth > 0,
          ),
        { timeout: 20000 },
      )
      .toBe(true);
  }
  expect(await page.locator(".candidate-grid .store-badge").count()).toBe(3);
  await page.getByText("核对理由与来源", { exact: true }).first().click();
  await expect(
    page.locator('.candidate-grid a[href*="itunes.apple.com"]').first(),
  ).toHaveAttribute("href", /^https:\/\/itunes.apple.com\//);
  await accessible(page);
  await page.getByRole("button", { name: "关闭来源面板" }).click();
  await noOverflow(page);
  await page.locator(".discovery-hero").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-result.png`,
    fullPage: true,
  });
  await page.locator(".candidate-grid").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-result-viewport.png`,
  });
  await page
    .getByRole("button", { name: "加入本次片单", exact: true })
    .first()
    .click();
  const checks = page.locator(".candidate-grid").getByRole("checkbox");
  await checks.nth(0).check();
  await checks.nth(1).check();
  await page.getByRole("link", { name: "开始对比", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "影片对比表，可左右滚动" }),
  ).toBeVisible();
  for (const c of data.candidates.slice(0, 2))
    await expect(
      page.getByRole("columnheader", {
        name: new RegExp(c.movie.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
      }),
    ).toBeVisible();
  await accessible(page);
  await noOverflow(page);
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-compare.png`,
    fullPage: true,
  });
  await page.getByRole("link", { name: "偏好与隐私", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "建立匿名身份并启用记忆" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("checkbox", { name: /同意在本机保存匿名身份/ }),
  ).not.toBeChecked();
  await page.getByRole("button", { name: "清空本次片单与对比" }).click();
  await expect(page.locator(".compare-tray")).toHaveCount(0);
  expect(errors).toEqual([]);
});
test("mood, genre and duration change real candidates; empty is honest", async ({
  page,
}, info) => {
  await page
    .getByRole("group", { name: "想要什么感觉？" })
    .getByRole("button", { name: "轻松解压", exact: true })
    .click();
  await page
    .getByRole("group", { name: "想看哪种故事？" })
    .getByRole("button", { name: "喜剧", exact: true })
    .click();
  await page
    .getByRole("group", { name: "今晚有多少时间？" })
    .getByRole("button", { name: "90 分钟内", exact: true })
    .click();
  const comedy = await submit(page, "看看候选电影");
  expect(comedy.candidates.length).toBeGreaterThan(0);
  for (const c of comedy.candidates) {
    expect(c.movie.genres).toContain("喜剧");
    expect(c.movie.runtime_minutes).toBeLessThanOrEqual(90);
    expect(c.movie.runtime_minutes).toBeGreaterThan(0);
  }
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-choices.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "清空选择", exact: true }).click();
  await page
    .getByRole("group", { name: "想要什么感觉？" })
    .getByRole("button", { name: "感动一下", exact: true })
    .click();
  const drama = await submit(page, "看看候选电影");
  expect(drama.candidates.length).toBeGreaterThan(0);
  expect(drama.candidates.map((c: any) => c.movie.movie_id)).not.toEqual(
    comedy.candidates.map((c: any) => c.movie.movie_id),
  );
  for (const c of drama.candidates) expect(c.movie.genres).toContain("剧情");
  await page
    .getByRole("group", { name: "想看哪种故事？" })
    .getByRole("button", { name: "恐怖", exact: true })
    .click();
  // A mood is soft: it must not intersect away an explicit genre.
  const horror = await submit(page, "看看候选电影");
  expect(horror.candidates.length).toBeGreaterThan(0);
  for (const c of horror.candidates) expect(c.movie.genres).toContain("恐怖");
  await page.getByText("精确时长与观看地区（可选）", { exact: true }).click();
  await page.getByLabel("最多看多久", { exact: false }).fill("1");
  const empty = await submit(page, "看看候选电影");
  expect(empty.status).toBe("empty");
  await expect(
    page.getByRole("heading", { name: "这次还没有合适的候选" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "清空筛选条件" }).click();
  expect((await submit(page)).candidates.length).toBe(3);
  const previous = await page.locator(".candidate-grid h3").allTextContents();
  await submit(page, "换一组真实电影");
  expect(
    await page.locator(".candidate-grid h3").allTextContents(),
  ).not.toEqual(previous);
});
test("era, ranking choice and session exclusions survive a fresh submission", async ({
  page,
}) => {
  const ordering = page.getByRole("group", { name: "怎么安排候选？" });
  await ordering.getByRole("button", { name: "榜单顺序", exact: true }).click();
  const request = page.waitForRequest(
    (r) => r.url().endsWith("/api/recommendations") && r.method() === "POST",
  );
  const first = await submit(page);
  expect((await request).postDataJSON().constraints.sort_by).toBe("popular");
  const rejected = first.candidates[0].movie.movie_id;
  await page
    .locator(".candidate-grid > article")
    .first()
    .getByRole("button", { name: "这次不想看", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "撤销本次排除", exact: true }),
  ).toBeVisible();
  await ordering.getByRole("button", { name: "均衡探索", exact: true }).click();
  const retry = page.waitForRequest(
    (r) => r.url().endsWith("/api/recommendations") && r.method() === "POST",
  );
  const second = await submit(page);
  expect((await retry).postDataJSON().constraints).toMatchObject({
    sort_by: "balanced",
    exclude_movie_ids: [rejected],
  });
  expect(second.candidates.map((c: any) => c.movie.movie_id)).not.toContain(
    rejected,
  );
  await page.getByRole("button", { name: "撤销本次排除", exact: true }).click();
  const group = page.getByRole("group", { name: "想看哪个年代？" });
  await group.getByRole("button", { name: "2000 年以前", exact: true }).click();
  const classic = await submit(page);
  expect(classic.candidates.length).toBeGreaterThan(0);
  expect(classic.candidates.every((c: any) => c.movie.year < 2000)).toBe(true);
  await noOverflow(page);
  await accessible(page);
});
test("real identity lookup, known film, watchlist and reload boundary", async ({
  page,
}) => {
  const data = await submit(page);
  const film = data.candidates[0].movie;
  await page.getByRole("tab", { name: "已知道片名", exact: true }).click();
  await page.getByLabel("影片名称", { exact: true }).fill(film.title);
  const response = page.waitForResponse(
    (r) => r.url().includes("/api/movies?") && r.request().method() === "GET",
  );
  await page.getByRole("button", { name: "查找影片", exact: true }).click();
  expect((await response).status()).toBe(200);
  await page
    .locator(".lookup-item")
    .filter({ hasText: film.title })
    .getByRole("button", { name: "确认这部", exact: true })
    .first()
    .click();
  const known = await submit(page, "看看候选电影");
  expect(known.candidates[0].movie.movie_id).toBe(film.movie_id);
  await page
    .getByRole("button", { name: "加入本次片单", exact: true })
    .first()
    .click();
  await page.getByRole("tab", { name: "从片单中选", exact: true }).click();
  const saved = await submit(page, "看看候选电影");
  expect(saved.candidates.map((c: any) => c.movie.movie_id)).toEqual([
    film.movie_id,
  ]);
  await page.reload();
  await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false");
  await page.getByRole("button", { name: "我有一点想法", exact: true }).click();
  await page.getByRole("link", { name: /本次片单/ }).click();
  await expect(
    page.getByRole("button", { name: "移出本次片单", exact: true }),
  ).toHaveCount(0);
});
test("failed or invalid source response preserves real results; poster failure is visible", async ({
  page,
}) => {
  const data = await submit(page);
  const title = data.candidates[0].movie.title;
  await page.route("**/api/recommendations", (r) => r.abort("failed"));
  await page.getByRole("button", { name: "看看候选电影", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("连接失败");
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await page.unroute("**/api/recommendations");
  await page.route("**/api/recommendations", (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: '{"status":"ready","candidates":[]}',
    }),
  );
  await page.getByRole("button", { name: "看看候选电影", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("接口约定不一致");
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await page.unroute("**/api/recommendations");
  await page.route("**/api/artwork/**", (r) => r.abort());
  await page.reload();
  await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false");
  await page.getByRole("button", { name: "我有一点想法", exact: true }).click();
  await submit(page);
  for (const poster of await page.locator(".candidate-grid .poster").all())
    await poster.scrollIntoViewIfNeeded();
  await expect(
    page.locator(".candidate-grid").getByText("海报加载失败", { exact: true }),
  ).toHaveCount(3);
});
test("system theme changes immediately, keyboard focus and narrow layout", async ({
  page,
}, info) => {
  await page.emulateMedia({ colorScheme: "light" });
  const light = await page
    .locator("body")
    .evaluate((e) => getComputedStyle(e).backgroundColor);
  await page.emulateMedia({ colorScheme: "dark" });
  await expect
    .poll(() =>
      page.locator("body").evaluate((e) => getComputedStyle(e).backgroundColor),
    )
    .not.toBe(light);
  await page.emulateMedia({
    colorScheme: info.project.name.includes("dark") ? "dark" : "light",
  });
  await page.reload();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "跳到主要内容" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false");
  await page.getByRole("button", { name: "我有一点想法", exact: true }).click();
  await submit(page);
  try {
    await page.setViewportSize(
      info.project.name.startsWith("mobile")
        ? { width: 320, height: 720 }
        : { width: 1920, height: 1080 },
    );
    await noOverflow(page);
    await accessible(page);
    await page.screenshot({
      path: `${screenshots}/${info.project.name}-${info.project.name.startsWith("mobile") ? "320" : "1920"}.png`,
      fullPage: true,
    });
  } finally {
    await page.setViewportSize({ width: 1440, height: 1000 });
    expect(page.viewportSize()).toEqual({ width: 1440, height: 1000 });
  }
});
test("stalled artwork times out and can be retried without losing the film", async ({
  page,
}, info) => {
  await page.clock.install();
  let pending = true;
  let requests = 0;
  await page.route("**/api/artwork/**", async (route) => {
    requests += 1;
    if (pending) await new Promise(() => {});
    else await route.abort();
  });
  await page.reload();
  await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false");
  await page.getByRole("button", { name: "我有一点想法", exact: true }).click();
  const data = await submit(page);
  await expect(
    page.locator(".candidate-grid").getByText("海报加载中…", { exact: true }),
  ).toHaveCount(3);
  await page.clock.fastForward(12001);
  await expect(
    page.locator(".candidate-grid").getByText("海报加载超时", { exact: true }),
  ).toHaveCount(3);
  await expect(
    page.getByRole("heading", {
      name: data.candidates[0].movie.title,
      exact: true,
    }),
  ).toBeVisible();
  const before = requests;
  pending = false;
  await page
    .locator(".candidate-grid")
    .getByRole("button", { name: /^重试 .* 海报$/ })
    .first()
    .click();
  await expect.poll(() => requests).toBeGreaterThan(before);
  await expect(
    page.locator(".candidate-grid").getByText("海报加载失败", { exact: true }),
  ).toHaveCount(1);
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: `../../artifacts/live-catalog/${info.project.name}-artwork-timeout.png`,
  });
  await page.unroute("**/api/artwork/**");
  await page
    .locator(".candidate-grid")
    .getByRole("button", { name: /^重试 .* 海报$/ })
    .first()
    .click();
  await expect
    .poll(
      () =>
        page
          .locator(".candidate-grid .poster img")
          .first()
          .evaluate(
            (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
          ),
      { timeout: 20000 },
    )
    .toBe(true);
});
test("unknown identities and scope documentation remain explicit", async ({
  page,
}) => {
  const lookup = page.waitForResponse((response) =>
    response.url().endsWith("/api/movies/itunes%3A1"),
  );
  await page.goto("/film/itunes%3A1");
  const result = await lookup;
  if (
    result.status() === 503 &&
    (await result.json()).code === "UPSTREAM_RATE_LIMIT"
  ) {
    test.setTimeout(180000);
    await expect(page.getByRole("alert")).toContainText("一分钟后重试");
    // Respect the actual provider's minute quota; retry the UI only once.
    await page.waitForTimeout(61000);
    await page.getByRole("button", { name: "重新尝试", exact: true }).click();
  }
  await expect(page.getByRole("alert")).toContainText("影片");
  await page.goto("/about");
  const scopeTable = page
    .getByRole("region", { name: "页面功能与使用边界" })
    .getByRole("table");
  await expect(scopeTable).toContainText("Apple 美国区公开数据");
  await expect(scopeTable).toContainText("尚未实现");
  await accessible(page);
  await page.goto("/unknown");
  await expect(
    page.getByRole("heading", { name: "这一页还没有开场" }),
  ).toBeVisible();
});
