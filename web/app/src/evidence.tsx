import { useEffect, useId, useRef, useState } from "react";
import { ExternalLink, FileCheck2, X } from "lucide-react";
import {
  safeSourceUrl,
  type Candidate,
  type DataMode,
  type Movie,
} from "./domain";
import {
  evidenceForMovie,
  reasonLabels,
  sourceSites,
  type Evidence,
} from "./evidence-model";
import "./evidence.css";

const evidenceLabels: Record<Evidence["kind"], string> = {
  metadata: "影片资料",
  rating: "评分记录",
  review: "来源观点",
  synthetic: "离线合成证据",
};
const dateFormat = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  timeZoneName: "short",
});

export function TMDBAttribution() {
  return (
    <section className="tmdb-attribution" aria-label="TMDB 数据署名">
      <a
        href="https://www.themoviedb.org/"
        target="_blank"
        rel="noopener noreferrer"
      >
        <img src="/tmdb-logo.svg" alt="TMDB" width="100" height="14" />
      </a>
      <p>
        This product uses the TMDB API but is not endorsed or certified by TMDB.
      </p>
      <p>TMDB 补充影片资料；影片资料不等同于独立影评或观看渠道。</p>
    </section>
  );
}

function RetrievedAt({ value }: { value: string }) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? (
    <span>采集时间未知</span>
  ) : (
    <span>
      采集时间：<time dateTime={value}>{dateFormat.format(date)}</time>
    </span>
  );
}

function EvidenceLink({
  url,
  label = "查看原始来源",
}: {
  url: string;
  label?: string;
}) {
  const safe = safeSourceUrl(url);
  return safe ? (
    <a href={safe} target="_blank" rel="noopener noreferrer">
      {label}
      <ExternalLink size={13} aria-hidden="true" />
    </a>
  ) : (
    <span className="muted">来源链接不可用</span>
  );
}

export function Ratings({
  movie,
  evidence = [],
}: {
  movie: Movie;
  evidence?: Evidence[];
}) {
  const entries = evidenceForMovie(movie, evidence);
  return (
    <div className="ratings">
      {movie.ratings?.length ? (
        movie.ratings.map((rating, i) => {
          const origin = entries.find(
            (e) =>
              e.evidence_id === rating.evidence_id &&
              e.source === rating.source &&
              e.spoiler_level === "safe",
          );
          return (
            <div key={`${rating.source}-${i}`} data-testid="source-rating">
              <strong>
                {rating.value}
                <small> / {rating.scale}</small>
              </strong>
              <span>{rating.source}</span>
              <small>
                {rating.vote_count == null
                  ? "票数未提供"
                  : `${rating.vote_count.toLocaleString("zh-CN")} 票`}
              </small>
              <div className="rating-origin">
                {origin ? (
                  <>
                    <RetrievedAt value={origin.retrieved_at} />
                    <EvidenceLink url={origin.url} label="核对评分出处" />
                  </>
                ) : (
                  <span>评分出处未提供，待核对</span>
                )}
              </div>
            </div>
          );
        })
      ) : (
        <p>
          评分：未获取<span>缺少评分不代表评分低</span>
        </p>
      )}
    </div>
  );
}

function EvidenceEntry({ entry, cited }: { entry: Evidence; cited: boolean }) {
  const [reveal, setReveal] = useState(false);
  const safe = entry.spoiler_level === "safe";
  return (
    <article className="evidence-entry">
      <div className="evidence-entry-heading">
        <strong>{entry.source}</strong>
        <span>
          {evidenceLabels[entry.kind]}
          {cited ? " · 理由引用" : ""}
        </span>
      </div>
      {entry.kind === "review" && (
        <p className="muted">
          作者：{entry.author || "未提供"}
          {entry.granularity === "excerpt" ? " · 原文摘录" : ""}
        </p>
      )}
      {safe || reveal ? (
        <p className={entry.kind === "review" ? "source-opinion" : ""}>
          {entry.claim}
        </p>
      ) : (
        <>
          <p>来源可能包含剧透，暂不展示内容。</p>
          <button
            type="button"
            className="button text-button"
            onClick={() => setReveal(true)}
          >
            仍要展开这条内容
          </button>
        </>
      )}
      {!safe && reveal && (
        <button
          type="button"
          className="button text-button"
          onClick={() => setReveal(false)}
        >
          收起剧透内容
        </button>
      )}
      <div className="evidence-entry-footer">
        <RetrievedAt value={entry.retrieved_at} />
        <EvidenceLink url={entry.url} />
      </div>
    </article>
  );
}

export function SourceOpinions({
  movie,
  evidence,
}: {
  movie: Movie;
  evidence: Evidence[];
}) {
  const opinions = evidenceForMovie(movie, evidence).filter(
    (e) => e.kind === "review",
  );
  return opinions.length ? (
    <ul className="opinion-list">
      {opinions.map((e) => (
        <li key={e.evidence_id}>
          <strong>{e.source}</strong>
          <p>
            {e.spoiler_level === "safe"
              ? e.claim
              : "观点内容可能包含剧透，请在来源面板中按需展开。"}
          </p>
        </li>
      ))}
    </ul>
  ) : (
    <p className="muted">尚未获取来源观点。</p>
  );
}

export function EvidenceOverview({
  movie,
  evidence,
  candidate,
  dataMode,
}: {
  movie: Movie;
  evidence: Evidence[];
  candidate?: Candidate;
  dataMode?: DataMode;
}) {
  const entries = evidenceForMovie(movie, evidence);
  const sites = sourceSites(entries);
  const doubanRating = movie.ratings?.some((r) => r.source.includes("豆瓣"));
  return (
    <div className="evidence-overview">
      {dataMode === "synthetic" && (
        <p className="notice warning">离线合成样例，仅用于接口与交互验收。</p>
      )}
      {dataMode === "cached" && (
        <p className="notice">本次使用缓存证据，请核对每条采集时间。</p>
      )}
      {entries.some((entry) =>
        ["TMDB", "TMDB Reviews"].includes(entry.source),
      ) && <TMDBAttribution />}
      <div className="evidence-coverage">
        <strong>
          {sites.length === 0
            ? "缺少可核对来源"
            : sites.length === 1
              ? "仅 1 个来源站点，尚无交叉核对。"
              : `${sites.length} 个来源站点；来源独立性尚未核验。`}
        </strong>
        <p>同一站点的多条资料不会计作多个来源，评分按原平台和量表分别展示。</p>
        {!doubanRating && <p>豆瓣评分未获取；不代表评分低或影片未收录。</p>}
      </div>
      {candidate && (
        <section className="evidence-reason">
          <h3>
            本次推荐理由 <span>{reasonLabels[candidate.reason.kind]}</span>
          </h3>
          <p>{candidate.reason.text}</p>
          <p className="small-text muted">
            匹配推断不等同于来源观点或观众口碑。
          </p>
        </section>
      )}
      <section>
        <h3>各平台评分</h3>
        <Ratings movie={movie} evidence={entries} />
      </section>
      <section>
        <h3>来源观点</h3>
        <SourceOpinions movie={movie} evidence={entries} />
        <p className="small-text muted">
          观点按来源并列展示。当前未生成跨来源观点差异结论。
        </p>
      </section>
      <section>
        <h3>
          证据记录 <span>{entries.length} 条</span>
        </h3>
        {entries.length ? (
          entries.map((e) => (
            <EvidenceEntry
              key={e.evidence_id}
              entry={e}
              cited={
                candidate?.reason.evidence_ids.includes(e.evidence_id) ?? false
              }
            />
          ))
        ) : (
          <p className="muted">
            本次没有取得这部影片的证据，评分与口碑仍需核对。
          </p>
        )}
      </section>
    </div>
  );
}

function EvidenceDrawer({
  movie,
  evidence,
  candidate,
  dataMode,
  close,
}: {
  movie: Movie;
  evidence: Evidence[];
  candidate?: Candidate;
  dataMode?: DataMode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const title = useId();
  useEffect(() => {
    const dialog = ref.current!;
    const overflow = document.body.style.overflow;
    if (!dialog.open) dialog.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      // Removing the element closes the modal. Calling close() here would also
      // enqueue onClose during StrictMode's setup/cleanup replay.
      document.body.style.overflow = overflow;
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="evidence-drawer"
      aria-labelledby={title}
      onClose={close}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(
          event.currentTarget.querySelectorAll<HTMLElement>(
            'a[href], button:not(:disabled), [tabindex="0"]',
          ),
        ).filter((element) => element.getClientRects().length > 0);
        const target = event.shiftKey ? controls.at(-1) : controls[0];
        const boundary = event.shiftKey ? controls[0] : controls.at(-1);
        if (target && document.activeElement === boundary) {
          event.preventDefault();
          target.focus();
        }
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) ref.current?.close();
      }}
    >
      <div className="evidence-drawer-inner">
        <header>
          <div>
            <p className="eyebrow">理由与来源</p>
            <h2 id={title}>
              {movie.title} <small>{movie.year ?? "年份未知"}</small>
            </h2>
          </div>
          <button
            type="button"
            className="button secondary"
            onClick={() => ref.current?.close()}
            aria-label="关闭来源面板"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </header>
        <EvidenceOverview
          movie={movie}
          evidence={evidence}
          candidate={candidate}
          dataMode={dataMode}
        />
      </div>
    </dialog>
  );
}

export function EvidencePanel({
  movie,
  evidence,
  candidate,
  dataMode,
  snapshot = false,
}: {
  movie: Movie;
  evidence: Evidence[];
  candidate?: Candidate;
  dataMode?: DataMode;
  snapshot?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const entries = evidenceForMovie(movie, evidence);
  const sites = sourceSites(entries).length;
  const opinions = entries.filter((e) => e.kind === "review").length;
  return (
    <div className="evidence-panel">
      <div className="evidence-panel-heading">
        <FileCheck2 size={17} aria-hidden="true" />
        <strong>证据覆盖</strong>
        <span>
          {entries.length} 条 · {sites} 个站点
        </span>
      </div>
      <p>
        {sites < 2 ? "缺少跨来源核对" : "来源独立性待核验"} ·{" "}
        {opinions ? `${opinions} 条来源观点` : "尚无影评证据"}
      </p>
      {snapshot && <p>沿用加入对比时的推荐快照，采集时间见记录。</p>}
      <button
        type="button"
        className="button text-button"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        核对理由与来源
      </button>
      {open && (
        <EvidenceDrawer
          movie={movie}
          evidence={entries}
          candidate={candidate}
          dataMode={dataMode}
          close={() => setOpen(false)}
        />
      )}
    </div>
  );
}
