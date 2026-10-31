import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemorySettings } from "./memory";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});

it("creates identity only after consent, saves versioned choices and requires deletion confirmation", async () => {
  const calls: string[] = [];
  let enabled = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit) => {
      calls.push(url);
      if (url.endsWith("/identities"))
        return new Response(
          JSON.stringify({ identity_token: "offline-token" }),
        );
      if (url.endsWith("/me/seen"))
        return new Response(
          JSON.stringify({ movie_ids: ["itunes:101"], version: 1 }),
        );
      if (url.includes("/me/data"))
        return new Response(JSON.stringify({ deleted: true }));
      if (options?.method === "PUT")
        enabled = JSON.parse(String(options.body)).enabled;
      return new Response(
        JSON.stringify({ enabled, constraints: {}, version: 1 }),
      );
    }),
  );
  const changed = vi.fn();
  render(<MemorySettings current={{ genres: ["喜剧"] }} onChanged={changed} />);
  expect(calls).toHaveLength(0);
  expect(
    screen.getByRole("button", { name: "建立匿名身份并启用记忆" }),
  ).toBeDisabled();
  fireEvent.click(
    screen.getByLabelText(
      "同意在本机保存匿名身份，并在服务端保存我确认的偏好与已看记录",
    ),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "建立匿名身份并启用记忆" }),
  );
  await screen.findByText("记忆已启用");
  expect(localStorage.getItem("movie-identity")).toBe("offline-token");
  fireEvent.click(
    screen.getByRole("button", { name: "保存当前点选为长期偏好" }),
  );
  await screen.findByText("长期偏好已保存");
  fireEvent.click(
    screen.getByRole("button", { name: "删除全部服务端个人数据" }),
  );
  expect(calls.some((url) => url.includes("/me/data"))).toBe(false);
  fireEvent.click(
    screen.getByLabelText("确认删除偏好、已看与会话，删除后无法撤销"),
  );
  fireEvent.click(screen.getByRole("button", { name: "确认删除全部个人数据" }));
  await waitFor(() =>
    expect(localStorage.getItem("movie-identity")).toBeNull(),
  );
});

it("keeps state and shows failure when a save is rejected", async () => {
  localStorage.setItem("movie-identity", "offline-token");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, options: RequestInit) => {
      if (options?.method === "PUT")
        return new Response(
          JSON.stringify({ message: "偏好已变化", code: "VERSION_CONFLICT" }),
          { status: 409 },
        );
      return new Response(
        JSON.stringify({
          enabled: true,
          constraints: {},
          version: 1,
          movie_ids: [],
        }),
      );
    }),
  );
  render(<MemorySettings current={{}} onChanged={() => {}} />);
  await screen.findByText("记忆已启用");
  fireEvent.click(
    screen.getByRole("button", { name: "保存当前点选为长期偏好" }),
  );
  await screen.findByRole("alert");
  expect(screen.getByText("记忆已启用")).toBeInTheDocument();
});

it("recovers from an identity revoked elsewhere without blocking fresh consent", async () => {
  localStorage.setItem("movie-identity", "revoked-offline-token");
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            code: "IDENTITY_REQUIRED",
            message: "身份已删除",
            retryable: false,
          }),
          { status: 401 },
        ),
    ),
  );
  const changed = vi.fn();
  render(<MemorySettings current={{}} onChanged={changed} />);
  await waitFor(() =>
    expect(localStorage.getItem("movie-identity")).toBeNull(),
  );
  expect(
    screen.getByRole("button", { name: "建立匿名身份并启用记忆" }),
  ).toBeDisabled();
  expect(changed).toHaveBeenCalledWith(false);
  expect(screen.getByRole("alert")).toHaveTextContent("匿名身份已失效");
});
