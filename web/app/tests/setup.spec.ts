import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixture from "../../../contracts/examples/success.json" with { type: "json" };

const screenshots = "../../artifacts/local-model/chrome";

test("OFFLINE setup makes TMDB optional, fits and follows the OS", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/configuration", (route) =>
    route.fulfill({
      json: {
        catalog_provider: "apple",
        intent_method: "rules-v1",
        model_location: "rules",
        model_name: null,
        tmdb: {
          state: "not_configured",
          missing: ["TMDB_READ_TOKEN"],
          live_verified: false,
        },
        llm: {
          state: "not_configured",
          missing: ["LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"],
          live_verified: false,
        },
      },
    }),
  );
  await page.goto("/about");
  await page.getByRole("link", { name: /本机运行配置与接入指引/ }).click();
  await expect(page).toHaveURL(/\/setup$/);
  await expect(
    page.getByRole("heading", { name: "本机运行配置", exact: true }),
  ).toBeVisible();
  const status = page.getByRole("region", { name: "当前配置状态" });
  await expect(status.getByText("未配置", { exact: true })).toHaveCount(1);
  await expect(status).toContainText("LLM_API_KEY");
  await expect(status).toContainText("无需 TMDB token");
  await expect(status).not.toContainText("TMDB_READ_TOKEN");
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
  await page.getByText("可选：改用 TMDB 或云模型", { exact: true }).click();
  await expect(
    page.getByRole("link", { name: /打开 TMDB API 设置/ }),
  ).toHaveAttribute("href", "https://www.themoviedb.org/settings/api");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-setup.png`,
    fullPage: true,
  });
  const before = await page
    .locator("body")
    .evaluate((el) => getComputedStyle(el).backgroundColor);
  try {
    await page.emulateMedia({
      colorScheme: info.project.use.colorScheme === "dark" ? "light" : "dark",
    });
    await expect
      .poll(() =>
        page
          .locator("body")
          .evaluate((el) => getComputedStyle(el).backgroundColor),
      )
      .not.toBe(before);
    await page.getByRole("button", { name: "刷新状态" }).focus();
    await page.keyboard.press("Enter");
    await expect(status.getByText("未配置", { exact: true })).toHaveCount(1);
    expect(errors).toEqual([]);
  } finally {
    await page.emulateMedia({
      colorScheme: info.project.use.colorScheme === "dark" ? "dark" : "light",
    });
  }
});

test("OFFLINE setup distinguishes partial/filled config and recovers from a visible API error", async ({
  page,
}) => {
  let calls = 0;
  let failing = true;
  await page.route("**/api/configuration", (route) => {
    calls += 1;
    return failing
      ? route.fulfill({
          status: 503,
          json: {
            code: "UPSTREAM_UNAVAILABLE",
            message: "测试注入的服务故障",
            trace_id: "offline-setup",
            retryable: true,
          },
        })
      : route.fulfill({
          json: {
            catalog_provider: "tmdb",
            intent_method: "rules-v1",
            tmdb: { state: "configured", missing: [], live_verified: false },
            llm: {
              state: "incomplete",
              missing: ["LLM_API_KEY"],
              live_verified: false,
            },
          },
        });
  });
  await page.goto("/setup");
  await expect(page.getByRole("alert")).toBeVisible();
  failing = false;
  await page.getByRole("button", { name: "重新尝试" }).click();
  const status = page.getByRole("region", { name: "当前配置状态" });
  await expect(status).toContainText("已填写 · 待联网验证");
  await expect(status).toContainText("配置不完整");
  await expect(status).toContainText("TMDB");
  expect(calls).toBeGreaterThanOrEqual(2);
});

test("OFFLINE TMDB keeps provider links, rating evidence and official attribution", async ({
  page,
}) => {
  const data = structuredClone(fixture);
  data.candidates = data.candidates.slice(0, 1);
  const candidate = data.candidates[0];
  candidate.movie.movie_id = "tmdb:101";
  candidate.movie.title = "离线 TMDB 适配验收";
  candidate.movie.ratings[0].source = "TMDB";
  Object.assign(candidate.movie, {
    source_url: "https://www.themoviedb.org/movie/101",
    poster_url: "https://image.tmdb.org/t/p/w500/fixture.jpg",
  });
  data.evidence = data.evidence.filter((e) =>
    candidate.reason.evidence_ids.includes(e.evidence_id),
  );
  for (const e of data.evidence) {
    e.movie_id = candidate.movie.movie_id;
    e.source = "TMDB";
    e.url = "https://www.themoviedb.org/movie/101";
  }
  data.warnings = ["离线合成适配验收，不代表 TMDB 联网通过。"];
  await page.route("**/api/health", async (route) => {
    const response = await route.fetch();
    const health = await response.json();
    await route.fulfill({
      json: {
        ...health,
        provider: "TMDB",
        capabilities: { ...health.capabilities, ratings: true },
      },
    });
  });
  await page.route("**/api/recommendations", (route) =>
    route.fulfill({ json: data }),
  );
  // An explicit failed-image fixture also proves the TMDB image URL was requested.
  let posterRequested = false;
  await page.route("https://image.tmdb.org/**", (route) => {
    posterRequested = true;
    return route.abort();
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "什么都行，直接看看", exact: true })
    .click();
  const card = page.locator(".candidate-grid > article");
  await expect(card).toHaveCount(1);
  await expect(
    card.getByRole("link", { name: "在 TMDB 核对影片资料" }),
  ).toHaveAttribute("href", "https://www.themoviedb.org/movie/101");
  await expect(card).toContainText("TMDB");
  await expect(card).toContainText("海报加载失败");
  expect(posterRequested).toBe(true);
  await card
    .getByRole("button", { name: "核对理由与来源", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("TMDB");
  await page.getByRole("button", { name: "关闭来源面板" }).click();
  await page.goto("/about");
  const logo = page.getByRole("img", { name: "The Movie Database (TMDB)" });
  await expect(logo).toBeVisible();
  await expect
    .poll(() =>
      logo.evaluate(
        (el: HTMLImageElement) => el.complete && el.naturalWidth > 0,
      ),
    )
    .toBe(true);
  await expect(page.getByText(/This product uses the TMDB API/)).toBeVisible();
});
