import { describe, expect, it } from "vitest";
import { safeSourceUrl, validateResponse, buildRequest } from "./domain";
import success from "../../../contracts/examples/success.json";
describe("truthful contract boundary", () => {
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
});
