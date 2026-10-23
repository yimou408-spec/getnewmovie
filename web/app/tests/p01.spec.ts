import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import success from "../../../contracts/examples/success.json" with { type: "json" };
import empty from "../../../contracts/examples/empty.json" with { type: "json" };
import clarification from "../../../contracts/examples/clarification.json" with { type: "json" };
import degraded from "../../../contracts/examples/degraded.json" with { type: "json" };
import timeout from "../../../contracts/examples/timeout.json" with { type: "json" };
import unconfigured from "../../../contracts/examples/unconfigured.json" with { type: "json" };

const screenshots = "../../docs/frontend/screenshots/p01";
async function accessibleAndFits(page: Page) {
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

test("P01 real service declaration separates metadata from reputation", async ({
  page,
}, info) => {
  await page.goto("/about");
  const region = page.getByRole("region", {
    name: "能力接入状态",
    exact: true,
  });
  await expect(region.getByRole("row", { name: /影片资料/ })).toContainText(
    "已接入",
  );
  await expect(region.getByRole("row", { name: /口碑评分/ })).toContainText(
    "未接入",
  );
  await expect(region.getByRole("row", { name: /影评证据/ })).toContainText(
    "未接入",
  );
  await expect(page.getByText(/不代表上游此刻可用/)).toBeVisible();
  await accessibleAndFits(page);
  await page.locator(".service-status").screenshot({
    path: `${screenshots}/${info.project.name}-capabilities.png`,
  });
  const before = await page
    .locator("body")
    .evaluate((el) => getComputedStyle(el).backgroundColor);
  const opposite = info.project.use.colorScheme === "dark" ? "light" : "dark";
  await page.emulateMedia({ colorScheme: opposite });
  await expect
    .poll(() =>
      page
        .locator("body")
        .evaluate((el) => getComputedStyle(el).backgroundColor),
    )
    .not.toBe(before);
});

test("P01 legacy health remains compatible and unknown", async ({ page }) => {
  await page.route("**/api/health", (route) =>
    route.fulfill({
      json: {
        service: "real-catalog",
        provider: "Apple iTunes US",
        synthetic_fallback: false,
        cache_ttl_seconds: 1800,
      },
    }),
  );
  await page.goto("/about");
  const region = page.getByRole("region", {
    name: "能力接入状态",
    exact: true,
  });
  await expect(region.getByText("待确认", { exact: true })).toHaveCount(6);
  await expect(region.getByText("已接入", { exact: true })).toHaveCount(0);
});

// These are explicitly offline S0 contract scenarios, never live movie recommendations.
for (const [name, body, status] of [
  ["success", success, 200],
  ["empty", empty, 200],
  ["clarification", clarification, 200],
  ["degraded", degraded, 200],
  ["timeout", timeout, 504],
  ["unconfigured", unconfigured, 503],
] as const) {
  test(`P00 S0 offline ${name}`, async ({ page }) => {
    let calls = 0;
    await page.route("**/api/recommendations", (route) => {
      calls += 1;
      return route.fulfill({ json: body, status });
    });
    await page.goto("/");
    await page
      .getByRole("button", { name: "什么都行，直接看看", exact: true })
      .click();
    if ("candidates" in body) {
      await expect(page.locator(".candidate-grid > article")).toHaveCount(
        body.candidates.length,
      );
      await expect(page.locator(".result-context")).toContainText("合成样例");
      if (name === "clarification")
        await expect(
          page.getByRole("heading", { name: "再补充一点想法" }),
        ).toBeVisible();
      if (name === "empty")
        await expect(
          page.getByRole("heading", {
            name: "这次还没有合适的候选",
            exact: true,
          }),
        ).toBeVisible();
      if (name === "degraded")
        await expect(page.locator(".results")).toContainText(body.warnings[0]);
    } else {
      await expect(page.getByRole("alert")).toContainText(
        name === "timeout" ? "超时" : "尚未配置",
      );
      await expect(page.getByRole("alert")).toContainText(body.trace_id);
      await expect(
        page.getByRole("button", { name: "重新尝试", exact: true }),
      ).toHaveCount(name === "timeout" ? 1 : 0);
    }
    expect(calls).toBe(1);
    await accessibleAndFits(page);
  });
}

test("P01 HTTP 422 requests correction without a retry loop", async ({
  page,
}) => {
  await page.route("**/api/recommendations", (route) =>
    route.fulfill({ status: 422, json: { detail: [], trace_id: "p01-422" } }),
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: "什么都行，直接看看", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("输入未通过服务校验");
  await expect(
    page.getByRole("button", { name: "重新尝试", exact: true }),
  ).toHaveCount(0);
});

test("P01 unavailable provider retains the previous candidates", async ({
  page,
}, info) => {
  let calls = 0;
  await page.route("**/api/recommendations", (route) => {
    calls += 1;
    return calls === 1
      ? route.fulfill({ json: success })
      : route.fulfill({
          status: 503,
          json: {
            code: "UPSTREAM_UNAVAILABLE",
            trace_id: "p01-503",
            retryable: true,
          },
        });
  });
  await page.goto("/");
  const start = page.getByRole("button", {
    name: "什么都行，直接看看",
    exact: true,
  });
  await start.click();
  await expect(page.locator(".candidate-grid > article")).toHaveCount(3);
  await start.click();
  await expect(page.getByRole("alert")).toContainText("资料源暂时不可用");
  await expect(
    page.getByRole("heading", { name: "上次候选结果" }),
  ).toBeVisible();
  await expect(page.locator(".candidate-grid > article")).toHaveCount(3);
  expect(calls).toBe(2);
  await accessibleAndFits(page);
  await page.locator(".results").screenshot({
    path: `${screenshots}/${info.project.name}-unavailable.png`,
  });
});

test("P01 cancel then resubmit cannot be overwritten by an older response", async ({
  page,
}) => {
  let calls = 0;
  let release: (() => void) | undefined;
  const latest = structuredClone(success);
  latest.candidates[0].movie.title = "取消后重新选择";
  await page.route("**/api/recommendations", async (route) => {
    calls += 1;
    if (calls === 2) {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      await route.fulfill({ json: success }).catch(() => {});
    } else await route.fulfill({ json: calls === 1 ? success : latest });
  });
  await page.goto("/");
  const start = page.getByRole("button", {
    name: "什么都行，直接看看",
    exact: true,
  });
  try {
    await start.click();
    await expect(page.locator(".candidate-grid > article")).toHaveCount(3);
    await start.click();
    await expect.poll(() => calls).toBe(2);
    await page
      .getByRole("button", { name: "取消本次请求", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "上次候选结果" }),
    ).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await start.click();
    await expect(page.locator(".candidate-grid")).toContainText(
      "取消后重新选择",
    );
    release?.();
    await expect(page.locator(".candidate-grid")).toContainText(
      "取消后重新选择",
    );
    expect(calls).toBe(3);
    await accessibleAndFits(page);
  } finally {
    release?.();
  }
});
