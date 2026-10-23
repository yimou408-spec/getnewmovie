import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const screenshots =
  process.env.ACCEPTANCE_SCREENSHOT_DIR ??
  "../../docs/frontend/screenshots/refinement";

test("real refinement: remove one condition, submit it and return without losing results", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false");
  await page
    .getByRole("button", { name: "我有一点想法", exact: true })
    .click();
  const input = page.getByLabel("说说今晚想看什么（可选）", { exact: true });
  const mood = page.getByRole("group", { name: "想要什么感觉？" });
  const genre = page.getByRole("group", { name: "想看哪种故事？" });
  const duration = page.getByRole("group", { name: "今晚有多少时间？" });
  // Point-and-click choices must precede the optional text in reading order.
  expect(
    await duration.evaluate((element) =>
      Boolean(
        element.compareDocumentPosition(document.querySelector("#mood")!) &
        Node.DOCUMENT_POSITION_FOLLOWING,
      ),
    ),
  ).toBe(true);
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-home.png`,
    fullPage: true,
  });
  await mood.getByRole("button", { name: "温暖治愈", exact: true }).click();
  await genre.getByRole("button", { name: "喜剧", exact: true }).click();
  await duration
    .getByRole("button", { name: "120 分钟内", exact: true })
    .click();
  await page
    .getByRole("button", { name: "移除条件 喜剧", exact: true })
    .click();
  await expect(
    genre.getByRole("button", { name: "喜剧", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await expect(
    mood.getByRole("button", { name: "温暖治愈", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await genre.getByRole("button", { name: "剧情", exact: true }).click();
  await expect(input).toHaveValue("");
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/recommendations") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "看看候选电影", exact: true }).click();
  const response = await responsePromise;
  expect(response.status(), await response.text()).toBe(200);
  const request = response.request().postDataJSON();
  expect(request.constraints.genres).toEqual(["剧情"]);
  expect(request.constraints.moods).toEqual(["温暖治愈"]);
  expect(request.constraints.max_runtime_minutes).toBe(120);
  const data = await response.json();
  await info.attach("real refinement request and response", {
    body: JSON.stringify({ request, response: data }, null, 2),
    contentType: "application/json",
  });
  expect(["live", "cached"]).toContain(data.data_mode);
  expect(data.candidates.length).toBeGreaterThan(0);
  expect(
    data.candidates.every(
      (candidate: any) =>
        candidate.movie.movie_id.startsWith("itunes:") &&
        candidate.movie.genres.includes("剧情") &&
        candidate.movie.runtime_minutes <= 120,
    ),
  ).toBe(true);
  const cards = page.locator(".candidate-grid > article");
  await expect(cards).toHaveCount(data.candidates.length);
  await page.locator(".candidate-grid").scrollIntoViewIfNeeded();
  for (const image of await cards.locator(".poster img").all()) {
    await image.scrollIntoViewIfNeeded();
    await expect
      .poll(
        () =>
          image.evaluate(
            (element: HTMLImageElement) =>
              element.complete && element.naturalWidth > 0,
          ),
        { timeout: 20000 },
      )
      .toBe(true);
  }
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-results.png`,
    fullPage: true,
  });
  let unexpectedRequests = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/recommendations")) unexpectedRequests++;
  });
  await page.getByRole("button", { name: "修改选片条件", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "精细选片", exact: true }),
  ).toBeFocused();
  await expect(
    genre.getByRole("button", { name: "剧情", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(cards).toHaveCount(data.candidates.length);
  expect(unexpectedRequests).toBe(0);
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
  expect(errors).toEqual([]);
});

test("film-first home loads real films before asking for input and rerolls", async ({ page }, info) => {
  const response = page.waitForResponse((r) => r.url().endsWith("/api/recommendations") && r.request().method() === "POST");
  await page.goto("/");
  const initial = await response;
  expect(initial.status()).toBe(200);
  const data = await initial.json();
  expect(["live", "cached"]).toContain(data.data_mode);
  await expect(page.locator(".stage-film")).toHaveCount(3);
  await expect(page.locator(".filter-workbench")).not.toHaveAttribute("open");
  await expect(page.getByLabel("说说今晚想看什么（可选）", { exact: true })).not.toBeVisible();
  for (const image of await page.locator(".poster-stage img").all()) {
    await expect.poll(() => image.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0), { timeout: 20000 }).toBe(true);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `${screenshots}/${info.project.name}-film-first.png`, fullPage: true });
  const next = page.waitForResponse((r) => r.url().endsWith("/api/recommendations") && r.request().method() === "POST");
  await page.getByRole("button", { name: "换一组真实电影", exact: true }).click();
  const rerolled = await next;
  expect(rerolled.status()).toBe(200);
  const ids = data.candidates.map((c: any) => c.movie.movie_id);
  expect(rerolled.request().postDataJSON().constraints.exclude_movie_ids).toEqual(expect.arrayContaining(ids));
  expect((await rerolled.json()).candidates.every((c: any) => !ids.includes(c.movie.movie_id))).toBe(true);
  await page.getByRole("button", { name: "我有一点想法", exact: true }).click();
  await expect(page.getByRole("heading", { name: "精细选片", exact: true })).toBeFocused();
  await expect(page.locator(".filter-workbench")).toHaveAttribute("open", "");
});
