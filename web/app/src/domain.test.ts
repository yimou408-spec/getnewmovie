import { describe, expect, it } from "vitest";
import {
  safeSourceUrl,
  validateResponse,
  buildRequest,
  discoverQuery,
} from "./domain";
import success from "../../../contracts/examples/success.json";
describe("truthful contract boundary", () => {
  it("allows discovery without typing and preserves selected preferences", () => {
    const empty = discoverQuery({ moods: [], genres: [], company: "" }, "");
    expect(buildRequest("discover", empty, "CN", "", []).query).toBeTruthy();
    const query = discoverQuery(
      { moods: ["轻松解压"], genres: ["科幻", "喜剧"], company: "两个人" },
      "不要恐怖",
    );
    expect(query).toContain("轻松解压");
    expect(query).toContain("科幻、喜剧");
    expect(query).toContain("两个人");
    expect(query).toContain("不要恐怖");
  });
  it("offers three distinct synthetic previews without claiming personalization", () => {
    expect(success.candidates).toHaveLength(3);
    expect(new Set(success.candidates.map((c) => c.movie.movie_id)).size).toBe(
      3,
    );
    expect(success.warnings.join("")).toContain("固定");
  });
  it("accepts the shared fixture but rejects unsupported versions and unsafe evidence", () => {
    expect(validateResponse(success).data_mode).toBe("synthetic");
    expect(() =>
      validateResponse({ ...success, contract_version: "99" }),
    ).toThrow();
    expect(() => validateResponse({ ...success, evidence: [] })).toThrow();
  });
  it("never turns placeholder or executable URLs into source links", () => {
    expect(safeSourceUrl("https://example.invalid/film")).toBeNull();
    expect(safeSourceUrl("javascript:alert(1)")).toBeNull();
    expect(safeSourceUrl("https://www.themoviedb.org/movie/1")).toBeTruthy();
  });
  it("requires confirmed identities and keeps memory disabled", () => {
    expect(() =>
      buildRequest("known_movie", "片名", "CN", "", [], undefined),
    ).toThrow("确认");
    expect(
      buildRequest("discover", "轻松电影", "CN", "100", [], undefined)
        .memory_enabled,
    ).toBe(false);
    expect(() =>
      buildRequest("discover", "电影", "CN", "0", [], undefined),
    ).toThrow();
  });
  it("does not require optional prose after choosing a film or a watchlist", () => {
    const movie = success.candidates[0].movie;
    expect(
      buildRequest("known_movie", "", "CN", "", [], movie).query,
    ).toBeTruthy();
    expect(
      buildRequest("watchlist", "   ", "CN", "", [movie.movie_id]).query,
    ).toBeTruthy();
  });
  it("rejects source results that disagree with top-level movie evidence", () => {
    const data = structuredClone(success) as unknown as Record<string, unknown>;
    data.source_results = [
      {
        movie_id: "syn:not-returned",
        source: "Douban",
        status: "timeout",
        evidence: [],
        ratings: [],
        warnings: [],
        cache_status: "none",
      },
    ];
    expect(() => validateResponse(data)).toThrow();
  });
});
