import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixture from "../../../contracts/examples/success.json" with { type: "json" };

test("memory: explicit consent, persistent preferences and seen, disable and delete", async ({
  page,
}, info) => {
  // Only movie results are synthetic; identities, SQLite and feedback use real API.
  const data = structuredClone(fixture);
  for (const [i, candidate] of data.candidates.entries()) {
    const old = candidate.movie.movie_id;
    candidate.movie.movie_id = `itunes:${900001 + i}` as typeof old;
    for (const evidence of data.evidence)
      if (evidence.movie_id === old)
        evidence.movie_id = candidate.movie.movie_id;
  }
  data.data_mode = "live";
  await page.route("**/api/recommendations", (route) =>
    route.fulfill({ json: data }),
  );
  await page.goto("/preferences");
  await expect(
    page.getByRole("button", { name: "建立匿名身份并启用记忆" }),
  ).toBeDisabled();
  await page
    .getByLabel("同意在本机保存匿名身份，并在服务端保存我确认的偏好与已看记录")
    .check();
  await page.getByRole("button", { name: "建立匿名身份并启用记忆" }).click();
  await expect(
    page.getByRole("heading", { name: "记忆已启用", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "保存当前点选为长期偏好" }).click();
  await expect(page.getByText("长期偏好已保存", { exact: true })).toBeVisible();
  const token = await page.evaluate(() =>
    localStorage.getItem("movie-identity"),
  );
  expect(token).toBeTruthy();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "记忆已启用", exact: true }),
  ).toBeVisible();
  await page.goto("/");
  await expect(page.locator(".candidate-grid > article")).toHaveCount(3);
  await page
    .getByRole("button", { name: "确认已看并保存", exact: true })
    .first()
    .click();
  await expect(page.locator(".toast-region")).toContainText("已确认保存");
  await page.goto("/preferences");
  await expect(
    page.getByRole("button", { name: "移除已看标记", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭记忆", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "长期记忆默认关闭", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "启用已保存记忆", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "移除已看标记", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "移除已看标记", exact: true }).click();
  await expect(
    page.getByText("还没有已看记录。", { exact: true }),
  ).toBeVisible();
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `../../artifacts/backend-acceptance/${info.project.name}-memory.png`,
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "删除全部服务端个人数据", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "确认删除全部个人数据", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("确认删除偏好、已看与会话，删除后无法撤销").check();
  await page
    .getByRole("button", { name: "确认删除全部个人数据", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "建立匿名身份并启用记忆" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => localStorage.getItem("movie-identity")),
  ).toBeNull();
  const stale = await page.request.get("/api/me/preferences", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(stale.status()).toBe(401);
});
