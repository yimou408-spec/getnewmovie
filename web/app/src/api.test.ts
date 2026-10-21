import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./domain";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function pendingFetch() {
  const fetcher = vi.fn(
    (_url: string, init: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init.signal!.addEventListener("abort", () =>
          reject(new DOMException("aborted", "AbortError")),
        );
      }),
  );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

describe("request lifecycle and error boundary", () => {
  it("returns a successful response and preserves request headers", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(Response.json({ status: "ready" }));
    vi.stubGlobal("fetch", fetcher);
    await expect(
      api("/test", { headers: new Headers({ "X-Test": "yes" }) }),
    ).resolves.toEqual({ status: "ready" });
    expect(new Headers(fetcher.mock.calls[0][1].headers).get("X-Test")).toBe(
      "yes",
    );
  });

  it.each([
    [422, {}, "validation", false],
    [503, { code: "NOT_CONFIGURED", retryable: true }, "not_configured", false],
    [
      503,
      { code: "UPSTREAM_UNAVAILABLE", retryable: true },
      "unavailable",
      true,
    ],
    [504, { code: "UPSTREAM_TIMEOUT" }, "timeout", true],
    [429, { code: "UPSTREAM_RATE_LIMIT" }, "rate_limit", true],
    [404, {}, "not_found", false],
  ])(
    "classifies HTTP %i without losing the trace",
    async (status, body, kind, retryable) => {
      vi.stubGlobal(
        "fetch",
        vi
          .fn()
          .mockResolvedValue(
            Response.json({ ...body, trace_id: "trace-p01" }, { status }),
          ),
      );
      await expect(api("/test")).rejects.toMatchObject({
        name: "ApiError",
        status,
        kind,
        retryable,
        trace: "trace-p01",
      });
    },
  );

  it("reports a local timeout separately from user cancellation", async () => {
    vi.useFakeTimers();
    pendingFetch();
    const request = api("/test");
    const assertion = expect(request).rejects.toMatchObject({
      kind: "timeout",
      retryable: true,
    });
    await vi.advanceTimersByTimeAsync(45000);
    await assertion;
    expect(vi.getTimerCount()).toBe(0);
  });

  it("forwards caller cancellation and removes its listener", async () => {
    vi.useFakeTimers();
    const fetcher = pendingFetch();
    const controller = new AbortController();
    const remove = vi.spyOn(controller.signal, "removeEventListener");
    const request = api("/test", { signal: controller.signal });
    const assertion = expect(request).rejects.toMatchObject({
      kind: "cancelled",
      retryable: false,
    });
    controller.abort();
    await assertion;
    expect(fetcher.mock.calls[0][1].signal!.aborted).toBe(true);
    expect(remove).toHaveBeenCalledWith("abort", expect.any(Function));
    expect(vi.getTimerCount()).toBe(0);
  });

  it("never sends an already cancelled request", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const controller = new AbortController();
    controller.abort();
    await expect(
      api("/test", { signal: controller.signal }),
    ).rejects.toMatchObject({ kind: "cancelled" });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("keeps HTTP 503 meaningful even when a proxy returns HTML", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("<html>Unavailable</html>", { status: 503 }),
        ),
    );
    await expect(api("/test")).rejects.toMatchObject({
      status: 503,
      kind: "unavailable",
    });
  });

  it("distinguishes invalid successful JSON from a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not JSON")));
    await expect(api("/test")).rejects.toMatchObject({
      kind: "invalid_response",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    await expect(api("/test")).rejects.toBeInstanceOf(ApiError);
    await expect(api("/test")).rejects.toMatchObject({ kind: "network" });
  });
});
