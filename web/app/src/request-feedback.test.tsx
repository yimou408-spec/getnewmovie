import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "./domain";
import { ErrorNotice } from "./request-feedback";
import { ServiceStatusView, validateHealth } from "./service-status";

afterEach(cleanup);
const legacy = {
  service: "real-catalog",
  provider: "Apple iTunes US",
  synthetic_fallback: false,
  cache_ttl_seconds: 1800,
};
const flags = {
  metadata: true,
  ratings: false,
  reviews: false,
  natural_language: false,
  long_term_memory: false,
  local_availability: false,
};

describe("visible request states", () => {
  it.each([
    ["timeout", "等待超过 45 秒，请重试。", true],
    ["validation", "输入未通过服务校验，请检查内容。", false],
    ["not_configured", "推荐服务尚未配置，请稍后再试。", false],
    ["unavailable", "电影资料源暂时不可用，已有结果仍可查看。", true],
  ])(
    "renders %s with a trace and the correct retry action",
    async (kind, message, retryable) => {
      const retry = vi.fn();
      render(
        <ErrorNotice
          error={new ApiError(message, "p01-trace", retryable, kind)}
          retry={retry}
        />,
      );
      expect(screen.getByRole("alert")).toHaveTextContent(message);
      expect(screen.getByText("请求编号：p01-trace")).toBeVisible();
      if (retryable) {
        await userEvent.click(screen.getByRole("button", { name: "重新尝试" }));
        expect(retry).toHaveBeenCalledOnce();
      } else expect(screen.queryByRole("button")).toBeNull();
    },
  );
  it("treats cancellation as a status without an error or retry action", () => {
    render(
      <ErrorNotice
        error={new ApiError("已取消本次请求。", undefined, false, "cancelled")}
        retry={vi.fn()}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("已取消");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("service capability compatibility", () => {
  it("renders successful metadata separately from missing reputation", () => {
    render(
      <ServiceStatusView
        health={validateHealth({ ...legacy, capabilities: flags })}
      />,
    );
    expect(screen.getByRole("row", { name: /影片资料/ })).toHaveTextContent(
      "已接入",
    );
    expect(screen.getByRole("row", { name: /口碑评分/ })).toHaveTextContent(
      "未接入",
    );
    expect(screen.getByRole("row", { name: /影评证据/ })).toHaveTextContent(
      "未接入",
    );
  });
  it("accepts old health responses but leaves all capabilities unknown", () => {
    render(<ServiceStatusView health={validateHealth(legacy)} />);
    expect(screen.getAllByText("待确认")).toHaveLength(7);
    expect(screen.queryByText("已接入")).toBeNull();
  });
  it("does not trust flags from an unexpected service or synthetic fallback", () => {
    render(
      <ServiceStatusView
        health={validateHealth({
          ...legacy,
          synthetic_fallback: true,
          capabilities: flags,
        })}
      />,
    );
    expect(screen.getAllByText("待确认")).toHaveLength(7);
    expect(screen.queryByText("已接入")).toBeNull();
  });
  it("rejects malformed flags instead of turning strings into available capabilities", () => {
    expect(() =>
      validateHealth({ ...legacy, capabilities: { ...flags, ratings: "yes" } }),
    ).toThrow("接口约定");
  });
});
