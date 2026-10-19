import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const screenshots = "../../docs/frontend/screenshots";
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}
async function accessible(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations).toEqual([]);
}

test("select, inspect sources, save, compare and privacy through real S0 API", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /今晚，\s*想看点什么？/ }),
  ).toBeVisible();
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: `${screenshots}/${testInfo.project.name}-home.png`,
    fullPage: true,
  });
  await page.getByLabel("说说这次的观影想法").fill("轻松的电影，100 分钟以内");
  await page.getByLabel("最多看多久").fill("100");
  const request = page.waitForRequest(
    (r) => r.url().endsWith("/api/recommendations") && r.method() === "POST",
  );
  await page.getByRole("button", { name: "看看候选电影" }).click();
  const body = (await request).postDataJSON();
  expect(body.memory_enabled).toBe(false);
  expect(body.constraints.max_runtime_minutes).toBe(100);
  await expect(page.getByRole("heading", { name: "春日来信" })).toBeVisible();
  await expect(page.getByText("观看渠道未知", { exact: false })).toBeVisible();
  await page.getByText("核对理由与来源", { exact: true }).click();
  await expect(page.getByText("查看来源（暂无可访问链接）")).toBeVisible();
  expect(await page.locator('a[href*=".invalid"]').count()).toBe(0);
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: `${screenshots}/${testInfo.project.name}-result.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "加入本次片单", exact: true }).click();
  await page.getByRole("checkbox", { name: "对比 春日来信 2024" }).check();
  await page.getByRole("link", { name: /本次片单/ }).click();
  await page.getByLabel("影片名称").fill("远星航线");
  await page.getByRole("button", { name: "查找影片" }).click();
  await expect(
    page.getByText("远星航线（2022）", { exact: true }),
  ).toBeVisible();
  await page
    .locator(".lookup-item")
    .getByRole("button", { name: "加入本次片单" })
    .click();
  await page.getByRole("checkbox", { name: "对比 远星航线 2022" }).check();
  await page.getByRole("link", { name: "开始对比" }).click();
  await expect(
    page.getByRole("region", { name: "影片对比表，可左右滚动" }),
  ).toBeVisible();
  await expect(page.getByRole("cell", { name: "95 分钟" })).toBeVisible();
  await noOverflow(page);
  await accessible(page);
  await page.screenshot({
    path: `${screenshots}/${testInfo.project.name}-compare.png`,
    fullPage: true,
  });
  await page.getByRole("link", { name: "偏好与隐私", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "记住我的观影偏好" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "清空本次片单与对比" }).click();
  await expect(page.locator(".compare-tray")).toHaveCount(0);
  await page.getByRole("button", { name: "撤销", exact: true }).click();
  await expect(page.locator(".compare-tray")).toContainText("已选 2/3 部");
  await page.getByRole("button", { name: "清空本次片单与对比" }).click();
  await page.getByRole("link", { name: "选片", exact: true }).click();
  await expect(page.getByLabel("说说这次的观影想法")).toHaveValue(
    "轻松的电影，100 分钟以内",
  );
  expect(errors).toEqual([]);
});

test("ambiguous identity, unknown film and all service states remain truthful", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "已知道片名" }).click();
  await page.getByLabel("影片名称").fill("春日来信");
  await page.getByRole("button", { name: "查找影片" }).click();
  await expect(page.getByText("找到同名影片，请确认具体年份。")).toBeVisible();
  await expect(page.getByRole("button", { name: "确认这部" })).toHaveCount(2);
  await page
    .locator(".lookup-item")
    .filter({ hasText: "1998" })
    .getByRole("button", { name: "确认这部" })
    .click();
  await expect(page.getByText("已确认：春日来信（1998）")).toBeVisible();
  await page
    .getByLabel("关于这部电影，你在意什么？")
    .fill("判断这部电影是否适合今晚");
  const knownRequest = page.waitForRequest(
    (r) => r.url().endsWith("/api/recommendations") && r.method() === "POST",
  );
  await page.getByRole("button", { name: "看看候选电影" }).click();
  expect((await knownRequest).postDataJSON().movie_id).toBe("syn:letter-1998");
  await expect(page.getByRole("heading", { name: "春日来信" })).toBeVisible();
  await page.getByRole("tab", { name: "不知道看什么" }).click();
  await page.getByLabel("说说这次的观影想法").fill("今晚想看电影");
  await page.getByText("联调场景设置", { exact: true }).click();
  for (const [scenario, text] of [
    ["empty", "这次还没有合适的候选"],
    ["degraded", "推荐服务暂时降级"],
    ["clarification", "再补充一点想法"],
    ["timeout", "推荐服务响应超时，可以重试。"],
    ["unconfigured", "推荐服务尚未配置，请稍后再试。"],
  ]) {
    await page.getByLabel("模拟服务状态").selectOption(scenario);
    await page.getByRole("button", { name: "看看候选电影" }).click();
    await expect(page.getByText(text, { exact: true })).toBeVisible();
    await noOverflow(page);
  }
  await expect(page.getByLabel("说说这次的观影想法")).toHaveValue(
    "今晚想看电影",
  );
  await page.goto("/film/syn%3Adoes-not-exist");
  await expect(page.getByRole("alert")).toContainText("没有找到这部影片");
  await page.goto("/unknown");
  await expect(
    page.getByRole("heading", { name: "这一页还没有开场" }),
  ).toBeVisible();
});

test("failed and malformed responses retain the last result and session data clears on reload", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("说说这次的观影想法").fill("今晚想看一部轻松的电影");
  await page.getByRole("button", { name: "看看候选电影" }).click();
  await expect(page.getByRole("heading", { name: "春日来信" })).toBeVisible();
  await page.getByRole("button", { name: "加入本次片单", exact: true }).click();
  await page.route("**/api/recommendations", (route) => route.abort("failed"));
  await page.getByRole("button", { name: "看看候选电影" }).click();
  await expect(page.getByRole("alert")).toContainText("连接失败");
  await expect(page.getByRole("heading", { name: "春日来信" })).toBeVisible();
  await page.unroute("**/api/recommendations");
  await page.route("**/api/recommendations", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ready", candidates: [] }),
    }),
  );
  await page.getByRole("button", { name: "看看候选电影" }).click();
  await expect(page.getByRole("alert")).toContainText("接口约定不一致");
  await expect(page.getByRole("heading", { name: "春日来信" })).toBeVisible();
  await page.reload();
  await page.getByRole("link", { name: /本次片单/ }).click();
  await expect(
    page.getByRole("heading", { name: "第一部，留给你想看的" }),
  ).toBeVisible();
  await noOverflow(page);
});

test("theme reacts immediately, keyboard entry works, and navigation never loses draft", async ({
  page,
}) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "跳到主要内容" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
  await page.getByLabel("说说这次的观影想法").fill("不丢失的草稿");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(20, 27, 37)",
  );
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(245, 246, 248)",
  );
  await page.getByRole("link", { name: "关于与数据说明" }).click();
  await accessible(page);
  await noOverflow(page);
  await page.getByRole("link", { name: "选片", exact: true }).click();
  await expect(page.getByLabel("说说这次的观影想法")).toHaveValue(
    "不丢失的草稿",
  );
  await page.setViewportSize({ width: 320, height: 720 });
  await noOverflow(page);
});

test("cinema artwork, wide layout and mood shortcuts remain usable", async ({
  page,
  isMobile,
}, testInfo) => {
  await page.goto("/");
  const artwork = page.getByRole("img", { name: /暖色车厢/ });
  await expect(artwork).toBeVisible();
  await expect
    .poll(() =>
      artwork.evaluate((img) => (img as HTMLImageElement).naturalWidth),
    )
    .toBe(2200);
  if (!isMobile) {
    for (const width of [1920, 2560]) {
      await page.setViewportSize({ width, height: 1080 });
      await noOverflow(page);
      const hero = await page.locator(".intro").boundingBox();
      expect(hero!.width).toBeGreaterThan(width * 0.65);
      await expect(
        page.getByRole("button", { name: "开始今晚的选片" }),
      ).toBeInViewport();
      await page.screenshot({
        path: `${screenshots}/${testInfo.project.name}-${width}.png`,
      });
    }
  } else {
    await page.setViewportSize({ width: 320, height: 720 });
    await noOverflow(page);
    await page.screenshot({
      path: `${screenshots}/${testInfo.project.name}-320.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "开始今晚的选片" }).click();
  await expect(page.getByLabel("说说这次的观影想法")).toBeFocused();
  await expect(page.getByLabel("说说这次的观影想法")).toBeInViewport();
  await page.getByRole("tab", { name: "已知道片名" }).click();
  await page.getByRole("button", { name: /松弛一点/ }).click();
  await expect(page.getByRole("tab", { name: "不知道看什么" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByLabel("说说这次的观影想法")).toHaveValue(
    "想轻松一下，100 分钟以内",
  );
  await expect(page.getByLabel("说说这次的观影想法")).toBeFocused();
  await expect(page.getByLabel("最多看多久")).toHaveValue("100");
  await page.getByRole("button", { name: "看看候选电影" }).click();
  await expect(page.getByRole("heading", { name: "春日来信" })).toBeVisible();
  await noOverflow(page);
});
