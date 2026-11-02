import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixture from "../../../contracts/examples/success.json" with { type: "json" };
import type { Recommendation } from "../src/domain";

for (const scope of ["independent_sources", "single_platform"] as const) {
  test(`OFFLINE ${scope} opinion comparison has citations, inference labels and responsive disclosure`, async ({
    page,
  }, info) => {
    const data = structuredClone(fixture) as Recommendation;
    data.candidates = data.candidates.slice(0, 1);
    const candidate = data.candidates[0];
    const reviews = ["a", "b"].map((id) => ({
      ...data.evidence[0],
      evidence_id: `opinion-${id}`,
      movie_id: candidate.movie.movie_id,
      source: scope === "single_platform" ? "IMDb" : `Offline ${id}`,
      url:
        scope === "single_platform"
          ? `https://www.imdb.com/review/rw000000${id === "a" ? "1" : "2"}/`
          : `https://example.com/${id}`,
      kind: "review" as const,
      granularity: "excerpt" as const,
      claim: id === "a" ? "节奏缓慢，氛围轻松。" : "节奏明快，氛围轻松。",
      spoiler_level: "safe" as const,
      author: `作者${id}`,
      independent_source_group: scope === "single_platform" ? null : id,
      source_content_id:
        scope === "single_platform" ? `rw000000${id === "a" ? "1" : "2"}` : id,
      usage_basis: "synthetic" as const,
    }));
    data.evidence.push(...reviews);
    candidate.opinion_summary = {
      status: "compared",
      synthetic: true,
      comparison_scope: scope,
      independent_group_count: scope === "single_platform" ? 0 : 2,
      opinions: reviews.map((e) => ({
        evidence_id: e.evidence_id,
        aspect: "tone",
        value: "light",
        quote: "氛围轻松",
      })),
      comparisons: [
        {
          aspect: "tone",
          kind: "agreement",
          text:
            scope === "single_platform"
              ? "本次IMDb站内材料在氛围上的描述一致：轻松。"
              : "本次独立材料在氛围上的描述一致：轻松。",
          evidence_ids: reviews.map((e) => e.evidence_id),
        },
      ],
      matches: [
        {
          text: "材料含轻松氛围线索，这是与你需求的匹配推断。",
          evidence_ids: [reviews[0].evidence_id],
        },
      ],
      cautions: [],
      limitations: ["仅对本次材料片段作对照，不代表全网口碑。"],
      extraction_method: "controlled_phrases",
      model_status: "not_enabled",
      followup_status: "not_needed",
    };
    await page.route("**/api/recommendations", (route) =>
      route.fulfill({ json: data }),
    );
    await page.goto("/");
    await expect(page.locator(".candidate-grid > article")).toHaveCount(1);
    await page
      .getByRole("button", { name: "核对理由与来源", exact: true })
      .click();
    const panel = page.getByRole("dialog");
    const synthesis = panel.getByRole("region", { name: "材料观点对照" });
    await expect(synthesis).toContainText("含离线合成材料");
    await expect(synthesis).toContainText("匹配推断");
    await expect(synthesis).toContainText("不代表全网口碑");
    if (scope === "single_platform")
      await expect(synthesis).toContainText("本站影评样本可对照");
    await expect(
      synthesis
        .getByRole("link", {
          name: scope === "single_platform" ? /IMDb/ : /Offline a/,
        })
        .first(),
    ).toHaveAttribute("href", reviews[0].url);
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
      path: `../../artifacts/imdb/${info.project.name}-${scope}-comparison.png`,
    });
    await page.getByRole("button", { name: "关闭来源面板" }).click();
    await expect(panel).toHaveCount(0);
  });
}
