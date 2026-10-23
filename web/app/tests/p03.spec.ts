import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixture from "../../../contracts/examples/success.json" with { type: "json" };
import type { Recommendation } from "../src/domain";

const screenshots =
  process.env.ACCEPTANCE_SCREENSHOT_DIR ?? "../../docs/frontend/screenshots";
const offline = () => structuredClone(fixture) as Recommendation;
async function accessible(page: Page) {
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}
async function submit(page: Page, name = "什么都行，直接看看") {
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/recommendations") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name, exact: true }).click();
  const received = await response;
  expect(received.status()).toBe(200);
  return (await received.json()) as Recommendation;
}

test("P03 real evidence drawer: provenance, focus, close and OS theme", async ({
  page,
}, info) => {
  await page.goto("/");
  await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false");
  await page
    .getByRole("button", { name: "我有一点想法", exact: true })
    .click();
  const data = await submit(page);
  expect(["live", "cached"]).toContain(data.data_mode);
  expect(data.candidates.length).toBe(3);
  expect(
    data.candidates.every(
      (c) => c.movie.movie_id.startsWith("itunes:") && !c.movie.ratings?.length,
    ),
  ).toBe(true);
  const card = page.locator(".candidate-grid > article").first();
  const trigger = card.getByRole("button", {
    name: "核对理由与来源",
    exact: true,
  });
  await trigger.click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toContainText(data.candidates[0].movie.title);
  await expect(drawer).toContainText("仅 1 个来源站点");
  await expect(drawer).toContainText("豆瓣评分未获取");
  await expect(drawer).toContainText("尚未获取来源观点");
  const evidence = data.evidence.find(
    (e) => e.movie_id === data.candidates[0].movie.movie_id,
  )!;
  await expect(drawer.locator("time").first()).toHaveAttribute(
    "datetime",
    evidence.retrieved_at,
  );
  await expect(
    drawer.getByRole("link", { name: "查看原始来源" }).first(),
  ).toHaveAttribute("href", evidence.url);
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    expect(
      await drawer.evaluate((el) => el.contains(document.activeElement)),
    ).toBe(true);
  }
  await accessible(page);
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-evidence-live.png`,
  });
  const originalTheme = info.project.use.colorScheme ?? "light";
  const before = await drawer.evaluate(
    (el) => getComputedStyle(el).backgroundColor,
  );
  try {
    await page.emulateMedia({
      colorScheme: originalTheme === "dark" ? "light" : "dark",
    });
    await expect
      .poll(() => drawer.evaluate((el) => getComputedStyle(el).backgroundColor))
      .not.toBe(before);
  } finally {
    await page.emulateMedia({ colorScheme: originalTheme });
  }
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await trigger.click();
  await page.getByRole("button", { name: "关闭来源面板" }).click();
  await expect(trigger).toBeFocused();
  await info.attach("P03 real evidence response", {
    body: JSON.stringify(data, null, 2),
    contentType: "application/json",
  });
});

for (const count of [0, 1, 2, 3])
  test(`P03 OFFLINE contract UI: ${count} candidates and nullable metadata`, async ({
    page,
  }) => {
    const data = offline();
    data.candidates = data.candidates.slice(0, count);
    data.status = count ? "ready" : "empty";
    data.warnings = ["离线合成契约验收，不代表真实推荐。"];
    data.evidence = data.evidence.filter((e) =>
      data.candidates.some((c) => c.movie.movie_id === e.movie_id),
    );
    for (const c of data.candidates) {
      c.movie.runtime_minutes = null;
      c.movie.year = null;
      c.movie.ratings = [];
    }
    await page.route("**/api/recommendations", (r) =>
      r.fulfill({ json: data }),
    );
    await page.goto("/");
    await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false");
    await page
      .getByRole("button", { name: "我有一点想法", exact: true })
      .click();
    await submit(page);
    await expect(page.locator(".candidate-grid > article")).toHaveCount(count);
    await expect(
      page.getByText("离线合成契约验收，不代表真实推荐。", { exact: true }),
    ).toBeVisible();
    if (count) {
      await expect(page.locator(".candidate-grid")).toContainText("片长未知");
      await page
        .getByRole("button", { name: "核对理由与来源", exact: true })
        .first()
        .click();
      await expect(page.getByRole("dialog")).toContainText("离线合成样例");
      await accessible(page);
      await page.getByRole("button", { name: "关闭来源面板" }).click();
    } else await accessible(page);
  });

test("P03 OFFLINE multi-platform provenance, long prose, unsafe links and spoiler consent", async ({
  page,
}, info) => {
  const data = offline();
  data.candidates = data.candidates.slice(0, 1);
  const candidate = data.candidates[0];
  const base = data.evidence[0];
  data.evidence = [base];
  candidate.movie.title = "离线证据验收：长片名".repeat(12);
  candidate.reason.text = "这段是匹配推断，不是来源观点。";
  candidate.reason.kind = "matching_inference";
  candidate.movie.ratings = [
    {
      source: "豆瓣",
      value: 8.2,
      scale: 10,
      vote_count: 1200,
      evidence_id: "douban-score",
    },
    {
      source: "IMDb",
      value: 77,
      scale: 100,
      vote_count: null,
      evidence_id: "imdb-score",
    },
  ];
  data.evidence.push(
    {
      ...base,
      evidence_id: "douban-score",
      source: "豆瓣",
      kind: "rating",
      url: "https://movie.douban.com/subject/1/",
    },
    {
      ...base,
      evidence_id: "imdb-score",
      source: "IMDb",
      kind: "rating",
      url: "https://www.imdb.com/title/test/",
    },
    {
      ...base,
      evidence_id: "opinion-a",
      source: "离线观点 A",
      kind: "review",
      url: "https://example.invalid/a",
      claim: "来源观点保持原文，不计算综合分。".repeat(45),
    },
    {
      ...base,
      evidence_id: "opinion-b",
      source: "离线观点 B",
      kind: "review",
      url: "javascript:alert(1)",
      spoiler_level: "contains_spoilers",
      claim: "离线剧透内容，只有主动展开才显示。",
    },
  );
  await page.route("**/api/recommendations", (r) => r.fulfill({ json: data }));
  await page.goto("/");
  await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false");
  await page
    .getByRole("button", { name: "我有一点想法", exact: true })
    .click();
  await submit(page);
  const scores = page.locator(".candidate-grid").getByTestId("source-rating");
  await expect(scores).toHaveCount(2);
  await expect(scores.nth(0)).toContainText("8.2 / 10");
  await expect(scores.nth(1)).toContainText("77 / 100");
  await page
    .getByRole("button", { name: "核对理由与来源", exact: true })
    .click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toContainText("来源独立性尚未核验");
  await expect(
    drawer.locator('a[href^="javascript:"],a[href*=".invalid"]'),
  ).toHaveCount(0);
  await expect(
    drawer.getByText("离线剧透内容，只有主动展开才显示。", { exact: true }),
  ).toHaveCount(0);
  await drawer.getByRole("button", { name: "仍要展开这条内容" }).click();
  await expect(
    drawer.getByText("离线剧透内容，只有主动展开才显示。", { exact: true }),
  ).toBeVisible();
  await drawer.getByRole("button", { name: "收起剧透内容" }).click();
  await expect(
    drawer.getByText("离线剧透内容，只有主动展开才显示。", { exact: true }),
  ).toHaveCount(0);
  await accessible(page);
  await drawer.evaluate((el) => el.scrollTo(0, 0));
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-evidence-offline-multisource.png`,
  });
});

test("P04 OFFLINE comparison keeps selected evidence through reroll and undo", async ({
  page,
}, info) => {
  const first = offline();
  const later = offline();
  for (const [i, c] of later.candidates.entries()) {
    const id = `syn:later-${i}`;
    c.movie.movie_id = id;
    c.movie.ratings = [];
    c.reason.text = "后来的结果，不应替换已选证据。";
    later.evidence[i].movie_id = id;
  }
  let calls = 0;
  await page.route("**/api/recommendations", (r) =>
    r.fulfill({ json: ++calls === 1 ? first : later }),
  );
  await page.route("**/api/comparisons", (r) =>
    r.fulfill({
      json: {
        contract_version: "0.1.0",
        data_mode: "synthetic",
        movies: first.candidates.slice(0, 2).map((c) => c.movie),
      },
    }),
  );
  await page.goto("/");
  await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false");
  await page
    .getByRole("button", { name: "我有一点想法", exact: true })
    .click();
  const checks = page.locator(".candidate-grid").getByRole("checkbox");
  await checks.nth(0).check();
  await checks.nth(1).check();
  await submit(page, "换一组真实电影");
  await page.getByRole("link", { name: "开始对比", exact: true }).click();
  await expect(page.getByRole("row", { name: /推荐理由/ })).toContainText(
    first.candidates[0].reason.text,
  );
  await expect(page.getByRole("row", { name: /推荐理由/ })).not.toContainText(
    "后来的结果",
  );
  await page
    .getByRole("button", { name: "核对理由与来源", exact: true })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText(first.evidence[0].claim);
  await accessible(page);
  await page.getByRole("button", { name: "关闭来源面板" }).click();
  await page.getByRole("link", { name: "偏好与隐私", exact: true }).click();
  await page.getByRole("button", { name: "清空本次片单与对比" }).click();
  await page.getByRole("button", { name: "撤销", exact: true }).click();
  await page.getByRole("link", { name: "开始对比", exact: true }).click();
  await expect(page.getByRole("row", { name: /推荐理由/ })).toContainText(
    first.candidates[0].reason.text,
  );
  await accessible(page);
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-comparison-evidence.png`,
    fullPage: true,
  });
});

test("P03 OFFLINE invalid rating provenance is rejected without replacing earlier results", async ({
  page,
}) => {
  const valid = offline();
  const invalid = offline();
  invalid.candidates[0].movie.ratings![0].evidence_id = "syn:e2";
  let calls = 0;
  await page.route("**/api/recommendations", (r) =>
    r.fulfill({ json: ++calls === 1 ? valid : invalid }),
  );
  await page.goto("/");
  await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false");
  await page
    .getByRole("button", { name: "我有一点想法", exact: true })
    .click();
  await submit(page, "换一组真实电影");
  await expect(page.getByRole("alert")).toContainText("缺少可核对的安全来源");
  await expect(page.locator(".candidate-grid > article")).toHaveCount(3);
  await expect(page.locator(".candidate-grid")).toContainText(
    valid.candidates[0].movie.title,
  );
});
