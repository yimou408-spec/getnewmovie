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
import { useMutation, useQuery } from "@tanstack/react-query";
import * as Tabs from "@radix-ui/react-tabs";
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
  CircleAlert,
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
  modeLabel,
  runtimeText,
  safeSourceUrl,
  validateResponse,
  type Candidate,
  type DataMode,
  type Mode,
  type Movie,
  type Recommendation,
  type SearchResponse,
} from "./domain";

const initialDrafts: Record<Mode, string> = {
  discover: "",
  watchlist: "从本次片单中，选一部适合今晚的电影",
  known_movie: "想了解这部电影是否适合今晚观看",
};
const ideas = [
  "想轻松一下，100 分钟以内",
  "两个人看，想聊点有意思的",
  "去一趟太空，今晚看科幻",
];
function Button({
  children,
  className = "",
  type = "button",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
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
function ErrorNotice({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <div role="alert" className="notice error">
      <CircleAlert aria-hidden="true" />
      <div>
        <strong>{error.message}</strong>
        {error instanceof ApiError && error.trace && (
          <small>请求编号：{error.trace}</small>
        )}
        {retry && (
          <Button className="quiet" onClick={retry}>
            重新尝试
          </Button>
        )}
      </div>
    </div>
  );
}
function Poster({ movie, small = false }: { movie: Movie; small?: boolean }) {
  return (
    <div
      className={`poster ${small ? "small" : ""}`}
      aria-label={`${movie.title}：暂无海报`}
    >
      <span className="poster-frame" aria-hidden="true">
        <Film size={small ? 24 : 40} />
      </span>
      <span className="poster-title">{movie.title}</span>
      <small>海报尚未提供</small>
    </div>
  );
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
  const [runtime, setRuntime] = useState("");
  const [region, setRegion] = useState("CN");
  const [scenario, setScenario] = useState("success");
  const [selected, setSelected] = useState<Movie>();
  const [saved, setSaved] = useState<Movie[]>([]);
  const [comparison, setComparison] = useState<Movie[]>([]);
  const [result, setResult] = useState<Recommendation>();
  const [snapshotQuery, setSnapshotQuery] = useState("");
  const [formError, setFormError] = useState<Error>();
  const [message, setMessage] = useState("");
  const [clarificationCount, setClarificationCount] = useState(0);
  const [hidden, setHidden] = useState<string[]>([]);
  const [undo, setUndo] = useState<{
    saved?: Movie[];
    comparison?: Movie[];
    selected?: Movie;
  }>();
  const resultsRef = useRef<HTMLElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const [pathKey, setPathKey] = useState(location.pathname);
  useEffect(() => {
    if (pathKey !== location.pathname) {
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
    mutationFn: async (body: ReturnType<typeof buildRequest>) =>
      validateResponse(
        await api("/recommendations", {
          method: "POST",
          headers: { "X-Mock-Scenario": scenario },
          body: JSON.stringify(body),
        }),
      ),
    onSuccess: (data, body) => {
      setResult(data);
      setSnapshotQuery(body.query);
      setHidden([]);
      requestAnimationFrame(() => {
        resultsRef.current?.focus();
        resultsRef.current?.scrollIntoView({
          behavior: "instant",
          block: "start",
        });
      });
    },
  });
  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (recommend.isPending) return;
    setFormError(undefined);
    try {
      recommend.mutate(
        buildRequest(
          mode,
          drafts[mode],
          region,
          runtime,
          saved.map((m) => m.movie_id),
          selected,
          clarificationCount,
        ),
      );
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
      setComparison((current) => [...current, movie]);
    else setMessage("最多对比 3 部影片，请先移除一部。");
  }
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
  function card(movie: Movie, candidate?: Candidate) {
    return (
      <article
        className={`movie-card ${candidate ? "recommendation-card" : ""}`}
        key={movie.movie_id}
      >
        <Link
          to={`/film/${encodeURIComponent(movie.movie_id)}`}
          className="poster-link"
          aria-label={`查看 ${movie.title} ${movie.year} 资料`}
        >
          <Poster movie={movie} small={!candidate} />
        </Link>
        <div className="movie-body">
          <div className="movie-heading">
            <div>
              <Badge
                mode={
                  movie.movie_id.startsWith("syn:")
                    ? "synthetic"
                    : candidate
                      ? result!.data_mode
                      : "unknown"
                }
              />
              <h3>
                <Link to={`/film/${encodeURIComponent(movie.movie_id)}`}>
                  {movie.title}
                  <ChevronRight size={19} />
                </Link>
              </h3>
            </div>
          </div>
          <MovieFacts movie={movie} />
          {candidate ? (
            <>
              <div className="reason">
                <span>
                  <Sparkles size={16} aria-hidden="true" />
                  为什么放进候选
                </span>
                <p>{candidate.reason.text}</p>
                <small>
                  {
                    {
                      metadata_fact: "影片资料",
                      source_opinion: "来源观点",
                      matching_inference: "匹配推断",
                    }[candidate.reason.kind]
                  }
                </small>
              </div>
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
              <Ratings movie={movie} />
              <Availability candidate={candidate} />
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
              <details className="sources">
                <summary>核对理由与来源</summary>
                {result!.evidence
                  .filter((e) =>
                    candidate.reason.evidence_ids.includes(e.evidence_id),
                  )
                  .map((e) => (
                    <div className="source" key={e.evidence_id}>
                      <strong>{e.source}</strong>
                      <p>
                        {e.spoiler_level === "safe"
                          ? e.claim
                          : "来源可能包含剧透，暂不展示内容。"}
                      </p>
                      <small>采集时间：{e.retrieved_at}</small>
                      <SourceLink url={e.url}>查看来源</SourceLink>
                    </div>
                  ))}
              </details>
              <Button
                className="text-button"
                onClick={() => {
                  setHidden((current) => [...current, movie.movie_id]);
                  setMessage(
                    "已在本次结果中隐藏；反馈尚未上传，也不会用于训练或记忆。",
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
            联调版
            <Info size={14} />
          </Link>
        </div>
      </header>
      <div className="demo-strip">
        <div>
          <Info size={16} aria-hidden="true" />
          <span>
            <strong>S0 合成数据联调</strong> ·
            影片与评分均为虚构样例，输入暂不参与真实推荐。
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
                <section className="intro">
                  <img
                    className="intro-image"
                    src="/images/coastal-train.webp"
                    alt="暖色车厢里，海岸风景从宽大的车窗外缓缓展开"
                    width={2200}
                    height={1237}
                    fetchPriority="high"
                  />
                  <div className="intro-copy">
                    <p className="intro-note">
                      私人选片室 · 给自己留一点电影时间
                    </p>
                    <h1>
                      今晚，
                      <br />
                      想看点什么？
                    </h1>
                    <p className="intro-description">
                      暂停日常，走进另一个故事。
                      <br />
                      从此刻的心情出发，找到今晚想看的那一部。
                    </p>
                    <button
                      className="hero-action"
                      onClick={() => textareaRef.current?.focus()}
                    >
                      开始今晚的选片 <ArrowRight size={20} aria-hidden="true" />
                    </button>
                  </div>
                  <div className="hero-caption">
                    <span>让生活慢下来，让故事开始。</span>
                    <a
                      href="https://unsplash.com/photos/JCqY2Ji5gj4"
                      target="_blank"
                      rel="noreferrer"
                    >
                      氛围摄影 · Shawn Rain / Unsplash{" "}
                      <ExternalLink size={12} aria-hidden="true" />
                    </a>
                  </div>
                </section>
                <div className="workspace">
                  <section
                    className="composer"
                    aria-labelledby="composer-title"
                  >
                    <div className="composer-heading">
                      <h2 id="composer-title">把今晚，交给一个好故事</h2>
                      <p>不必先想好片名，说说你想怎么度过这段时间。</p>
                    </div>
                    <Tabs.Root
                      value={mode}
                      onValueChange={(v) => {
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
                        <form onSubmit={submit}>
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
                          <div className="field">
                            <label htmlFor="mood">
                              {mode === "known_movie"
                                ? "关于这部电影，你在意什么？"
                                : "说说这次的观影想法"}
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
                              placeholder="比如：下班后想放松一下，轻松、有点幽默，100 分钟以内。"
                              maxLength={2000}
                              rows={3}
                              required
                              aria-describedby="mood-help"
                            />
                            <div className="input-help" id="mood-help">
                              <span>
                                心情、题材、一起看的人，都可以告诉我。
                              </span>
                              <span>{drafts[mode].length}/2000</span>
                            </div>
                          </div>
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
                          <div className="composer-bottom">
                            <p>
                              <ShieldCheck size={16} aria-hidden="true" />
                              本次对话不写入长期记忆
                            </p>
                            <Button
                              className="primary"
                              type="submit"
                              disabled={recommend.isPending}
                            >
                              {recommend.isPending
                                ? "正在获取样例…"
                                : "看看候选电影"}
                              {!recommend.isPending && <ArrowRight size={17} />}
                            </Button>
                          </div>
                        </form>
                      </Tabs.Content>
                    </Tabs.Root>
                    <details className="dev-tools">
                      <summary>联调场景设置</summary>
                      <div className="field">
                        <label htmlFor="scenario">模拟服务状态</label>
                        <select
                          id="scenario"
                          name="scenario"
                          autoComplete="off"
                          value={scenario}
                          onChange={(e) => setScenario(e.target.value)}
                        >
                          <option value="success">成功样例</option>
                          <option value="empty">没有匹配</option>
                          <option value="clarification">需要澄清</option>
                          <option value="degraded">降级响应</option>
                          <option value="timeout">上游超时</option>
                          <option value="unconfigured">服务未配置</option>
                        </select>
                        <small>
                          仅用于检查界面状态；Mock 返回固定样例，不解析输入。
                        </small>
                      </div>
                    </details>
                  </section>
                  <aside className="inspiration">
                    <div className="aside-heading">
                      <Sparkles size={19} aria-hidden="true" />
                      <h2>从一个念头开始</h2>
                    </div>
                    <p>选一种心情，试着打开今晚。</p>
                    <div className="idea-list">
                      {ideas.map((idea, i) => (
                        <button
                          key={idea}
                          onClick={() => {
                            setMode("discover");
                            setDrafts((current) => ({
                              ...current,
                              discover: idea,
                            }));
                            if (i === 0) setRuntime("100");
                            requestAnimationFrame(() =>
                              textareaRef.current?.focus(),
                            );
                          }}
                        >
                          <span className="idea-icon" aria-hidden="true">
                            {i === 0 ? (
                              <Moon size={23} />
                            ) : i === 1 ? (
                              <Heart size={23} />
                            ) : (
                              <Telescope size={23} />
                            )}
                          </span>
                          <span>
                            {["松弛一点", "一起看", "换个世界"][i]}
                            <small>{idea}</small>
                          </span>
                          <ChevronRight size={17} />
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
                        ? recommend.isError || recommend.isPending
                          ? "上次候选结果"
                          : "你的候选电影"
                        : "把今晚留给合适的一部"}
                    </h2>
                    <span>
                      {result
                        ? `${result.candidates.length} 部候选 / 最多 3 部`
                        : "先说心情，再做选择"}
                    </span>
                  </div>
                  {(formError || recommend.error) && (
                    <ErrorNotice
                      error={formError ?? recommend.error!}
                      retry={
                        recommend.error instanceof ApiError &&
                        recommend.error.retryable
                          ? () => submit()
                          : undefined
                      }
                    />
                  )}
                  {recommend.isPending && (
                    <div className="loading" role="status">
                      <div className="skeleton" />
                      <p>正在向联调服务获取结果…</p>
                      <small>不会自动重复请求。</small>
                    </div>
                  )}
                  {result && (
                    <>
                      <div className="result-context">
                        <Badge mode={result.data_mode} />
                        <span>本次想法：{snapshotQuery}</span>
                        <small>
                          {result.memory_used
                            ? "服务报告使用了记忆"
                            : "未使用长期记忆"}
                        </small>
                      </div>
                      {result.warnings.map((warning, i) => (
                        <div className="notice" key={i}>
                          <Info size={18} />
                          <span>{warning}</span>
                        </div>
                      ))}
                      {result.status === "needs_clarification" && (
                        <div className="clarification">
                          <h3>再补充一点想法</h3>
                          {result.questions.map((q) => (
                            <div key={q.question_id}>
                              <p>{q.text}</p>
                              <div className="choice-row">
                                {(q.options ?? []).map((option) => (
                                  <Button
                                    key={option}
                                    className="secondary"
                                    disabled={clarificationCount >= 2}
                                    onClick={() => {
                                      setDrafts((current) => ({
                                        ...current,
                                        [mode]:
                                          `${current[mode]}\n补充：${q.text}${option}`.slice(
                                            0,
                                            2000,
                                          ),
                                      }));
                                      setClarificationCount((n) => n + 1);
                                      setMessage(
                                        "已补充到输入。当前 Mock 不会据此生成新推荐。",
                                      );
                                      textareaRef.current?.focus();
                                    }}
                                  >
                                    {option}
                                  </Button>
                                ))}
                              </div>
                            </div>
                          ))}
                          <small>
                            {clarificationCount >= 2
                              ? "已达到接口最多 2 次补充的限制。"
                              : "选择会补充到输入；当前服务只演示澄清，不执行推理。"}
                          </small>
                        </div>
                      )}
                      {result.candidates
                        .filter((c) => !hidden.includes(c.movie.movie_id))
                        .map((c) => card(c.movie, c))}
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
                          <p>试着放宽片长或换个描述，也可以稍后再试。</p>
                          <Button
                            className="secondary"
                            onClick={() => {
                              setRuntime("");
                              textareaRef.current?.focus();
                            }}
                          >
                            调整观影想法
                          </Button>
                        </Empty>
                      )}
                      {result.candidates.length > 0 &&
                        result.candidates.every((c) =>
                          hidden.includes(c.movie.movie_id),
                        ) && (
                          <Empty title="本次候选已隐藏">
                            <p>反馈仅在当前结果生效，尚未同步到服务。</p>
                            <Button
                              className="secondary"
                              onClick={() => setHidden([])}
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
                        不用翻完一整面片墙。
                        <br />
                        <strong>
                          说说你想要的，我们把候选缩小到三部以内。
                        </strong>
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
                      查找片名并确认年份后加入。试试合成片名“春日来信”或“远星航线”。
                    </p>
                  </Empty>
                )}
              </>
            }
          />
          <Route
            path="/compare"
            element={
              <Compare
                movies={comparison}
                candidates={knownCandidates}
                onRemove={compare}
              />
            }
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
function Ratings({ movie }: { movie: Movie }) {
  return (
    <div className="ratings">
      {(movie.ratings ?? []).length ? (
        (movie.ratings ?? []).map((r, i) => (
          <div key={i}>
            <strong>
              {r.value}
              <small> / {r.scale}</small>
            </strong>
            <span>{r.source}</span>
            <small>
              {r.vote_count == null
                ? "票数未提供"
                : `${r.vote_count.toLocaleString("zh-CN")} 票`}
            </small>
          </div>
        ))
      ) : (
        <p>
          评分：未获取<span>缺少评分不代表评分低</span>
        </p>
      )}
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
  const search = useMutation({
    mutationFn: async () => {
      const data = await api<SearchResponse>(
        `/movies?query=${encodeURIComponent(query.trim())}${year ? `&year=${year}` : ""}`,
      );
      if (
        !Array.isArray(data.movies) ||
        !["synthetic", "live", "cached"].includes(data.data_mode)
      )
        throw new Error("影片查找返回的数据不完整。");
      return data;
    },
  });
  const run = () => {
    if (query.trim() && !search.isPending) {
      setSearched(true);
      search.mutate();
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
              setSearched(false);
            }}
            placeholder="试试：春日来信"
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
            onChange={(e) => {
              setYear(e.target.value);
              setSearched(false);
            }}
            placeholder="如 2024"
          />
        </div>
        <Button
          type="button"
          className="secondary"
          disabled={
            !query.trim() ||
            search.isPending ||
            (!!year &&
              (Number(year) < 1888 ||
                Number(year) > 2200 ||
                !Number.isInteger(Number(year))))
          }
          onClick={run}
        >
          <Search size={16} />
          {search.isPending ? "查找中…" : "查找影片"}
        </Button>
      </div>
      <p className="muted small-text">
        同名影片请核对年份；当前仅检索 4 部合成样例。
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
              : "没有找到影片。试试“春日来信”或“远星航线”。"}
          </p>
          {search.data.movies.map((m) => (
            <div className="lookup-item" key={m.movie_id}>
              <div>
                <strong>
                  {m.title}（{m.year ?? "年份未知"}）
                </strong>
                <MovieFacts movie={m} />
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
    queryFn: () => api<Movie>(`/movies/${encodeURIComponent(movieId!)}`),
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
          当前接口未提供剧情简介、演职员与海报。页面不补造影片内容；观看渠道需要独立核实。
        </span>
      </div>
    </>
  );
}
function Compare({
  movies,
  candidates,
  onRemove,
}: {
  movies: Movie[];
  candidates: Candidate[];
  onRemove: (m: Movie) => void;
}) {
  const ids = movies.map((m) => m.movie_id);
  const query = useQuery({
    queryKey: ["compare", ...ids],
    queryFn: () =>
      api<SearchResponse>("/comparisons", {
        method: "POST",
        body: JSON.stringify({ movie_ids: ids }),
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
              对比接口仅提供基础资料。推荐理由沿用本次已有结果；未获取的评分和渠道保持未知。
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
                      "观看渠道",
                    ].map((row, i) => (
                      <tr key={row}>
                        <th scope="row">{row}</th>
                        {query.data!.movies.map((m) => {
                          const c = candidates.find(
                            (c) => c.movie.movie_id === m.movie_id,
                          );
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
                                <Ratings movie={c?.movie ?? m} />
                              ) : i === 5 ? (
                                (c?.reason.text ?? "本次尚未获取")
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
          这是“今晚看什么”的产品前端。目前连接仓库内的 S0
          联调服务，所有影片、评分、来源均为合成样例，不能作为真实观影依据。
        </p>
      </div>
      <div
        className="table-scroll"
        role="region"
        aria-label="能力接入状态"
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
                "联调可用",
                "检索 4 部合成影片；同名按年份确认。",
              ],
              [
                "推荐与澄清",
                "固定样例",
                "输入经过接口校验，但不参与真实推荐或推理。",
              ],
              [
                "影片对比",
                "基础资料可用",
                "仅对比已确认的 2–3 部影片，不生成对比结论。",
              ],
              [
                "本次片单与隐藏反馈",
                "仅当前页面",
                "保存在内存；刷新清空，不上传反馈。",
              ],
              [
                "海报、剧情与真实评分",
                "待后端接入",
                "契约尚未提供海报与简介；合成评分不作真实数据。",
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
                "TMDB 与商业数据许可",
                "待正式接入",
                "未调用真实数据服务。上线前需核实授权、署名及商用许可。",
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
        合成来源中的 example.invalid
        是占位地址，页面不会将其作为可访问链接。当前无第三方图片、外部字体、追踪脚本或分析服务。
      </p>
    </>
  );
}
