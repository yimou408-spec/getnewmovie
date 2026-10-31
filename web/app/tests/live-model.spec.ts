import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const screenshots = "../../artifacts/local-model/chrome";

test("REAL local Qwen and Apple complete the rendered recommendation workflow", async ({
  page,
}, info) => {
  test.skip(
    process.env.MOVIE_ACCEPT_LOCAL_MODEL !== "1",
    "Requires installed local weights and the real runtime",
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const config = await (await page.request.get("/api/configuration")).json();
  expect(config.model_location).toBe("local");
  expect(config.model_name).toBe("qwen2.5-1.5b-instruct-q4_k_m");
  await page.goto("/");
  // Finish the initial catalog request before observing the submitted recommendation.
  await expect(page.locator(".results")).toHaveAttribute("aria-busy", "false", {
    timeout: 50_000,
  });
  await page.getByRole("button", { name: "我有一点想法", exact: true }).click();
  await page
    .getByRole("textbox", { name: "说说今晚想看什么（可选）" })
    .fill("想看温暖治愈的喜剧，不要恐怖片，两个小时以内");
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/recommendations") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "看看候选电影", exact: true }).click();
  const received = await response;
  expect(received.status(), await received.text()).toBe(200);
  const data = await received.json();
  expect(data.status).toBe("ready");
  expect(data.interpretation.method).toBe("llm-v1");
  expect(data.interpretation.effective_constraints).toMatchObject({
    genres: ["喜剧"],
    moods: ["温暖治愈"],
    max_runtime_minutes: 120,
    exclude_genres: ["恐怖"],
  });
  expect(data.candidates.length).toBeGreaterThan(0);
  for (const c of data.candidates) {
    expect(c.movie.movie_id).toMatch(/^itunes:\d+$/);
    expect(c.movie.genres).toContain("喜剧");
    expect(c.movie.runtime_minutes).toBeLessThanOrEqual(120);
    expect(c.movie.ratings).toEqual([]);
  }
  await expect(page.locator(".candidate-grid > article")).toHaveCount(
    data.candidates.length,
  );
  await expect(page.locator(".intent-summary")).toContainText("模型");
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
    path: `${screenshots}/${info.project.name}-real-model-results.png`,
    fullPage: true,
  });
  await info.attach("Real local model and catalog response", {
    body: JSON.stringify(data, null, 2),
    contentType: "application/json",
  });
  await page
    .getByRole("textbox", { name: "继续调整本次推荐" })
    .fill("改成90分钟以内");
  const followup = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/recommendations") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "继续推荐", exact: true }).click();
  const refinedResponse = await followup;
  expect(refinedResponse.status()).toBe(200);
  const refined = await refinedResponse.json();
  expect(refined.interpretation.effective_constraints).toMatchObject({
    genres: ["喜剧"],
    max_runtime_minutes: 90,
    exclude_genres: ["恐怖"],
  });
  expect(
    refined.candidates.every(
      (c: { movie: { runtime_minutes: number } }) =>
        c.movie.runtime_minutes <= 90,
    ),
  ).toBe(true);
  await expect(page.locator(".candidate-grid > article")).toHaveCount(
    refined.candidates.length,
  );
  await page.goto("/setup");
  await expect(
    page.getByText("已完成真实模型调用", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "当前配置状态" }),
  ).toContainText("qwen2.5-1.5b-instruct-q4_k_m");
  await expect(
    page.getByRole("region", { name: "当前配置状态" }),
  ).toContainText("无需 TMDB token");
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-real-model-setup.png`,
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("REAL Apple recovers when optional TMDB and model services are deliberately unavailable", async ({
  page,
}, info) => {
  test.skip(
    process.env.MOVIE_ACCEPT_FAULT_SERVER !== "1",
    "Uses a dedicated fault acceptance server, not the healthy demo",
  );
  await page.goto("/");
  await page.getByRole("button", { name: "我有一点想法", exact: true }).click();
  await page
    .getByRole("textbox", { name: "说说今晚想看什么（可选）" })
    .fill("喜剧，100分钟以内，不要恐怖");
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/recommendations") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "看看候选电影", exact: true }).click();
  const received = await response;
  expect(received.status(), await received.text()).toBe(200);
  const data = await received.json();
  expect(data.status).toBe("ready");
  expect(data.interpretation.method).toBe("rules-v1");
  expect(data.warnings.join(" ")).toContain("模型暂时不可用");
  expect(data.warnings.join(" ")).toContain("已切换至 Apple");
  expect(
    data.candidates.every((c: { movie: { movie_id: string } }) =>
      c.movie.movie_id.startsWith("itunes:"),
    ),
  ).toBe(true);
  await expect(page.locator(".candidate-grid > article")).toHaveCount(
    data.candidates.length,
  );
  await expect(
    page.getByText(/已切换至 Apple/, { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "核对理由与来源", exact: true })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText("Apple");
  await page.getByRole("button", { name: "关闭来源面板" }).click();
  await page
    .getByRole("textbox", { name: "继续调整本次推荐" })
    .fill("改成90分钟以内");
  const followup = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/recommendations") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "继续推荐", exact: true }).click();
  const refined = await (await followup).json();
  expect(refined.status).toBe("ready");
  expect(refined.interpretation.method).toBe("rules-v1");
  expect(refined.interpretation.effective_constraints).toMatchObject({
    genres: ["喜剧"],
    max_runtime_minutes: 90,
    exclude_genres: ["恐怖"],
  });
  await expect(page.locator(".candidate-grid > article")).toHaveCount(
    refined.candidates.length,
  );
  await page.screenshot({
    path: `${screenshots}/${info.project.name}-real-source-recovery.png`,
    fullPage: true,
  });
  await info.attach("Real Apple recovery response", {
    body: JSON.stringify(data, null, 2),
    contentType: "application/json",
  });
});
