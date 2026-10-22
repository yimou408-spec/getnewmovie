import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { EvidenceOverview, Ratings } from "./evidence";
import { evidenceForMovie, snapshotForComparison } from "./evidence-model";
import { validateResponse, type Recommendation } from "./domain";
import fixture from "../../../contracts/examples/success.json";

// Contract fixtures are used only in offline tests, never in the running app.
afterEach(cleanup);
const response = () => structuredClone(fixture) as Recommendation;

describe("evidence identity and provenance", () => {
  it("rejects duplicate IDs and rating references to another film or source", () => {
    const duplicate = response();
    duplicate.evidence.push(duplicate.evidence[0]);
    expect(() => validateResponse(duplicate)).toThrow();
    const foreign = response();
    foreign.candidates[0].movie.ratings![0].evidence_id = "syn:e2";
    expect(() => validateResponse(foreign)).toThrow();
    const wrongSource = response();
    wrongSource.candidates[0].movie.ratings![0].source = "Unverified platform";
    expect(() => validateResponse(wrongSource)).toThrow();
  });

  it("keeps a selected comparison snapshot when subsequent results change", () => {
    const original = response();
    const movie = original.candidates[0].movie;
    const selected = snapshotForComparison(movie, original);
    original.candidates[0].reason.text = "changed";
    original.evidence[0].claim = "changed";
    expect(selected.snapshot?.candidate.reason.text).not.toBe("changed");
    expect(selected.snapshot?.evidence[0].claim).not.toBe("changed");
    expect(selected.snapshot?.traceId).toBe("s0-success");
    expect(snapshotForComparison(movie).snapshot).toBeUndefined();
  });

  it("isolates all evidence by film, including evidence outside reason references", () => {
    const data = response();
    const movie = data.candidates[0].movie;
    data.evidence.push({
      ...data.evidence[0],
      evidence_id: "extra-review",
      kind: "review",
      source: "IMDb",
      url: "https://www.imdb.com/title/test/reviews/",
    });
    expect(evidenceForMovie(movie, data.evidence)).toHaveLength(2);
    expect(
      evidenceForMovie(movie, data.evidence).every(
        (e) => e.movie_id === movie.movie_id,
      ),
    ).toBe(true);
  });
});

describe("per-film evidence display", () => {
  it("keeps missing evidence, rating and opinions explicit", () => {
    const movie = { ...response().candidates[1].movie, ratings: [] };
    render(<EvidenceOverview movie={movie} evidence={[]} />);
    expect(screen.getByText("缺少可核对来源")).toBeVisible();
    expect(
      screen.getByText("豆瓣评分未获取；不代表评分低或影片未收录。"),
    ).toBeVisible();
    expect(screen.getByText("尚未获取来源观点。")).toBeVisible();
  });

  it("counts websites instead of relabelled links as independent sources", () => {
    const data = response();
    const movie = data.candidates[0].movie;
    const first = {
      ...data.evidence[0],
      kind: "metadata" as const,
      url: "https://itunes.apple.com/us/movie/id1",
      source: "Apple",
    };
    const second = {
      ...first,
      evidence_id: "another",
      source: "Another label",
      url: "https://itunes.apple.com/us/movie/id2",
    };
    render(<EvidenceOverview movie={movie} evidence={[first, second]} />);
    expect(screen.getByText(/仅 1 个来源站点/)).toBeVisible();
    expect(screen.queryByText(/多源已验证/)).toBeNull();
  });

  it("separates platform scores, scales, votes, timestamps and original links", () => {
    const data = response();
    const movie = data.candidates[0].movie;
    movie.ratings = [
      {
        source: "豆瓣",
        value: 8.2,
        scale: 10,
        vote_count: 1200,
        evidence_id: "douban",
      },
      {
        source: "IMDb",
        value: 77,
        scale: 100,
        vote_count: null,
        evidence_id: "imdb",
      },
    ];
    const evidence = movie.ratings.map((r) => ({
      ...data.evidence[0],
      evidence_id: r.evidence_id,
      source: r.source,
      url:
        r.source === "豆瓣"
          ? "https://movie.douban.com/subject/1/"
          : "https://www.imdb.com/title/test/",
      kind: "rating" as const,
    }));
    render(<Ratings movie={movie} evidence={evidence} />);
    const scores = screen.getAllByTestId("source-rating");
    expect(scores).toHaveLength(2);
    expect(scores[0]).toHaveTextContent("8.2 / 10");
    expect(scores[0]).toHaveTextContent("1,200 票");
    expect(scores[1]).toHaveTextContent("77 / 100");
    expect(scores[1]).toHaveTextContent("票数未提供");
    expect(within(scores[0]).getByRole("link")).toHaveAttribute(
      "href",
      evidence[0].url,
    );
    expect(scores[0].querySelector("time")).toHaveAttribute(
      "datetime",
      evidence[0].retrieved_at,
    );
  });

  it("masks spoilers, blocks dangerous links and renders source prose as text", () => {
    const data = response();
    const movie = data.candidates[0].movie;
    const dangerous = {
      ...data.evidence[0],
      url: "javascript:alert(1)",
      kind: "review" as const,
      claim: "<script>bad()</script>",
    };
    const spoiler = {
      ...dangerous,
      evidence_id: "spoiler",
      spoiler_level: "contains_spoilers" as const,
      claim: "secret ending",
    };
    render(<EvidenceOverview movie={movie} evidence={[dangerous, spoiler]} />);
    expect(screen.queryByRole("link")).toBeNull();
    for (const claim of screen.getAllByText("<script>bad()</script>"))
      expect(claim).toBeVisible();
    expect(screen.queryByText("secret ending")).toBeNull();
    expect(screen.getByText("来源可能包含剧透，暂不展示内容。")).toBeVisible();
    expect(document.querySelector("script")).toBeNull();
  });
});
