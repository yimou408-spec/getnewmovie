import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Tabs from "@radix-ui/react-tabs";
import { DiscoveryHero } from "./discovery-hero";
import * as Checkbox from "@radix-ui/react-checkbox";
import {
  ArrowRight,
  ArrowLeft,
  Bookmark,
  Check,
  ChevronRight,
  Clapperboard,
  Clock3,
  Film,
  GitCompareArrows,
  Info,
  Search,
  ShieldCheck,
  Sparkles,
  X,
  ExternalLink,
  Monitor,
  Moon,
  Heart,
  Telescope,
} from "lucide-react";
import {
  api,
  ApiError,
  buildRequest,
  discoverQuery,
  modeLabel,
  runtimeText,
  safeSourceUrl,
  validateResponse,
  type Candidate,
  type DataMode,
  type DiscoverPreferences,
  type Mode,
  type Movie,
  type Recommendation,
  type SearchResponse,
} from "./domain";
import { ErrorNotice } from "./request-feedback";
import { ServiceStatus } from "./service-status";
import { EvidencePanel, Ratings, SourceOpinions } from "./evidence";
import {
  reasonLabels,
  snapshotForComparison,
  type ComparedMovie,
} from "./evidence-model";

const initialDrafts: Record<Mode, string> = {
  discover: "",
  watchlist: "",
  known_movie: "",
};
const emptyPreferences: DiscoverPreferences = {
  moods: [],
  genres: [],
  company: "",
};
const ideas = [
  {
    title: "松弛一点",
    subtitle: "轻松喜剧 · 90 分钟内",
    moods: ["轻松解压"],
    genres: ["喜剧"],
    company: "",
    runtime: "90",
    icon: Moon,
  },
  {
    title: "约会之夜",
    subtitle: "两个人 · 爱情与浪漫",
    moods: ["浪漫心动"],
    genres: ["爱情"],
    company: "两个人",
    runtime: "",
    icon: Heart,
  },
  {
    title: "换个世界",
    subtitle: "科幻与奇幻 · 换一种想象",
    moods: ["惊奇冒险"],
    genres: ["科幻与奇幻"],
    company: "",
    runtime: "",
    icon: Telescope,
  },
  {
    title: "烧脑之夜",
    subtitle: "惊悚与悬念 · 想猜到最后",
    moods: ["烧脑过瘾"],
    genres: ["惊悚"],
    company: "",
    runtime: "",
    icon: Search,
  },
  {
    title: "全家一起",
    subtitle: "家人相伴 · 动画冒险",
    moods: ["温暖治愈"],
    genres: ["动画"],
    company: "和家人",
    runtime: "120",
    icon: Clapperboard,
  },
  {
    title: "留点余味",
    subtitle: "一个人 · 慢慢看个故事",
    moods: ["感动一下"],
    genres: ["剧情"],
    company: "一个人",
    runtime: "",
    icon: Film,
  },
];

function ChoiceGroup({
  label,
  options,
  selected,
  onChange,
  multiple = false,
  anyLabel = "不限",
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (value: string[]) => void;
  multiple?: boolean;
  anyLabel?: string;
}) {
  return (
    <fieldset className="preference-group">
      <legend>
        {label}
        <span>{multiple ? "可多选" : "可跳过"}</span>
      </legend>
      <div className="preference-options">
        <button
          type="button"
          aria-pressed={!selected.length}
          onClick={() => onChange([])}
        >
          {anyLabel}
        </button>
        {options.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={selected.includes(option)}
            onClick={() =>
              onChange(
                multiple
                  ? selected.includes(option)
                    ? selected.filter((item) => item !== option)
                    : [...selected, option]
                  : selected.includes(option)
                    ? []
                    : [option],
              )
            }
          >
            {selected.includes(option) && (
              <Check size={14} aria-hidden="true" />
            )}
            {option}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
function Button({
  children,
  className = "",
  type = "button",
  ...props
}: React.ComponentProps<"button">) {
  return (
    <button className={`button ${className}`} type={type} {...props}>
      {children}
    </button>
  );
}
function Badge({ mode }: { mode: DataMode | "unknown" }) {
  return (
    <span className="badge">
      <span aria-hidden="true" />
      {mode === "unknown" ? "来源模式未提供" : modeLabel[mode]}
    </span>
  );
}
function Empty({
  icon = <Film />,
  title,
  children,
}: {
  icon?: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon" aria-hidden="true">
        {icon}
      </span>
      <h2>{title}</h2>
      <div>{children}</div>
    </div>
  );
}
function Poster({ movie, small = false }: { movie: Movie; small?: boolean }) {
  const [status, setStatus] = useState<
    "loading" | "ready" | "error" | "timeout"
  >("loading");
  const [attempt, setAttempt] = useState(0);
  const url = safeSourceUrl(movie.poster_url);
  const canShow =
    url &&
    new URL(url).hostname.endsWith(".mzstatic.com") &&
    movie.source_url &&
    status !== "error" &&
    status !== "timeout";
  useEffect(() => {
    if (!canShow || status !== "loading") return;
    const timeout = window.setTimeout(() => setStatus("timeout"), 12000);
    return () => window.clearTimeout(timeout);
  }, [canShow, status, attempt]);
  return (
    <div className="poster-link">
      <Link
        to={`/film/${encodeURIComponent(movie.movie_id)}`}
        aria-label={`查看 ${movie.title} ${movie.year} 资料`}
        className={`poster ${small ? "small" : ""} ${canShow ? "has-artwork" : ""}`}
      >
        {canShow ? (
          <>
            <img
              key={attempt}
              src={`/api/artwork/${encodeURIComponent(movie.movie_id)}?attempt=${attempt}`}
              alt={`${movie.title} 海报`}
              loading="eager"
              decoding="async"
              width="170"
              height="255"
              onLoad={() => setStatus("ready")}
              onError={() => setStatus("error")}
            />
            {status === "loading" && (
              <small className="poster-loading">海报加载中…</small>
            )}
          </>
        ) : (
          <>
            <span className="poster-frame" aria-hidden="true">
              <Film size={small ? 24 : 40} />
            </span>
            <span className="poster-title">{movie.title}</span>
            <small>
              {status === "timeout"
                ? "海报加载超时"
                : status === "error"
                  ? "海报加载失败"
                  : "海报尚未提供"}
            </small>
          </>
        )}
      </Link>
      {(status === "error" || status === "timeout") && (
        <button
          type="button"
          className="poster-retry"
          aria-label={`重试 ${movie.title} 海报`}
          onClick={() => {
            setAttempt((previous) => previous + 1);
            setStatus("loading");
          }}
        >
          重试海报
        </button>
      )}
    </div>
  );
}
function StoreBadge({ movie }: { movie: Movie }) {
  const url = safeSourceUrl(movie.source_url);
  return url &&
    ["itunes.apple.com", "tv.apple.com"].includes(new URL(url).hostname) ? (
    <a
      className="store-badge"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`在 iTunes Store 查看 ${movie.title}（美国区，新窗口）`}
    >
      <img
        src="/itunes-store-badge.svg"
        alt="Get it on iTunes Store"
        width="110"
        height="40"
      />
      <span>美国区商店 · 非直接播放</span>
    </a>
  ) : null;
}
function MovieFacts({ movie }: { movie: Movie }) {
  return (
    <p className="facts">
      <span>{movie.year ?? "年份未知"}</span>
      <span>
        <Clock3 size={14} aria-hidden="true" />
        {runtimeText(movie)}
      </span>
      <span>{(movie.genres ?? []).join(" / ") || "类型未知"}</span>
    </p>
  );
}
function SourceLink({
  url,
  children,
}: {
  url?: string | null;
  children: ReactNode;
}) {
  const safe = safeSourceUrl(url);
  return safe ? (
    <a href={safe} target="_blank" rel="noopener noreferrer">
      {children}
      <ExternalLink size={13} aria-label="新窗口打开" />
    </a>
  ) : (
    <span>{children}（暂无可访问链接）</span>
  );
}

export default function App() {
  const [mode, setMode] = useState<Mode>("discover");
  const [drafts, setDrafts] = useState(initialDrafts);
  const [preferences, setPreferences] =
    useState<DiscoverPreferences>(emptyPreferences);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [runtime, setRuntime] = useState("");
  const [region, setRegion] = useState("CN");
  const [selected, setSelected] = useState<Movie>();
  const [saved, setSaved] = useState<Movie[]>([]);
  const [comparison, setComparison] = useState<ComparedMovie[]>([]);
  const [submittedResult, setResult] = useState<Recommendation>();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [resultRequest, setResultRequest] =
    useState<ReturnType<typeof buildRequest>>();
  const [snapshotQuery, setSnapshotQuery] = useState("");
  const [cancelled, setCancelled] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);
  const sessionId = useRef<string | undefined>(undefined);
  const inFlight = useRef(false);
  const lastAttempt = useRef<ReturnType<typeof buildRequest> | undefined>(
    undefined,
  );
  const [formError, setFormError] = useState<Error>();
  const [message, setMessage] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [clarificationStale, setClarificationStale] = useState(false);
  const [hidden, setHidden] = useState<string[]>([]);
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<"balanced" | "popular">("balanced");
  const [era, setEra] = useState<"any" | "recent" | "2000s" | "classic">("any");
  const [undo, setUndo] = useState<{
    saved?: Movie[];
    comparison?: ComparedMovie[];
    selected?: Movie;
  }>();
  const resultsRef = useRef<HTMLElement>(null);
  const composerRef = useRef<HTMLHeadingElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const discoverRef = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [pathKey, setPathKey] = useState(location.pathname);
  const opening = useQuery({
    queryKey: ["opening-selection", region],
    enabled: location.pathname === "/" && !submittedResult,
    staleTime: 1800000,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async ({ signal }) =>
      validateResponse(
        await api("/recommendations", {
          method: "POST",
          signal,
          body: JSON.stringify(
            buildRequest(
              "discover",
              discoverQuery(emptyPreferences, ""),
              region,
              "",
              [],
            ),
          ),
        }),
      ),
  });
  const result = submittedResult ?? opening.data;
  useEffect(() => {
    if (pathKey !== location.pathname) {
      activeRequest.current?.abort();
      activeRequest.current = null;
      inFlight.current = false;
      recommend.reset();
      if (result?.status === "needs_clarification") {
        setClarificationStale(true);
        setAnswers({});
      }
      setPathKey(location.pathname);
      setMessage("");
      setUndo(undefined);
      window.scrollTo(0, 0);
      document.querySelector<HTMLElement>("main")?.focus();
    }
  }, [location.pathname, pathKey]);
  useEffect(() => {
    document.title = `${location.pathname === "/compare" ? "影片对比" : location.pathname === "/watchlist" ? "本次片单" : location.pathname === "/preferences" ? "偏好与隐私" : location.pathname === "/about" ? "关于与接入状态" : location.pathname.startsWith("/film/") ? "影片资料" : "今晚看什么"} · 私人选片室`;
  }, [location.pathname]);
  const recommend = useMutation({
    mutationFn: async ({
      body,
      controller,
    }: {
      body: ReturnType<typeof buildRequest>;
      controller: AbortController;
    }) => {
      if (body.input_source === "natural_language") {
        if (!sessionId.current) {
          const session = await api<{ session_id: string }>("/sessions", {
            method: "POST",
            signal: controller.signal,
          });
          if (!/^[a-f0-9]{32}$/.test(session.session_id))
            throw new ApiError(
              "无法建立临时会话，请重试。",
              undefined,
              true,
              "invalid_response",
            );
          if (
            activeRequest.current === controller &&
            !controller.signal.aborted
          )
            sessionId.current = session.session_id;
        }
        body = { ...body, session_id: sessionId.current ?? "" };
      }
      if (activeRequest.current === controller) lastAttempt.current = body;
      const data = validateResponse(
        await api("/recommendations", {
          method: "POST",
          body: JSON.stringify(body),
          signal: controller.signal,
        }),
      );
      return { data, controller, body };
    },
    onSuccess: ({ data, controller, body }) => {
      if (activeRequest.current !== controller || controller.signal.aborted)
        return;
      setCancelled(false);
      setFiltersOpen(false);
      setResult(data);
      setResultRequest(body);
      setSnapshotQuery(body.query);
      setHidden([]);
      if (data.status === "needs_clarification") setAnswers({});
      requestAnimationFrame(() => {
        resultsRef.current?.focus();
        resultsRef.current?.scrollIntoView({
          behavior: "instant",
          block: "start",
        });
      });
    },
    onError: (error, { controller }) => {
      if (activeRequest.current !== controller) return;
      if (error instanceof ApiError && error.code === "SESSION_EXPIRED") {
        sessionId.current = undefined;
        setClarificationStale(true);
      }
      if (error instanceof ApiError && error.code === "STALE_CLARIFICATION")
        setClarificationStale(true);
    },
    onSettled: (_data, _error, { controller }) => {
      if (activeRequest.current === controller) inFlight.current = false;
    },
  });
  useEffect(() => () => activeRequest.current?.abort(), []);
  function startRecommendation(body: ReturnType<typeof buildRequest>) {
    if (inFlight.current) return;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    inFlight.current = true;
    lastAttempt.current = body;
    setCancelled(false);
    setMessage("");
    recommend.mutate({ body, controller });
  }
  function cancelRecommendation() {
    void queryClient.cancelQueries({ queryKey: ["opening-selection"] });
    activeRequest.current?.abort();
    activeRequest.current = null;
    inFlight.current = false;
    recommend.reset();
    setCancelled(true);
    setMessage(
      "已取消本次请求，上一批结果仍保留。取消只停止本页面等待，不保证上游任务已停止。",
    );
    discoverRef.current?.focus();
  }
  function invalidateClarification() {
    if (result?.status !== "needs_clarification" && !inFlight.current) return;
    activeRequest.current?.abort();
    activeRequest.current = null;
    inFlight.current = false;
    recommend.reset();
    setAnswers({});
    setClarificationStale(true);
  }
  function confirmClarification() {
    if (
      clarificationStale ||
      !resultRequest ||
      !result?.clarification_id ||
      !result.questions.every((q) =>
        q.options?.includes(answers[q.question_id]),
      )
    )
      return;
    startRecommendation({
      ...resultRequest,
      clarification: {
        clarification_id: result.clarification_id,
        answers: result.questions.map((q) => ({
          question_id: q.question_id,
          option: answers[q.question_id],
        })),
      },
    });
  }
  function submit(
    event?: FormEvent,
    discovery?: {
      preferences: DiscoverPreferences;
      runtime: string;
      note?: string;
    },
  ) {
    event?.preventDefault();
    if (inFlight.current) return;
    setFormError(undefined);
    setAnswers({});
    setClarificationStale(false);
    const requestMode = discovery ? "discover" : mode;
    const chosen = discovery?.preferences ?? preferences;
    if (discovery) {
      setMode("discover");
      setPreferences(chosen);
      setRuntime(discovery.runtime);
      setEra("any");
      setSortBy("balanced");
      setDrafts((current) => ({ ...current, discover: discovery.note ?? "" }));
    }
    try {
      const note = discovery ? (discovery.note ?? "") : drafts[requestMode];
      const body = buildRequest(
        requestMode,
        requestMode === "discover"
          ? note.trim() || discoverQuery(chosen, "")
          : note,
        region,
        discovery ? discovery.runtime : runtime,
        saved.map((m) => m.movie_id),
        selected,
        0,
        requestMode === "discover" ? [...chosen.moods, ...chosen.genres] : [],
        requestMode === "discover" ? chosen : undefined,
      );
      body.input_source = note.trim() ? "natural_language" : "structured";
      body.constraints = {
        company: "",
        ...body.constraints,
        exclude_movie_ids: dismissed,
        sort_by: discovery ? "balanced" : sortBy,
        era: discovery ? "any" : era,
      };
      startRecommendation(body);
    } catch (e) {
      setFormError(e as Error);
      resultsRef.current?.focus();
      resultsRef.current?.scrollIntoView({ block: "start" });
    }
  }
  function save(movie: Movie) {
    setUndo(
      saved.some((m) => m.movie_id === movie.movie_id)
        ? { saved: [movie] }
        : undefined,
    );
    setSaved((current) =>
      current.some((m) => m.movie_id === movie.movie_id)
        ? current.filter((m) => m.movie_id !== movie.movie_id)
        : [...current, movie],
    );
    setMessage("本次片单已更新；仅保留在当前页面会话，刷新即清空。");
  }
  function restore() {
    if (!undo) return;
    if (undo.saved)
      setSaved((current) => [
        ...new Map(
          [...current, ...undo.saved!].map((m) => [m.movie_id, m]),
        ).values(),
      ]);
    if (undo.comparison)
      setComparison((current) =>
        [
          ...new Map(
            [...current, ...undo.comparison!].map((m) => [m.movie_id, m]),
          ).values(),
        ].slice(0, 3),
      );
    if (undo.selected) setSelected(undo.selected);
    setUndo(undefined);
    setMessage("已撤销清空或移出操作。");
  }
  function compare(movie: Movie) {
    if (comparison.some((m) => m.movie_id === movie.movie_id))
      setComparison((current) =>
        current.filter((m) => m.movie_id !== movie.movie_id),
      );
    else if (comparison.length < 3)
      setComparison((current) => [
        ...current,
        snapshotForComparison(movie, result),
      ]);
    else setMessage("最多对比 3 部影片，请先移除一部。");
  }
  function editConditions() {
    setFiltersOpen(true);
    requestAnimationFrame(() => {
      composerRef.current?.focus({ preventScroll: true });
      composerRef.current?.scrollIntoView({ block: "start" });
    });
  }
  const selectedConditions = [
    ...preferences.moods.map((label) => ({
      label,
      remove: () =>
        setPreferences((current) => ({
          ...current,
          moods: current.moods.filter((value) => value !== label),
        })),
    })),
    ...preferences.genres.map((label) => ({
      label,
      remove: () =>
        setPreferences((current) => ({
          ...current,
          genres: current.genres.filter((value) => value !== label),
        })),
    })),
    ...(preferences.company
      ? [
          {
            label: preferences.company,
            remove: () =>
              setPreferences((current) => ({ ...current, company: "" })),
          },
        ]
      : []),
    ...(runtime
      ? [{ label: `${runtime} 分钟内`, remove: () => setRuntime("") }]
      : []),
    ...(era !== "any"
      ? [
          {
            label: {
              recent: "2020 年至今",
              "2000s": "2000—2019 年",
              classic: "2000 年以前",
            }[era],
            remove: () => setEra("any"),
          },
        ]
      : []),
    ...(sortBy === "popular"
      ? [{ label: "榜单顺序", remove: () => setSortBy("balanced") }]
      : []),
  ];
  const actions = (movie: Movie) => (
    <>
      <Button
        className="secondary"
        onClick={() => save(movie)}
        aria-pressed={saved.some((m) => m.movie_id === movie.movie_id)}
      >
        <Bookmark size={16} />
        {saved.some((m) => m.movie_id === movie.movie_id)
          ? "移出本次片单"
          : "加入本次片单"}
      </Button>
      <label className="check-label">
        <Checkbox.Root
          className="checkbox"
          checked={comparison.some((m) => m.movie_id === movie.movie_id)}
          onCheckedChange={() => compare(movie)}
          aria-label={`对比 ${movie.title} ${movie.year}`}
        >
          <Checkbox.Indicator>
            <Check size={14} />
          </Checkbox.Indicator>
        </Checkbox.Root>
        加入对比
      </label>
    </>
  );
  const knownCandidates = result?.candidates ?? [];
  function card(movie: Movie, candidate?: Candidate, index = 0) {
    return (
      <article
        className={`movie-card film-tile ${candidate ? "recommendation-card" : ""}`}
        key={movie.movie_id}
      >
        <div className="movie-summary">
          <div className="movie-cover">
            <Poster
              key={movie.poster_url ?? movie.movie_id}
              movie={movie}
              small={!candidate}
            />
            {candidate && (
              <span className="pick-number" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
            )}
          </div>
          <div className="movie-identity">
            <Badge
              mode={
                movie.movie_id.startsWith("syn:")
                  ? "synthetic"
                  : candidate
                    ? result!.data_mode
                    : "unknown"
              }
            />
            <div className="movie-heading">
              <h3>
                <Link to={`/film/${encodeURIComponent(movie.movie_id)}`}>
                  {movie.title}
                  <ChevronRight size={19} />
                </Link>
              </h3>
            </div>
            <MovieFacts movie={movie} />
            {movie.director && (
              <p className="muted movie-director">导演：{movie.director}</p>
            )}
          </div>
        </div>
        <div className="movie-body">
          {candidate ? (
            <>
              <div className="reason">
                <span>
                  <Sparkles size={16} aria-hidden="true" />
                  为什么放进候选
                </span>
                <p>{candidate.reason.text}</p>
                <small>
                  {reasonLabels[candidate.reason.kind]} · 不等同于观众口碑
                </small>
              </div>
              <Ratings movie={movie} evidence={result?.evidence} />
              <Availability candidate={candidate} />
              <details className="movie-context">
                <summary>查看资料与观看提醒</summary>
                <StoreBadge movie={movie} />
                {movie.content_advisory && (
                  <p className="muted">
                    美国内容分级：{movie.content_advisory} · 不代表本地适龄结论
                  </p>
                )}
                <div className="caveats">
                  {(candidate.caveats ?? []).map((c, i) => (
                    <p key={i}>
                      <Info size={15} aria-hidden="true" />
                      {c}
                    </p>
                  ))}
                  {(candidate.uncertain_conditions ?? []).map((c, i) => (
                    <p key={i}>待确认：{c}</p>
                  ))}
                </div>
              </details>
            </>
          ) : (
            <p className="muted">
              {(movie.tags ?? []).join(" / ") || "暂无更多标签"} ·
              仅提供基础资料
            </p>
          )}
          <div className="movie-actions">{actions(movie)}</div>
          {candidate && (
            <>
              <EvidencePanel
                movie={movie}
                candidate={candidate}
                evidence={result?.evidence ?? []}
                dataMode={result?.data_mode}
              />
              <Button
                className="text-button"
                onClick={() => {
                  setHidden((current) => [...current, movie.movie_id]);
                  setDismissed((current) =>
                    [...new Set([...current, movie.movie_id])].slice(-500),
                  );
                  setMessage(
                    "已从本次选片中排除；继续点选或换一组时都不会再推荐。刷新清空，可撤销。",
                  );
                }}
              >
                这次不想看
              </Button>
            </>
          )}
        </div>
      </article>
    );
  }
  return (
    <>
      <a className="skip-link" href="#main">
        跳到主要内容
      </a>
      <header className="site-header">
        <div className="header-inner">
          <Link className="brand" to="/" aria-label="今晚看什么 首页">
            <span className="brand-mark" aria-hidden="true">
              <Clapperboard size={23} />
            </span>
            <span>
              今晚看什么<small>私人选片室</small>
            </span>
          </Link>
          <nav aria-label="主导航">
            <NavLink to="/" end>
              选片
            </NavLink>
            <NavLink to="/watchlist">
              本次片单
              {saved.length > 0 && (
                <span className="count">{saved.length}</span>
              )}
            </NavLink>
            <NavLink to="/preferences">偏好与隐私</NavLink>
          </nav>
          <Link className="header-status" to="/about">
            <span aria-hidden="true" />
            真实片库
            <Info size={14} />
          </Link>
        </div>
      </header>
      <div className="demo-strip">
        <div>
          <Info size={16} aria-hidden="true" />
          <span>
            <strong>真实片库已接入</strong> · Apple 美国区电影榜单 ·
            类型、心情与时长参与匹配。
          </span>
          <Link to="/about">
            查看接入状态
            <ChevronRight size={14} />
          </Link>
        </div>
      </div>
      <main
        id="main"
        tabIndex={-1}
        className={`${comparison.length ? "with-tray" : ""} ${location.pathname === "/" ? "home-page" : ""}`}
      >
        <Routes>
          <Route
            path="/"
            element={
              <>
                <DiscoveryHero
                  movies={result?.candidates.map((item) => item.movie) ?? []}
                  loading={opening.isFetching || recommend.isPending}
                  renderPoster={(movie) => <Poster movie={movie} />}
                  onExplore={() => {
                    resultsRef.current?.scrollIntoView({ block: "start" });
                    resultsRef.current?.focus({ preventScroll: true });
                  }}
                  onCustomize={editConditions}
                />
                <div className="workspace">
                  <aside className="inspiration">
                    <div className="aside-heading">
                      <Sparkles size={19} aria-hidden="true" />
                      <h2>从一个场景开始</h2>
                    </div>
                    <p>选好氛围，剩下的交给我们。</p>
                    <div className="idea-list">
                      {ideas.map((idea) => (
                        <button
                          key={idea.title}
                          disabled={recommend.isPending}
                          onClick={() =>
                            submit(undefined, {
                              preferences: {
                                moods: idea.moods,
                                genres: idea.genres,
                                company: idea.company,
                              },
                              runtime: idea.runtime,
                            })
                          }
                        >
                          <span className="idea-icon" aria-hidden="true">
                            <idea.icon size={23} />
                          </span>
                          <span>
                            {idea.title}
                            <small>{idea.subtitle}</small>
                          </span>
                          <ArrowRight size={17} aria-hidden="true" />
                        </button>
                      ))}
                    </div>
                    <div className="principle">
                      <ShieldCheck size={20} />
                      <p>
                        <strong>让选择有据可依</strong>
                        <span>
                          区分资料、观点与推断。未知的评分与观看渠道，保持未知。
                        </span>
                      </p>
                    </div>
                  </aside>
                  <details
                    className="filter-workbench"
                    open={filtersOpen}
                    onToggle={(event) =>
                      setFiltersOpen(event.currentTarget.open)
                    }
                  >
                    <summary>
                      <span>按自己的想法找</span>
                      <span>类型、时长、片名与更多条件</span>
                      <ChevronRight size={20} aria-hidden="true" />
                    </summary>
                    <section
                      className="composer"
                      aria-labelledby="composer-title"
                    >
                      <div className="composer-heading">
                        <h2 id="composer-title" ref={composerRef} tabIndex={-1}>
                          精细选片
                        </h2>
                        <p>只调整在意的条件，其余交给我们。</p>
                      </div>
                      <Tabs.Root
                        value={mode}
                        onValueChange={(v) => {
                          invalidateClarification();
                          setMode(v as Mode);
                          setFormError(undefined);
                        }}
                      >
                        <Tabs.List className="mode-tabs" aria-label="选片方式">
                          <Tabs.Trigger value="discover">
                            <Sparkles size={16} />
                            不知道看什么
                          </Tabs.Trigger>
                          <Tabs.Trigger value="watchlist">
                            <Bookmark size={16} />
                            从片单中选
                          </Tabs.Trigger>
                          <Tabs.Trigger value="known_movie">
                            <Search size={16} />
                            已知道片名
                          </Tabs.Trigger>
                        </Tabs.List>
                        <Tabs.Content value={mode} className="mode-panel">
                          <form
                            onSubmit={submit}
                            onChangeCapture={invalidateClarification}
                            onClickCapture={(event) => {
                              if (
                                (event.target as HTMLElement).closest(
                                  'button:not([type="submit"])',
                                )
                              )
                                invalidateClarification();
                            }}
                          >
                            {mode === "discover" && (
                              <>
                                <div className="discovery-start">
                                  <Button
                                    className="primary"
                                    ref={discoverRef}
                                    onClick={() =>
                                      submit(undefined, {
                                        preferences: emptyPreferences,
                                        runtime: "",
                                      })
                                    }
                                    disabled={recommend.isPending}
                                  >
                                    <Sparkles size={18} aria-hidden="true" />
                                    什么都行，直接看看
                                    <ArrowRight size={17} aria-hidden="true" />
                                  </Button>
                                  <p>不用打字，先看 3 部真实电影</p>
                                </div>
                                <div className="preference-heading">
                                  <strong>给今晚一点方向</strong>
                                  <button
                                    type="button"
                                    className="reset-preferences"
                                    onClick={() => {
                                      setPreferences(emptyPreferences);
                                      setRuntime("");
                                      setEra("any");
                                      setSortBy("balanced");
                                      setDrafts((current) => ({
                                        ...current,
                                        discover: "",
                                      }));
                                    }}
                                  >
                                    清空选择
                                  </button>
                                </div>
                                <div className="discovery-preferences">
                                  <ChoiceGroup
                                    label="想要什么感觉？"
                                    anyLabel="不挑心情"
                                    multiple
                                    options={[
                                      "轻松解压",
                                      "温暖治愈",
                                      "烧脑过瘾",
                                      "浪漫心动",
                                      "惊奇冒险",
                                      "感动一下",
                                    ]}
                                    selected={preferences.moods}
                                    onChange={(moods) =>
                                      setPreferences((current) => ({
                                        ...current,
                                        moods,
                                      }))
                                    }
                                  />
                                  <ChoiceGroup
                                    label="想看哪种故事？"
                                    multiple
                                    options={[
                                      "喜剧",
                                      "科幻与奇幻",
                                      "惊悚",
                                      "动作",
                                      "爱情",
                                      "动画",
                                      "剧情",
                                      "家庭",
                                      "纪录片",
                                      "恐怖",
                                    ]}
                                    selected={preferences.genres}
                                    onChange={(genres) =>
                                      setPreferences((current) => ({
                                        ...current,
                                        genres,
                                      }))
                                    }
                                  />
                                  <ChoiceGroup
                                    label="今晚有多少时间？"
                                    options={[
                                      "90 分钟内",
                                      "120 分钟内",
                                      "150 分钟内",
                                      ...(runtime &&
                                      !["90", "120", "150"].includes(runtime)
                                        ? [`${runtime} 分钟内`]
                                        : []),
                                    ]}
                                    selected={
                                      runtime ? [`${runtime} 分钟内`] : []
                                    }
                                    onChange={(values) =>
                                      setRuntime(values[0]?.split(" ")[0] ?? "")
                                    }
                                  />
                                  <ChoiceGroup
                                    label="和谁一起看？（家人会筛选家庭/动画）"
                                    anyLabel="都可以"
                                    options={[
                                      "一个人",
                                      "两个人",
                                      "和朋友",
                                      "和家人",
                                    ]}
                                    selected={
                                      preferences.company
                                        ? [preferences.company]
                                        : []
                                    }
                                    onChange={(values) =>
                                      setPreferences((current) => ({
                                        ...current,
                                        company: values[0] ?? "",
                                      }))
                                    }
                                  />
                                  <ChoiceGroup
                                    label="想看哪个年代？"
                                    anyLabel="不限年代"
                                    options={[
                                      "2020 年至今",
                                      "2000—2019 年",
                                      "2000 年以前",
                                    ]}
                                    selected={
                                      era === "any"
                                        ? []
                                        : [
                                            {
                                              recent: "2020 年至今",
                                              "2000s": "2000—2019 年",
                                              classic: "2000 年以前",
                                            }[era],
                                          ]
                                    }
                                    onChange={(values) =>
                                      setEra(
                                        values[0] === "2020 年至今"
                                          ? "recent"
                                          : values[0] === "2000—2019 年"
                                            ? "2000s"
                                            : values[0] === "2000 年以前"
                                              ? "classic"
                                              : "any",
                                      )
                                    }
                                  />
                                  <ChoiceGroup
                                    label="怎么安排候选？"
                                    anyLabel="均衡探索"
                                    options={["榜单顺序"]}
                                    selected={
                                      sortBy === "popular" ? ["榜单顺序"] : []
                                    }
                                    onChange={(values) =>
                                      setSortBy(
                                        values.length ? "popular" : "balanced",
                                      )
                                    }
                                  />
                                </div>
                                <div
                                  className="selection-summary"
                                  aria-label="已选条件"
                                  role="status"
                                >
                                  {selectedConditions.length ? (
                                    <>
                                      <span className="selection-caption">
                                        已选 {selectedConditions.length} 项
                                      </span>
                                      {selectedConditions.map((condition) => (
                                        <button
                                          key={condition.label}
                                          type="button"
                                          onClick={condition.remove}
                                          aria-label={`移除条件 ${condition.label}`}
                                        >
                                          {condition.label}
                                          <X size={13} aria-hidden="true" />
                                        </button>
                                      ))}
                                    </>
                                  ) : (
                                    <span>不设条件也可以，直接看看就好。</span>
                                  )}
                                </div>
                                <p className="mock-limit">
                                  <Info size={15} aria-hidden="true" />
                                  类型、年代和时长严格筛选。心情结合类型与简介词法线索推断；均衡探索会分散类型和导演，不代表口碑评分。
                                </p>
                              </>
                            )}
                            <div className="field natural-input">
                              <label htmlFor="mood">
                                {mode === "known_movie"
                                  ? "关于这部电影，你在意什么？"
                                  : "说说今晚想看什么（可选）"}
                              </label>
                              <textarea
                                id="mood"
                                name="query"
                                autoComplete="off"
                                ref={textareaRef}
                                value={drafts[mode]}
                                onChange={(e) =>
                                  setDrafts((current) => ({
                                    ...current,
                                    [mode]: e.target.value,
                                  }))
                                }
                                placeholder="例如：想看轻松的喜剧，两个小时以内，不要恐怖片。"
                                maxLength={mode === "discover" ? 1500 : 2000}
                                rows={2}
                                aria-describedby="mood-help"
                              />
                              <div className="input-help" id="mood-help">
                                <span>
                                  不填也能选。支持常见类型、心情、时长和排除；无法执行的要求会先请你确认。
                                </span>
                                <span>
                                  {drafts[mode].length}/
                                  {mode === "discover" ? 1500 : 2000}
                                </span>
                              </div>
                            </div>
                            {mode === "known_movie" && (
                              <>
                                <MovieLookup
                                  onChoose={(movie) => {
                                    setSelected(movie);
                                    setMessage(
                                      `已确认 ${movie.title}（${movie.year}）`,
                                    );
                                  }}
                                  chooseLabel="确认这部"
                                />
                                {selected && (
                                  <div className="confirmed">
                                    <Check size={16} />
                                    已确认：{selected.title}（{selected.year}）
                                    <Button
                                      className="text-button"
                                      onClick={() => setSelected(undefined)}
                                    >
                                      取消确认
                                    </Button>
                                  </div>
                                )}
                              </>
                            )}
                            {mode === "watchlist" && (
                              <p className="mode-hint">
                                {saved.length
                                  ? `将从本次片单的 ${saved.length} 部影片中选择。`
                                  : "本次片单还是空的。先查找影片并加入，再回到这里选片。"}{" "}
                                <Link to="/watchlist">管理本次片单</Link>
                              </p>
                            )}
                            <details
                              className="optional-preferences"
                              open={mode !== "discover" || detailsOpen}
                              onToggle={(event) => {
                                if (mode === "discover")
                                  setDetailsOpen(event.currentTarget.open);
                              }}
                            >
                              <summary>精确时长与观看地区（可选）</summary>
                              <div className="constraints">
                                <div className="field">
                                  <label htmlFor="runtime">
                                    最多看多久 <span>（可选）</span>
                                  </label>
                                  <div className="number-input">
                                    <input
                                      id="runtime"
                                      name="max_runtime_minutes"
                                      autoComplete="off"
                                      type="number"
                                      min="1"
                                      max="600"
                                      step="1"
                                      inputMode="numeric"
                                      value={runtime}
                                      onChange={(e) => setRuntime(e.target.value)}
                                      placeholder="不限"
                                    />
                                    <span>分钟</span>
                                  </div>
                                </div>
                                <div className="field">
                                  <label htmlFor="region">观看地区</label>
                                  <select
                                    id="region"
                                    name="region"
                                    autoComplete="off"
                                    value={region}
                                    onChange={(e) => setRegion(e.target.value)}
                                  >
                                    <option value="CN">中国大陆</option>
                                    <option value="HK">中国香港</option>
                                    <option value="TW">中国台湾</option>
                                    <option value="JP">日本</option>
                                    <option value="US">美国</option>
                                  </select>
                                </div>
                              </div>
                            </details>
                            <div className="composer-bottom">
                              <p>
                                <ShieldCheck size={16} aria-hidden="true" />
                                可跳过所有选项 · 不写入长期记忆
                              </p>
                              <Button
                                className="primary"
                                type="submit"
                                disabled={recommend.isPending}
                              >
                                {recommend.isPending
                                  ? "正在查找电影…"
                                  : "看看候选电影"}
                                {!recommend.isPending && <ArrowRight size={17} />}
                              </Button>
                            </div>
                          </form>
                        </Tabs.Content>
                      </Tabs.Root>
                    </section>
                  </details>
                </div>
                <section
                  className="results"
                  ref={resultsRef}
                  tabIndex={-1}
                  aria-labelledby="results-title"
                  aria-busy={recommend.isPending}
                >
                  <div className="section-heading">
                    <h2 id="results-title">
                      {result
                        ? recommend.isError || recommend.isPending || cancelled
                          ? "上次候选结果"
                          : "你的候选电影"
                        : "把今晚留给合适的一部"}
                    </h2>
                    <span>
                      {result
                        ? `${result.candidates.length} 部候选 / 最多 3 部`
                        : "不必填写，点一下就能开始"}
                    </span>
                  </div>
                  {(formError || recommend.error || (!result && opening.error)) && (
                    <ErrorNotice
                      error={formError ?? recommend.error ?? opening.error!}
                      retry={
                        recommend.error instanceof ApiError &&
                        recommend.error.retryable
                          ? () => {
                              if (lastAttempt.current)
                                startRecommendation(lastAttempt.current);
                            }
                          : undefined
                      }
                    />
                  )}
                  {(recommend.isPending || (!result && opening.isFetching)) && (
                    <div className="loading" role="status">
                      <div className="skeleton" />
                      <p>正在从真实片库匹配电影…</p>
                      <small>不会自动重复请求。</small>
                      <Button
                        className="secondary"
                        onClick={cancelRecommendation}
                      >
                        取消本次请求
                      </Button>
                    </div>
                  )}
                  {result && (
                    <>
                      <div className="result-context">
                        {result.status === "needs_clarification" ? (
                          <>
                            {result.data_mode === "synthetic" && (
                              <Badge mode="synthetic" />
                            )}
                            <span className="badge">待确认 · 尚未查询片库</span>
                          </>
                        ) : (
                          <Badge mode={result.data_mode} />
                        )}
                        <span>已提交偏好：{snapshotQuery || "随意探索 · 未设筛选条件"}</span>
                        <small>
                          {result.memory_used
                            ? "服务报告使用了记忆"
                            : "未使用长期记忆"}
                        </small>
                      </div>
                      {result.status !== "needs_clarification" && (
                        <p className="match-summary">
                          当前查得 {result.catalog_size ?? "未知"} 部 · 符合条件{" "}
                          {result.matched_count ?? result.candidates.length} 部
                          · 本次展示 {result.candidates.length} 部
                        </p>
                      )}
                      {result.interpretation && (
                        <section
                          className="intent-summary"
                          aria-label="本次条件解释"
                        >
                          <h3>
                            {result.status === "needs_clarification"
                              ? "已识别条件（待确认）"
                              : "已识别条件"}
                          </h3>
                          <p className="intent-method">
                            规则解析 · 心情仅作软偏好
                          </p>
                          <ul>
                            {(result.interpretation.hard_conditions ?? []).map(
                              (item) => (
                                <li key={item}>{item}</li>
                              ),
                            )}
                            {(result.interpretation.soft_preferences ?? []).map(
                              (item) => (
                                <li key={item}>{item}</li>
                              ),
                            )}
                          </ul>
                          {!result.interpretation.hard_conditions?.length &&
                            !result.interpretation.soft_preferences?.length && (
                              <p>未指定可执行条件，按当前榜单探索。</p>
                            )}
                          {(result.interpretation.conflicts ?? []).map(
                            (item) => (
                              <p className="intent-warning" key={item}>
                                待确认：{item}
                              </p>
                            ),
                          )}
                          {(result.interpretation.unhandled ?? []).map(
                            (item) => (
                              <p className="intent-warning" key={item}>
                                未执行：{item}
                              </p>
                            ),
                          )}
                        </section>
                      )}
                      {dismissed.length > 0 && (
                        <div className="selection-summary" role="status">
                          本次已排除 {dismissed.length} 部，后续选片继续生效。
                          <Button
                            className="text-button"
                            onClick={() => {
                              setDismissed([]);
                              setHidden([]);
                              setMessage("已撤销本次排除，刷新页面也会清空。");
                            }}
                          >
                            撤销本次排除
                          </Button>
                        </div>
                      )}
                      {result.warnings.length > 0 && (
                        <div className="result-limits">
                          <p>
                            <ShieldCheck size={16} aria-hidden="true" />
                            {result.data_mode === "synthetic"
                              ? "离线合成数据，仅用于接口验收。"
                              : "单一来源片库 · 未获取豆瓣评分 · 本地观看渠道未知"}
                          </p>
                          <details
                            open={
                              result.data_mode === "synthetic" ||
                              result.status === "degraded"
                            }
                          >
                            <summary>
                              数据边界与说明（{result.warnings.length}）
                            </summary>
                            {result.warnings.map((warning, i) => (
                              <p key={i}>{warning}</p>
                            ))}
                          </details>
                        </div>
                      )}
                      {result.status === "needs_clarification" && (
                        <div className="clarification">
                          <h3>再补充一点想法</h3>
                          {result.questions.map((q) => (
                            <fieldset
                              key={q.question_id}
                              disabled={
                                recommend.isPending || clarificationStale
                              }
                            >
                              <legend>{q.text}</legend>
                              <div className="choice-row">
                                {(q.options ?? []).map((option) => (
                                  <label
                                    className="clarification-option"
                                    key={option}
                                  >
                                    <input
                                      type="radio"
                                      name={`clarification-${q.question_id}`}
                                      value={option}
                                      checked={
                                        answers[q.question_id] === option
                                      }
                                      onChange={() =>
                                        setAnswers((current) => ({
                                          ...current,
                                          [q.question_id]: option,
                                        }))
                                      }
                                    />
                                    {option}
                                  </label>
                                ))}
                              </div>
                            </fieldset>
                          ))}
                          {clarificationStale && (
                            <p role="status">
                              条件已变更或会话已过期。请在上方重新提交，旧答案不会继续使用。
                            </p>
                          )}
                          <div className="choice-row">
                            <Button
                              className="primary"
                              onClick={confirmClarification}
                              disabled={
                                clarificationStale ||
                                recommend.isPending ||
                                !result.clarification_id ||
                                !result.questions.every((q) =>
                                  q.options?.includes(answers[q.question_id]),
                                )
                              }
                            >
                              确认并继续推荐{" "}
                              <ArrowRight size={17} aria-hidden="true" />
                            </Button>
                            <Button
                              className="secondary"
                              onClick={() => {
                                invalidateClarification();
                                textareaRef.current?.focus();
                                textareaRef.current?.scrollIntoView({
                                  block: "center",
                                });
                              }}
                            >
                              修改观影想法
                            </Button>
                          </div>
                          <small>
                            请确认每个问题后继续；也可以修改文字重新提交。确认前不会查询或展示电影候选。
                          </small>
                        </div>
                      )}
                      {result.candidates.length > 0 && (
                        <div className="result-toolbar">
                          <Button
                            className="secondary"
                            onClick={editConditions}
                          >
                            修改选片条件
                          </Button>
                          <Button
                            className="secondary"
                            disabled={recommend.isPending}
                            onClick={() => {
                              const previous = resultRequest;
                              if (previous)
                                startRecommendation({
                                  ...previous,
                                  constraints: {
                                    company: "",
                                    sort_by: "balanced",
                                    era: "any",
                                    ...previous.constraints,
                                    exclude_movie_ids: [
                                      ...new Set([
                                        ...(previous.constraints
                                          ?.exclude_movie_ids ?? []),
                                        ...dismissed,
                                        ...result.candidates.map(
                                          (c) => c.movie.movie_id,
                                        ),
                                      ]),
                                    ].slice(-500),
                                  },
                                });
                            }}
                          >
                            换一组真实电影
                          </Button>
                        </div>
                      )}
                      <div className="candidate-grid">
                        {result.candidates
                          .filter((c) => !hidden.includes(c.movie.movie_id))
                          .map((c, index) => card(c.movie, c, index))}
                      </div>
                      {(result.status === "empty" ||
                        (result.status === "degraded" &&
                          !result.candidates.length)) && (
                        <Empty
                          title={
                            result.status === "empty"
                              ? "这次还没有合适的候选"
                              : "推荐服务暂时降级"
                          }
                        >
                          <p>试着放宽片长、年代或类型条件，也可以稍后再试。</p>
                          <Button
                            className="secondary"
                            onClick={() => {
                              setPreferences(emptyPreferences);
                              setRuntime("");
                              setEra("any");
                              setSortBy("balanced");
                              setDetailsOpen(false);
                              requestAnimationFrame(() =>
                                discoverRef.current?.focus(),
                              );
                            }}
                          >
                            清空筛选条件
                          </Button>
                        </Empty>
                      )}
                      {result.candidates.length > 0 &&
                        result.candidates.every((c) =>
                          hidden.includes(c.movie.movie_id),
                        ) && (
                          <Empty title="本次候选已隐藏">
                            <p>
                              这些影片将在本次页面会话中持续排除。可换一组，也可撤销排除。
                            </p>
                            <Button
                              className="secondary"
                              onClick={() => {
                                setHidden([]);
                                setDismissed([]);
                              }}
                            >
                              恢复显示
                            </Button>
                          </Empty>
                        )}
                      <small className="trace">
                        请求编号：{result.trace_id} · 契约{" "}
                        {result.contract_version}
                      </small>
                    </>
                  )}
                  {!result && !recommend.isPending && (
                    <div className="pre-result">
                      <Film size={28} aria-hidden="true" />
                      <p>
                        不用想好，也不用打字。
                        <br />
                        <strong>点选一个场景，或直接看看三部真实电影。</strong>
                      </p>
                    </div>
                  )}
                </section>
              </>
            }
          />
          <Route
            path="/watchlist"
            element={
              <>
                <PageHeading
                  title="本次片单"
                  subtitle="把想看的先放在一起，再决定今晚看哪部。"
                />
                <div className="notice">
                  <Info />
                  <span>
                    仅在当前页面会话保留，刷新或关闭即清空；云端片单与账号尚未接入。
                  </span>
                </div>
                <section className="lookup-panel">
                  <h2>找一部想看的电影</h2>
                  <MovieLookup
                    onChoose={save}
                    chooseLabel="加入本次片单"
                    saved={saved}
                  />
                </section>
                {saved.length ? (
                  <>
                    <div className="section-heading">
                      <h2>已加入 {saved.length} 部</h2>
                      <Button
                        className="secondary"
                        onClick={() => {
                          setMode("watchlist");
                          navigate("/");
                        }}
                      >
                        从这些电影中选
                        <ArrowRight size={16} />
                      </Button>
                    </div>
                    <div className="movie-grid">
                      {saved.map((m) => card(m))}
                    </div>
                  </>
                ) : (
                  <Empty icon={<Bookmark />} title="第一部，留给你想看的">
                    <p>
                      输入来源中的原文片名，核对年份后加入。本次片单刷新后清空。
                    </p>
                  </Empty>
                )}
              </>
            }
          />
          <Route
            path="/compare"
            element={<Compare movies={comparison} onRemove={compare} />}
          />
          <Route
            path="/film/:movieId"
            element={
              <FilmPage candidates={knownCandidates} renderCard={card} />
            }
          />
          <Route
            path="/preferences"
            element={
              <>
                <PageHeading
                  title="偏好与隐私"
                  subtitle="每一次选择，都应该由你掌握。"
                />
                <div className="settings">
                  <section>
                    <ShieldCheck />
                    <div>
                      <h2>长期记忆尚未启用</h2>
                      <p>
                        所有推荐请求均发送 memory_enabled:
                        false。当前没有偏好读写或删除接口。
                      </p>
                      <label className="check-label disabled">
                        <Checkbox.Root
                          disabled
                          className="checkbox"
                          aria-label="记住我的观影偏好"
                        />
                        记住我的观影偏好（待后端接入）
                      </label>
                    </div>
                  </section>
                  <section>
                    <Bookmark />
                    <div>
                      <h2>片单只保留在本次会话</h2>
                      <p>
                        内容保存在当前页面内存中，不写入本地存储。刷新或关闭页面会清空。
                      </p>
                      <Button
                        className="secondary"
                        disabled={!saved.length && !comparison.length}
                        onClick={() => {
                          setUndo({ saved, comparison, selected });
                          setSaved([]);
                          setComparison([]);
                          setSelected(undefined);
                          setMessage("已清空本次片单、对比与确认影片。");
                        }}
                      >
                        清空本次片单与对比
                      </Button>
                    </div>
                  </section>
                  <section>
                    <Monitor />
                    <div>
                      <h2>外观跟随系统</h2>
                      <p>
                        界面自动适配系统的浅色或深色设置，系统切换时立即生效。
                      </p>
                    </div>
                  </section>
                  <section>
                    <Info />
                    <div>
                      <h2>数据控制的接入边界</h2>
                      <p>
                        账号、历史记录、偏好导出与服务端数据删除均未实现。上面的清空操作只作用于当前页面，不代表删除服务端数据。
                      </p>
                      <Link to="/about">
                        查看全部接入状态
                        <ChevronRight size={15} />
                      </Link>
                    </div>
                  </section>
                </div>
              </>
            }
          />
          <Route path="/about" element={<About />} />
          <Route
            path="*"
            element={
              <Empty title="这一页还没有开场">
                <p>页面不存在，回选片室重新开始。</p>
                <Link className="button primary" to="/">
                  回到选片
                </Link>
              </Empty>
            }
          />
        </Routes>
      </main>
      <footer>
        <span>
          <Clapperboard size={16} aria-hidden="true" />
          今晚看什么
        </span>
        <p>少一点犹豫，留一点时间给电影。</p>
        <Link to="/about">关于与数据说明</Link>
      </footer>
      {comparison.length > 0 && location.pathname !== "/compare" && (
        <div className="compare-tray">
          <div>
            <GitCompareArrows size={20} />
            <span>
              已选 {comparison.length}/3 部
              <span className="tray-names">
                {comparison.map((m) => m.title).join("、")}
              </span>
            </span>
            <Button
              className="text-button"
              onClick={() => {
                setUndo({ comparison });
                setComparison([]);
                setMessage("已清空对比选择，可以撤销。");
              }}
            >
              清空
            </Button>
            <Link
              className={`button primary ${comparison.length < 2 ? "is-disabled" : ""}`}
              aria-disabled={comparison.length < 2}
              to="/compare"
              onClick={(e) => {
                if (comparison.length < 2) e.preventDefault();
              }}
            >
              {comparison.length < 2 ? "再选 1 部即可对比" : "开始对比"}
              <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      )}
      <div className="toast-region" role="status" aria-live="polite">
        {message && (
          <div className="toast">
            <Info size={17} />
            <span>{message}</span>
            {undo && (
              <Button className="text-button" onClick={restore}>
                撤销
              </Button>
            )}
            <button
              aria-label="关闭提示"
              onClick={() => {
                setMessage("");
                setUndo(undefined);
              }}
            >
              <X size={17} />
            </button>
          </div>
        )}
      </div>
    </>
  );
}

function PageHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="page-heading">
      <Link to="/" className="back-link">
        <ArrowLeft size={16} />
        回选片室
      </Link>
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </div>
  );
}
function Availability({ candidate }: { candidate: Candidate }) {
  const labels = {
    unknown: "观看渠道未知",
    stale: "渠道信息已过期",
    listed: "来源列出此渠道，尚需自行确认",
    search_entry: "仅提供搜索入口，未确认可观看",
  };
  return (
    <div className="availability">
      {candidate.availability.map((a, i) => (
        <div key={i}>
          <strong>
            {a.region} · {labels[a.status]}
          </strong>
          {a.provider && <span>{a.provider}</span>}
          {a.checked_at && <small>检查时间：{a.checked_at}</small>}
          {a.status !== "unknown" && (
            <SourceLink url={a.url}>核对渠道</SourceLink>
          )}
        </div>
      ))}
    </div>
  );
}
function MovieLookup({
  onChoose,
  chooseLabel,
  saved = [],
}: {
  onChoose: (movie: Movie) => void;
  chooseLabel: string;
  saved?: Movie[];
}) {
  const [query, setQuery] = useState("");
  const [year, setYear] = useState("");
  const [searched, setSearched] = useState(false);
  const activeSearch = useRef<AbortController | null>(null);
  const invalidYear =
    Boolean(year) &&
    (!Number.isInteger(Number(year)) ||
      Number(year) < 1888 ||
      Number(year) > 2200);
  const search = useMutation({
    mutationFn: async (input: {
      query: string;
      year: string;
      controller: AbortController;
    }) => {
      const data = await api<SearchResponse>(
        `/movies?query=${encodeURIComponent(input.query)}${input.year ? `&year=${input.year}` : ""}`,
        { signal: input.controller.signal },
      );
      if (
        !Array.isArray(data.movies) ||
        !["synthetic", "live", "cached"].includes(data.data_mode)
      )
        throw new Error("影片查找返回的数据不完整。");
      return data;
    },
  });
  useEffect(() => () => activeSearch.current?.abort(), []);
  const invalidateSearch = () => {
    activeSearch.current?.abort();
    activeSearch.current = null;
    search.reset();
    setSearched(false);
  };
  const run = () => {
    if (query.trim() && !invalidYear && !search.isPending) {
      const controller = new AbortController();
      activeSearch.current = controller;
      setSearched(true);
      search.mutate({ query: query.trim(), year, controller });
    }
  };
  return (
    <div className="movie-lookup">
      <div className="lookup-fields">
        <div className="field">
          <label htmlFor={`lookup-${chooseLabel}`}>影片名称</label>
          <input
            id={`lookup-${chooseLabel}`}
            name="movie_title"
            autoComplete="off"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              invalidateSearch();
            }}
            placeholder="输入来源原文片名"
            maxLength={100}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                run();
              }
            }}
          />
        </div>
        <div className="field year">
          <label htmlFor={`year-${chooseLabel}`}>年份（可选）</label>
          <input
            id={`year-${chooseLabel}`}
            name="movie_year"
            autoComplete="off"
            inputMode="numeric"
            type="number"
            min="1888"
            max="2200"
            value={year}
            aria-invalid={invalidYear || undefined}
            aria-describedby={
              invalidYear ? `year-error-${chooseLabel}` : undefined
            }
            onChange={(e) => {
              setYear(e.target.value);
              invalidateSearch();
            }}
            placeholder="如 2024"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                run();
              }
            }}
          />
          {invalidYear && (
            <small id={`year-error-${chooseLabel}`} role="alert">
              年份请输入 1888–2200 之间的整数。
            </small>
          )}
        </div>
        <Button
          type="button"
          className="secondary"
          disabled={!query.trim() || search.isPending || invalidYear}
          onClick={run}
        >
          <Search size={16} />
          {search.isPending ? "查找中…" : "查找影片"}
        </Button>
      </div>
      <p className="muted small-text">
        检索 Apple
        美国区当前分类榜单，非全量片库；请用来源原文片名，中文译名可能查不到。
      </p>
      {search.error && <ErrorNotice error={search.error} retry={run} />}
      {searched && search.data && !search.isPending && !search.error && (
        <div className="lookup-results" aria-live="polite">
          <Badge mode={search.data.data_mode} />
          <p>
            {search.data.movies.length
              ? search.data.requires_confirmation
                ? "找到同名影片，请确认具体年份。"
                : "请核对影片后确认。"
              : "没有找到影片。请核对来源原文片名，或清空年份后重试；当前仅检索 Apple 美国区分类榜单。"}
          </p>
          {search.data.movies.map((m) => (
            <div className="lookup-item" key={m.movie_id}>
              <div>
                <strong>
                  {m.title}（{m.year ?? "年份未知"}）
                </strong>
                <MovieFacts movie={m} />
                <StoreBadge movie={m} />
              </div>
              <Button
                type="button"
                className="secondary"
                disabled={saved.some((s) => s.movie_id === m.movie_id)}
                onClick={() => onChoose(m)}
              >
                {saved.some((s) => s.movie_id === m.movie_id)
                  ? "已加入"
                  : chooseLabel}
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
function FilmPage({
  candidates,
  renderCard,
}: {
  candidates: Candidate[];
  renderCard: (movie: Movie, candidate?: Candidate) => ReactNode;
}) {
  const { movieId } = useParams();
  const existing = candidates.find((c) => c.movie.movie_id === movieId);
  const query = useQuery({
    queryKey: ["film", movieId],
    queryFn: ({ signal }) =>
      api<Movie>(`/movies/${encodeURIComponent(movieId!)}`, { signal }),
    enabled: !existing,
    staleTime: 60000,
  });
  return (
    <>
      <PageHeading
        title="影片资料"
        subtitle="确认片名与年份，了解选择背后的理由。"
      />
      {query.isPending && !existing ? (
        <p role="status">正在读取影片资料…</p>
      ) : query.error && !existing ? (
        <ErrorNotice
          error={query.error}
          retry={() => {
            void query.refetch();
          }}
        />
      ) : (
        (existing?.movie || query.data) &&
        renderCard((existing?.movie || query.data)!, existing)
      )}
      <div className="notice">
        <Info />
        <span>
          当前资料包含来源提供的导演、海报等字段，缺失项保持未知；口碑评分、影评与本地观看渠道尚未接入。
        </span>
      </div>
    </>
  );
}
function Compare({
  movies,
  onRemove,
}: {
  movies: ComparedMovie[];
  onRemove: (m: Movie) => void;
}) {
  const ids = movies.map((m) => m.movie_id);
  const query = useQuery({
    queryKey: ["compare", ...ids],
    queryFn: ({ signal }) =>
      api<SearchResponse>("/comparisons", {
        method: "POST",
        body: JSON.stringify({ movie_ids: ids }),
        signal,
      }),
    enabled: ids.length >= 2,
    staleTime: 60000,
  });
  return (
    <>
      <PageHeading
        title="把选择放在一起看"
        subtitle="并排核对关键信息，让今晚的选择更清楚。"
      />
      {movies.length < 2 ? (
        <Empty icon={<GitCompareArrows />} title="选好两部，就可以对比">
          <p>从候选或本次片单勾选 2–3 部影片。</p>
          <Link to="/watchlist" className="button secondary">
            去本次片单
          </Link>
        </Empty>
      ) : (
        <>
          {query.isPending && <p role="status">正在核对影片资料…</p>}
          {query.error && (
            <ErrorNotice
              error={query.error}
              retry={() => {
                void query.refetch();
              }}
            />
          )}
          <div className="notice">
            <Info />
            <span>
              基础资料由对比接口提供。推荐与证据沿用加入对比时的快照，未获取的评分和渠道保持未知。不同影片的来源观点并列展示，不生成未经证实的差异结论。
            </span>
          </div>
          {query.data && (
            <>
              <Badge mode={query.data.data_mode} />
              <p className="small-text muted">
                窄屏可左右滑动表格，影片维度固定在左侧。
              </p>
              <div
                className="table-scroll"
                role="region"
                aria-label="影片对比表，可左右滚动"
                tabIndex={0}
              >
                <table>
                  <thead>
                    <tr>
                      <th scope="col">对比维度</th>
                      {query.data.movies.map((m) => (
                        <th scope="col" key={m.movie_id}>
                          <Link to={`/film/${encodeURIComponent(m.movie_id)}`}>
                            {m.title}
                            <small>{m.year ?? "年份未知"}</small>
                          </Link>
                          <Button
                            className="text-button"
                            onClick={() => onRemove(m)}
                            aria-label={`移除对比 ${m.title} ${m.year}`}
                          >
                            <X size={15} />
                            移除
                          </Button>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      "片长",
                      "国家 / 地区",
                      "类型",
                      "标签",
                      "评分",
                      "推荐理由",
                      "来源观点",
                      "证据与出处",
                      "观看渠道",
                    ].map((row, i) => (
                      <tr key={row}>
                        <th scope="row">{row}</th>
                        {query.data!.movies.map((m) => {
                          const snapshot = movies.find(
                            (selected) => selected.movie_id === m.movie_id,
                          )?.snapshot;
                          const c = snapshot?.candidate;
                          return (
                            <td key={m.movie_id}>
                              {i === 0 ? (
                                runtimeText(m)
                              ) : i === 1 ? (
                                (m.countries ?? []).join(" / ") || "未提供"
                              ) : i === 2 ? (
                                (m.genres ?? []).join(" / ") || "未提供"
                              ) : i === 3 ? (
                                (m.tags ?? []).join(" / ") || "未提供"
                              ) : i === 4 ? (
                                <Ratings
                                  movie={c?.movie ?? m}
                                  evidence={snapshot?.evidence}
                                />
                              ) : i === 5 ? (
                                c ? (
                                  <>
                                    <small className="muted">
                                      {reasonLabels[c.reason.kind]}
                                    </small>
                                    <p>{c.reason.text}</p>
                                  </>
                                ) : (
                                  "本次尚未获取"
                                )
                              ) : i === 6 ? (
                                <SourceOpinions
                                  movie={m}
                                  evidence={snapshot?.evidence ?? []}
                                />
                              ) : i === 7 ? (
                                <EvidencePanel
                                  movie={c?.movie ?? m}
                                  candidate={c}
                                  evidence={snapshot?.evidence ?? []}
                                  dataMode={snapshot?.dataMode}
                                  snapshot={Boolean(snapshot)}
                                />
                              ) : c ? (
                                <Availability candidate={c} />
                              ) : (
                                "未知，尚未获取"
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}
function About() {
  return (
    <>
      <PageHeading
        title="关于与接入状态"
        subtitle="呈现已经拥有的，也说明仍然缺少的。"
      />
      <div className="about-intro">
        <Clapperboard size={32} />
        <h2>为一场恰好的电影，少做一点选择题。</h2>
        <p>
          电影资料来自 Apple
          美国区公开电影榜单及影片查询接口，按点选条件实时匹配。心情结合类型与简介词法线索推断，均衡探索会分散类型与导演，不是模型或影评结论。来源缓存
          30 分钟，保留采集时间。
        </p>
      </div>
      <ServiceStatus />
      <h2 className="section-heading">页面功能与使用边界</h2>
      <div
        className="table-scroll"
        role="region"
        aria-label="页面功能与使用边界"
        tabIndex={0}
      >
        <table className="capabilities">
          <thead>
            <tr>
              <th>能力</th>
              <th>当前状态</th>
              <th>使用边界</th>
            </tr>
          </thead>
          <tbody>
            {[
              [
                "影片查找与身份确认",
                "按资料源查找",
                "按来源原文片名检索并确认年份，最多 50 条。商店搜索无电影结果时查当前分类榜单；未覆盖的影片可能查不到。推荐候选仍来自分类榜单。",
              ],
              [
                "类型、心情与片长匹配",
                "规则匹配已接入",
                "文字通过规则解析常见类型、心情、时长、年代与排除；冲突或无法执行的条件需确认后才查询片库。类型、年代和片长为硬条件，文字心情仅辅助召回与排序。不具备通用模型理解能力。",
              ],
              [
                "影片对比",
                "基础资料可用",
                "仅对比已确认的 2–3 部影片，不生成对比结论。",
              ],
              [
                "本次片单与隐藏反馈",
                "仅当前页面",
                "片单与排除影片保存在页面内存；排除会传入后续选片条件，支持撤销。刷新清空，不保存长期偏好。",
              ],
              [
                "来源海报",
                "海报已接入",
                "使用来源海报并链接对应商店。评分、影评与剧情总结尚未接入。",
              ],
              [
                "地区观看渠道",
                "待真实数据",
                "未知不等于不可观看；不会提供虚假的播放按钮。",
              ],
              [
                "账号、云端片单、长期记忆",
                "尚未实现",
                "无登录、偏好读写、历史、导出或服务端删除接口。",
              ],
              [
                "资料来源与使用范围",
                "Apple 美国区公开数据",
                "海报用于介绍并链接原电影商店；未提供播放、下载或完整片库覆盖保证。",
              ],
            ].map((row) => (
              <tr key={row[0]}>
                <th scope="row">{row[0]}</th>
                <td>{row[1]}</td>
                <td>{row[2]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        海报由 Apple
        图片服务加载；商店链接会打开第三方网站。未使用外部字体、追踪脚本或分析服务。iTunes
        Store is a trademark of Apple Inc., registered in the U.S. and other
        countries.
      </p>
    </>
  );
}
