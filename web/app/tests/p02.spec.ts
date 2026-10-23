import { test, expect, type Page, type Response } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const screenshots =
  process.env.ACCEPTANCE_SCREENSHOT_DIR ?? "../../docs/frontend/screenshots";
const input = (page: Page) =>
  page.getByRole("textbox", { name: "说说今晚想看什么（可选）" });
const cards = (page: Page) => page.locator(".candidate-grid > article");
const confirm = (page: Page) =>
  page.getByRole("button", { name: "确认并继续推荐", exact: true });
async function response(page: Page, action: () => Promise<unknown>) {
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/recommendations") &&
      r.request().method() === "POST",
  );
  await action();
  return pending;
}
async function received(page: Page, r: Response) {
  if (r.status() === 503 && (await r.json()).code === "UPSTREAM_RATE_LIMIT") {
    test.setTimeout(180000);
    await expect(page.getByRole("alert")).toContainText("一分钟后重试");
    await page.waitForTimeout(61000);
    r = await response(page, () =>
      page.getByRole("button", { name: "重新尝试", exact: true }).click(),
    );
  }
  expect(r.status(), await r.text()).toBe(200);
  const data = await r.json();
  await test.info().attach("P02 request and actual response", {
    body: JSON.stringify(
      { request: r.request().postDataJSON(), response: data },
      null,
      2,
    ),
    contentType: "application/json",
  });
  expect(["live", "cached"]).toContain(data.data_mode);
  expect(
    data.candidates.every(
      (c: any) =>
        c.movie.movie_id.startsWith("itunes:") && c.movie.ratings.length === 0,
    ),
  ).toBe(true);
  await expect(cards(page)).toHaveCount(data.candidates.length);
  return data;
}
async function submit(page: Page) {
  return received(
    page,
    await response(page, () =>
      page.getByRole("button", { name: "看看候选电影", exact: true }).click(),
    ),
  );
}
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
test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("P02 real natural text changes hard conditions and soft mood, with visible interpretation", async ({
  page,
}, info) => {
  await expect(input(page)).toBeVisible();
  await input(page).fill("想看温暖治愈的喜剧，不要恐怖片，两个小时以内");
  const data = await submit(page);
  expect(data.status).toBe("ready");
  expect(data.interpretation.effective_constraints).toMatchObject({
    genres: ["喜剧"],
    moods: ["温暖治愈"],
    max_runtime_minutes: 120,
    exclude_genres: ["恐怖"],
  });
  expect(data.candidates.length).toBeGreaterThan(0);
  for (const c of data.candidates) {
    expect(c.movie.genres).toContain("喜剧");
    expect(c.movie.genres).not.toContain("恐怖");
    expect(c.movie.runtime_minutes).toBeGreaterThan(0);
    expect(c.movie.runtime_minutes).toBeLessThanOrEqual(120);
  }
  await expect(
    page.getByRole("heading", { name: "已识别条件", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".intent-summary")).toContainText("未知时长不入选");
  await accessible(page);
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-p02-natural.png`,
    fullPage: true,
  });
});

for (const choice of ["按文字条件", "按点选条件"]) {
  test(`P02 conflict really applies ${choice} before querying the catalog`, async ({
    page,
  }, info) => {
    await page
      .getByRole("group", { name: "想看哪种故事？" })
      .getByRole("button", { name: "喜剧", exact: true })
      .click();
    await input(page).fill("剧情片，120分钟以内");
    const pending = await submit(page);
    expect(pending.status).toBe("needs_clarification");
    expect(pending.evidence).toEqual([]);
    expect(pending.catalog_size).toBeNull();
    await expect(cards(page)).toHaveCount(0);
    await expect(confirm(page)).toBeDisabled();
    await page.getByRole("radio", { name: choice, exact: true }).check();
    await accessible(page);
    await page.screenshot({
      path: `${screenshots}/${info.project.name}-p02-${choice}.png`,
      fullPage: true,
    });
    const done = await received(
      page,
      await response(page, () => confirm(page).click()),
    );
    const genre = choice === "按文字条件" ? "剧情" : "喜剧";
    expect(done.status).toBe("ready");
    expect(done.interpretation.effective_constraints.genres).toEqual([genre]);
    expect(
      done.candidates.every((c: any) => c.movie.genres.includes(genre)),
    ).toBe(true);
    await expect(input(page)).toHaveValue("剧情片，120分钟以内");
    await expect(
      page
        .getByRole("group", { name: "想看哪种故事？" })
        .getByRole("button", { name: "喜剧", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
  });
}

test("P02 all clarification answers are required, unsupported rating is explicit, reroll retains consent", async ({
  page,
}) => {
  await page
    .getByRole("group", { name: "想看哪种故事？" })
    .getByRole("button", { name: "喜剧", exact: true })
    .click();
  await input(page).fill("豆瓣8分以上的剧情片，120分钟以内");
  const pending = await submit(page);
  expect(pending.questions).toHaveLength(2);
  await page.getByRole("radio", { name: "按文字条件", exact: true }).check();
  await expect(confirm(page)).toBeDisabled();
  const unsupported = page.getByRole("radio", {
    name: "仅按已识别条件继续",
    exact: true,
  });
  await unsupported.focus();
  await page.keyboard.press("Space");
  await expect(unsupported).toBeChecked();
  await expect(confirm(page)).toBeEnabled();
  await confirm(page).focus();
  const done = await received(
    page,
    await response(page, () => page.keyboard.press("Enter")),
  );
  expect(done.status).toBe("ready");
  await expect(page.locator(".results")).toContainText(
    "经你确认未采用：豆瓣8分以上",
  );
  const rerolled = await received(
    page,
    await response(page, () =>
      page.getByRole("button", { name: "换一组真实电影", exact: true }).click(),
    ),
  );
  expect(rerolled.status).not.toBe("needs_clarification");
  expect(rerolled.interpretation.effective_constraints.genres).toEqual([
    "剧情",
  ]);
  const ids = done.candidates.map((c: any) => c.movie.movie_id);
  expect(
    rerolled.candidates.every((c: any) => !ids.includes(c.movie.movie_id)),
  ).toBe(true);
});

test("P02 editing conditions invalidates clarification and duplicate submission sends once", async ({
  page,
}) => {
  await input(page).fill("豆瓣8分以上的喜剧");
  await submit(page);
  await page
    .getByRole("radio", { name: "仅按已识别条件继续", exact: true })
    .check();
  await input(page).fill("剧情片，120分钟以内");
  await expect(confirm(page)).toBeDisabled();
  await expect(page.getByText(/条件已变更或会话已过期/)).toBeVisible();
  let posts = 0;
  page.on("request", (r) => {
    if (r.url().endsWith("/api/recommendations") && r.method() === "POST")
      posts++;
  });
  const done = await received(
    page,
    await response(page, () =>
      page.locator(".composer form").evaluate((form: HTMLFormElement) => {
        form.requestSubmit();
        form.requestSubmit();
      }),
    ),
  );
  expect(posts).toBe(1);
  expect(done.interpretation.effective_constraints.genres).toEqual(["剧情"]);
});

test("P02 explicit fault injection: retry preserves the exact clarification payload", async ({
  page,
}) => {
  await input(page).fill("豆瓣8分以上的喜剧");
  await submit(page);
  await page
    .getByRole("radio", { name: "仅按已识别条件继续", exact: true })
    .check();
  await page.route(
    "**/api/recommendations",
    (route) =>
      route.fulfill({
        status: 503,
        json: {
          contract_version: "0.1.0",
          trace_id: "p02-injected-unavailable",
          data_mode: "live",
          code: "UPSTREAM_UNAVAILABLE",
          message: "Injected test failure",
          retryable: true,
        },
      }),
    { times: 1 },
  );
  const failed = await response(page, () => confirm(page).click());
  expect(failed.status()).toBe(503);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(cards(page)).toHaveCount(0);
  const retried = await response(page, () =>
    page.getByRole("button", { name: "重新尝试", exact: true }).click(),
  );
  expect(retried.request().postDataJSON()).toEqual(
    failed.request().postDataJSON(),
  );
  expect((await received(page, retried)).status).toBe("ready");
});

test("P02 cancel and a newer result cannot be overwritten by an older real response", async ({
  page,
}) => {
  let release!: () => void;
  let loaded = false;
  let delivered!: () => void;
  const finished = new Promise<void>((resolve) => {
    delivered = resolve;
  });
  await page.route(
    "**/api/recommendations",
    async (route) => {
      const real = await route.fetch();
      loaded = true;
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      await route.fulfill({ response: real }).catch(() => {});
      delivered();
    },
    { times: 1 },
  );
  await input(page).fill("喜剧片");
  await page.getByRole("button", { name: "看看候选电影", exact: true }).click();
  await expect.poll(() => loaded, { timeout: 30000 }).toBe(true);
  await page.getByRole("button", { name: "取消本次请求", exact: true }).click();
  await input(page).fill("剧情片，120分钟以内");
  const newer = await submit(page);
  expect(newer.status).toBe("ready");
  release();
  await finished;
  await expect(page.locator(".results .trace")).toContainText(newer.trace_id);
  await expect(page.locator(".intent-summary")).toContainText("类型：剧情");
  await expect(cards(page)).toHaveCount(newer.candidates.length);
});

test("P02 explicit session expiry: stale answers stop and a new session recovers", async ({
  page,
}) => {
  await input(page).fill("豆瓣8分以上的喜剧");
  const first = await submit(page);
  await page
    .getByRole("radio", { name: "仅按已识别条件继续", exact: true })
    .check();
  await page.route(
    "**/api/recommendations",
    (route) =>
      route.fulfill({
        status: 409,
        json: {
          contract_version: "0.1.0",
          trace_id: "p02-injected-expired",
          data_mode: "live",
          code: "SESSION_EXPIRED",
          message: "Injected expiry",
          retryable: false,
        },
      }),
    { times: 1 },
  );
  const expired = await response(page, () => confirm(page).click());
  await expect(page.getByRole("alert")).toContainText("临时会话已过期");
  await expect(confirm(page)).toBeDisabled();
  await input(page).fill("喜剧片");
  const recoveredResponse = await response(page, () =>
    page.getByRole("button", { name: "看看候选电影", exact: true }).click(),
  );
  expect(recoveredResponse.request().postDataJSON().session_id).not.toBe(
    expired.request().postDataJSON().session_id,
  );
  expect((await received(page, recoveredResponse)).status).toBe("ready");
  expect(first.status).toBe("needs_clarification");
});

test("P02 switching modes and changing a pick both invalidate old clarification", async ({
  page,
}) => {
  await input(page).fill("豆瓣8分以上的喜剧");
  await submit(page);
  await page
    .getByRole("radio", { name: "仅按已识别条件继续", exact: true })
    .check();
  await page.getByRole("tab", { name: "从片单中选", exact: true }).click();
  await expect(confirm(page)).toBeDisabled();
  await page.getByRole("tab", { name: "不知道看什么", exact: true }).click();
  await submit(page);
  await page
    .getByRole("radio", { name: "仅按已识别条件继续", exact: true })
    .check();
  await page
    .getByRole("group", { name: "想看哪种故事？" })
    .getByRole("button", { name: "剧情", exact: true })
    .click();
  await expect(confirm(page)).toBeDisabled();
  await expect(cards(page)).toHaveCount(0);
});

test("P02 cancelling confirmation preserves selected answers and allows a real retry", async ({
  page,
}) => {
  await input(page).fill("豆瓣8分以上的喜剧");
  await submit(page);
  const answer = page.getByRole("radio", {
    name: "仅按已识别条件继续",
    exact: true,
  });
  await answer.check();
  let release!: () => void;
  let loaded = false;
  let delivered!: () => void;
  const finished = new Promise<void>((resolve) => {
    delivered = resolve;
  });
  await page.route(
    "**/api/recommendations",
    async (route) => {
      const real = await route.fetch();
      loaded = true;
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      await route.fulfill({ response: real }).catch(() => {});
      delivered();
    },
    { times: 1 },
  );
  await confirm(page).click();
  await expect.poll(() => loaded, { timeout: 30000 }).toBe(true);
  await page.getByRole("button", { name: "取消本次请求", exact: true }).click();
  release();
  await finished;
  await expect(answer).toBeChecked();
  await expect(confirm(page)).toBeEnabled();
  await expect(cards(page)).toHaveCount(0);
  expect(
    (await received(page, await response(page, () => confirm(page).click())))
      .status,
  ).toBe("ready");
});

test("P02 negated watch phrases exclude a genre through the real UI", async ({
  page,
}, info) => {
  for (const prefix of ["不要看", "不喜欢看", "不想看", "别看", "不看"]) {
    await input(page).fill(`${prefix}恐怖片，喜剧，120分钟以内`);
    const data = await submit(page);
    expect(data.status).toBe("ready");
    expect(data.interpretation.effective_constraints).toMatchObject({
      genres: ["喜剧"],
      exclude_genres: ["恐怖"],
      max_runtime_minutes: 120,
    });
    expect(data.candidates.length).toBeGreaterThan(0);
    for (const candidate of data.candidates) {
      expect(candidate.movie.genres).toContain("喜剧");
      expect(candidate.movie.genres).not.toContain("恐怖");
      expect(candidate.movie.runtime_minutes).toBeLessThanOrEqual(120);
    }
    await expect(page.locator(".intent-summary")).toContainText("排除类型：恐怖");
  }
  await accessible(page);
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-p02-negated-genre.png`,
    fullPage: true,
  });
});

test("P02 negated era and mood require consent instead of becoming positive filters", async ({
  page,
}, info) => {
  await input(page).fill("不要看新片，不想看感动的喜剧，120分钟以内");
  const pending = await submit(page);
  expect(pending.status).toBe("needs_clarification");
  expect(pending.catalog_size).toBeNull();
  expect(pending.evidence).toEqual([]);
  expect(pending.interpretation.effective_constraints).toMatchObject({
    genres: ["喜剧"],
    era: "any",
    moods: [],
  });
  await expect(cards(page)).toHaveCount(0);
  await expect(confirm(page)).toBeDisabled();
  await page
    .getByRole("radio", { name: "仅按已识别条件继续", exact: true })
    .check();
  const done = await received(
    page,
    await response(page, () => confirm(page).click()),
  );
  expect(done.status).toBe("ready");
  expect(done.interpretation.effective_constraints).toMatchObject({
    era: "any",
    moods: [],
    genres: ["喜剧"],
  });
  await expect(page.locator(".results")).toContainText("经你确认未采用");
  await accessible(page);
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-p02-negated-context.png`,
    fullPage: true,
  });
});

test("P02 ambiguous company and era cannot silently choose a different intent", async ({
  page,
}, info) => {
  await input(page).fill("一个人和朋友看喜剧，新片和2000年以前，120分钟以内");
  const pending = await submit(page);
  expect(pending.status).toBe("needs_clarification");
  expect(pending.catalog_size).toBeNull();
  expect(pending.evidence).toEqual([]);
  expect(pending.interpretation.effective_constraints).toMatchObject({
    company: "",
    era: "any",
    genres: ["喜剧"],
  });
  expect(pending.interpretation.unhandled.join(" ")).toContain("多个不同同行");
  expect(pending.interpretation.unhandled.join(" ")).toContain("多个不同年代");
  await expect(cards(page)).toHaveCount(0);
  await expect(confirm(page)).toBeDisabled();
  await page
    .getByRole("radio", { name: "仅按已识别条件继续", exact: true })
    .check();
  const done = await received(
    page,
    await response(page, () => confirm(page).click()),
  );
  expect(done.status).toBe("ready");
  expect(done.interpretation.effective_constraints).toMatchObject({
    company: "",
    era: "any",
    genres: ["喜剧"],
  });
  await expect(page.locator(".results")).toContainText("经你确认未采用");
  await accessible(page);
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-p02-ambiguous-context.png`,
    fullPage: true,
  });
});
