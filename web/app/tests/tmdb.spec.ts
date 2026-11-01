import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixture from "../../../contracts/examples/success.json" with { type: "json" };
import type { Recommendation } from "../src/domain";

test("TMDB OFFLINE metadata: provenance, attribution and responsive source drawer", async ({
  page,
}, info) => {
  // Invented TMDB text verifies UI behavior only; no real identity or HTTP claims.
  const data = structuredClone(fixture) as Recommendation;
  data.candidates = data.candidates.slice(0, 1);
  const movie = data.candidates[0].movie;
  movie.ratings = [];
  data.evidence = data.evidence.filter(
    (entry) => entry.movie_id === movie.movie_id,
  );
  const extra = {
    ...data.evidence[0],
    evidence_id: "offline-tmdb-metadata",
    source: "TMDB",
    kind: "metadata" as const,
    usage_basis: "synthetic" as const,
    url: "https://www.themoviedb.org/movie/129",
    claim: "离线中文资料测试；影片别名与原片名分别展示。",
  };
  data.evidence.push(extra);
  data.source_results = [
    {
      movie_id: movie.movie_id,
      source: "TMDB",
      status: "ok",
      evidence: [extra],
      ratings: [],
      cache_status: "fresh",
      warnings: [],
    },
  ];
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/recommendations")) return route.fulfill({ json: data });
    if (path.endsWith("/sessions"))
      return route.fulfill({
        json: { session_id: "offline", expires_in_seconds: 1800 },
      });
    if (path.endsWith("/health"))
      return route.fulfill({
        json: {
          service: "real-catalog",
          provider: "Offline test",
          synthetic_fallback: false,
          cache_ttl_seconds: 1800,
          capabilities: { metadata: true, ratings: false, reviews: false },
        },
      });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto("/");
  await expect(page.locator(".candidate-grid > article")).toHaveCount(1);
  await expect(page.locator(".candidate-grid")).toContainText(
    "TMDB：已取得材料 · 缓存",
  );
  await page
    .getByRole("button", { name: "核对理由与来源", exact: true })
    .click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toContainText(extra.claim);
  await expect(drawer).toContainText("not endorsed or certified by TMDB");
  const logo = drawer.getByAltText("TMDB");
  await expect(logo).toBeVisible();
  expect(
    await logo.evaluate((image) => (image as HTMLImageElement).naturalWidth),
  ).toBeGreaterThan(0);
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
  await page.screenshot({
    path: `${process.env.ACCEPTANCE_SCREENSHOT_DIR ?? "../../artifacts/tmdb-ui"}/${info.project.name}-tmdb.png`,
  });
  await page.getByRole("button", { name: "关闭来源面板" }).click();
  await page.goto("/about");
  await expect(
    page.getByRole("region", { name: "TMDB 数据署名" }),
  ).toBeVisible();
});
