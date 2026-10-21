import Ajv from "ajv";
import addFormats from "ajv-formats";
import responseSchema from "../../../contracts/generated/recommendation-response.schema.json";
import requestSchema from "../../../contracts/generated/recommendation-request.schema.json";
import type { components } from "./generated/api";

export type Movie = components["schemas"]["Movie"];
export type Candidate = components["schemas"]["Candidate"];
export type Recommendation = components["schemas"]["RecommendationResponse"];
export type Request = components["schemas"]["RecommendationRequest"];
export type Mode = Request["mode"];
export type DataMode = Recommendation["data_mode"];
const ajv = new Ajv({ strict: false });
addFormats(ajv);
const responseValid = ajv.compile<Recommendation>(responseSchema);
const requestValid = ajv.compile<Request>(requestSchema);

export function validateResponse(raw: unknown): Recommendation {
  if (!responseValid(raw))
    throw new Error("服务返回的数据与接口约定不一致，请重试。");
  const ids = new Set(raw.candidates.map((c) => c.movie.movie_id));
  if (
    ids.size !== raw.candidates.length ||
    (raw.status === "ready" && !ids.size) ||
    (["empty", "needs_clarification"].includes(raw.status) && ids.size) ||
    (raw.status === "needs_clarification" && !raw.questions.length) ||
    (raw.status !== "needs_clarification" && raw.questions.length > 0) ||
    (["empty", "degraded"].includes(raw.status) && !raw.warnings.length)
  )
    throw new Error("服务返回的候选状态不完整。");
  for (const c of raw.candidates) {
    if (c.movie.ratings?.some((r) => r.value > r.scale))
      throw new Error("评分超出了来源量表。");
    for (const id of c.reason.evidence_ids) {
      if (
        !raw.evidence.some(
          (e) =>
            e.evidence_id === id &&
            e.movie_id === c.movie.movie_id &&
            e.spoiler_level === "safe",
        )
      )
        throw new Error("推荐理由缺少可核对的安全来源。");
    }
  }
  return raw;
}

export function safeSourceUrl(value: string | null | undefined): string | null {
  try {
    const u = new URL(value ?? "");
    return ["http:", "https:"].includes(u.protocol) &&
      !u.hostname.replace(/\.$/, "").endsWith(".invalid") &&
      u.hostname.replace(/\.$/, "") !== "invalid" &&
      !u.username &&
      !u.password
      ? u.href
      : null;
  } catch {
    return null;
  }
}

export type DiscoverPreferences = {
  moods: string[];
  genres: string[];
  company: string;
};

export function discoverQuery(
  preferences: DiscoverPreferences,
  note: string,
): string {
  const parts = [
    preferences.moods.length ? `心情：${preferences.moods.join("、")}` : "",
    preferences.genres.length ? `类型：${preferences.genres.join("、")}` : "",
    preferences.company ? `一起看的人：${preferences.company}` : "",
    note.trim() ? `补充：${note.trim()}` : "",
  ].filter(Boolean);
  return parts.length
    ? parts.join("；")
    : "什么都行，没有特别偏好，直接给我一些电影候选。";
}

export function buildRequest(
  mode: Mode,
  query: string,
  region: string,
  runtime: string,
  saved: string[],
  selected?: Movie,
  clarificationCount = 0,
  preferredTags: string[] = [],
  preferences?: DiscoverPreferences,
): Request {
  if (mode === "known_movie" && !selected)
    throw new Error("请先查找并确认影片及年份。");
  if (mode === "watchlist" && !saved.length)
    throw new Error("请先查找影片并加入本次片单。");
  if (
    runtime &&
    (!Number.isInteger(Number(runtime)) ||
      Number(runtime) < 1 ||
      Number(runtime) > 600)
  )
    throw new Error("时长请输入 1–600 分钟的整数。");
  const request: Request = {
    mode,
    query: query.trim(),
    region,
    session_id: "frontend-session",
    memory_enabled: false,
    clarification_count: clarificationCount,
    movie_id: mode === "known_movie" ? selected!.movie_id : null,
    watchlist_movie_ids: mode === "watchlist" ? saved : [],
    constraints: {
      max_runtime_minutes: runtime ? Number(runtime) : null,
      exclude_movie_ids: [],
      exclude_genres: [],
      preferred_tags: preferredTags,
      moods: preferences?.moods ?? [],
      genres: preferences?.genres ?? [],
      company: preferences?.company ?? "",
      sort_by: "balanced",
      era: "any",
    } as Request["constraints"],
  };
  if (!requestValid(request))
    throw new Error("请填写 1–2000 字的观影想法，并检查地区与时长。");
  return request;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public trace?: string,
    public retryable = true,
    public kind = "service",
    public status?: number,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const controller = new AbortController();
  const callerSignal = options.signal;
  const cancel = () => controller.abort();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 45000);
  callerSignal?.addEventListener("abort", cancel, { once: true });
  try {
    if (callerSignal?.aborted) controller.abort();
    if (controller.signal.aborted)
      throw new DOMException("aborted", "AbortError");
    const headers = new Headers(options.headers);
    if (!headers.has("Content-Type"))
      headers.set("Content-Type", "application/json");
    const res = await fetch(`/api${path}`, {
      ...options,
      signal: controller.signal,
      headers,
    });
    let raw: unknown;
    try {
      raw = await res.json();
    } catch (error) {
      if (controller.signal.aborted) throw error;
      if (res.ok)
        throw new ApiError(
          "服务返回的内容无法读取，请重试。",
          undefined,
          true,
          "invalid_response",
          res.status,
        );
    }
    if (!res.ok) {
      const body =
        raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
      const code = typeof body.code === "string" ? body.code : undefined;
      const [kind, message, retryable] =
        res.status === 422
          ? (["validation", "输入未通过服务校验，请检查内容。", false] as const)
          : code === "NOT_CONFIGURED"
            ? ([
                "not_configured",
                "推荐服务尚未配置，请稍后再试。",
                false,
              ] as const)
            : code === "UPSTREAM_RATE_LIMIT" || res.status === 429
              ? ([
                  "rate_limit",
                  "资料源请求较多，请一分钟后重试。",
                  true,
                ] as const)
              : code === "UPSTREAM_TIMEOUT" || res.status === 504
                ? (["timeout", "推荐服务响应超时，可以重试。", true] as const)
                : code === "UPSTREAM_UNAVAILABLE" || res.status === 503
                  ? ([
                      "unavailable",
                      "电影资料源暂时不可用，已有结果仍可查看。",
                      true,
                    ] as const)
                  : res.status === 404
                    ? ([
                        "not_found",
                        "没有找到这部影片，请重新查找。",
                        false,
                      ] as const)
                    : ([
                        "service",
                        "服务暂时无法完成请求，请重试。",
                        res.status >= 500,
                      ] as const);
      throw new ApiError(
        message,
        typeof body.trace_id === "string" ? body.trace_id : undefined,
        retryable && body.retryable !== false,
        kind,
        res.status,
        code,
      );
    }
    if (controller.signal.aborted)
      throw new DOMException("aborted", "AbortError");
    return raw as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted)
      throw new ApiError(
        timedOut ? "等待超过 45 秒，请重试。" : "已取消本次请求。",
        undefined,
        timedOut,
        timedOut ? "timeout" : "cancelled",
      );
    throw new ApiError(
      "连接失败，请确认本地服务已启动后重试。",
      undefined,
      true,
      "network",
    );
  } finally {
    window.clearTimeout(timer);
    callerSignal?.removeEventListener("abort", cancel);
  }
}
export type SearchResponse = components["schemas"]["MovieSearchResponse"];
export const modeLabel: Record<DataMode, string> = {
  synthetic: "合成样例",
  live: "实时数据",
  cached: "缓存结果",
};
export const runtimeText = (movie: Movie) =>
  movie.runtime_minutes == null ? "片长未知" : `${movie.runtime_minutes} 分钟`;
