import type { ReactNode } from "react";
import { ArrowDown, ArrowUpRight, SlidersHorizontal } from "lucide-react";
import type { Movie } from "./domain";

export function DiscoveryHero({
  movies,
  loading,
  synthetic,
  renderPoster,
  onExplore,
  onCustomize,
}: {
  movies: Movie[];
  loading: boolean;
  synthetic: boolean;
  renderPoster: (movie: Movie) => ReactNode;
  onExplore: () => void;
  onCustomize: () => void;
}) {
  return (
    <section className="discovery-hero" aria-labelledby="discovery-heading">
      <div className="discovery-editorial">
        <p className="editorial-kicker">TONIGHT / 一场电影的时间</p>
        <h1 id="discovery-heading">
          好故事，
          <br />
          不必费力找。
        </h1>
        <p className="editorial-description">
          先看看这些电影。遇见心动的，留给今晚。
          <br />
          还没感觉？换一种心情，再发现下一部。
        </p>
        <div className="editorial-actions">
          <button className="button primary" onClick={onExplore}>
            看看今晚的电影 <ArrowDown size={18} aria-hidden="true" />
          </button>
          <button className="button secondary" onClick={onCustomize}>
            <SlidersHorizontal size={17} aria-hidden="true" />
            我有一点想法
          </button>
        </div>
        <p className="editorial-footnote">
          无需填写问卷 · 无需注册 · 偏好只留在本次会话
        </p>
      </div>
      <div className="screening-display" aria-label="今晚的电影预览">
        <div className="screening-label">
          <span>NOW DISCOVERING</span>
          <span>{loading ? "正在查找" : "本次发现"}</span>
        </div>
        <div className="poster-stage" aria-busy={loading}>
          {movies.slice(0, 3).map((movie, index) => (
            <div className="stage-film" key={movie.movie_id}>
              {renderPoster(movie)}
              <div className="stage-caption">
                <span>{String(index + 1).padStart(2, "0")}</span>
                <p>{movie.title}</p>
                <ArrowUpRight size={16} aria-hidden="true" />
              </div>
            </div>
          ))}
          {!movies.length && (
            <div className="stage-empty" role="status">
              <span className="stage-orbit" aria-hidden="true">
                ◎
              </span>
              <p>{loading ? "好故事，正在路上。" : "等一部电影的时间。"}</p>
              <small>
                {loading ? "正在读取真实片库" : "请在下方重试，或调整选片条件"}
              </small>
            </div>
          )}
        </div>
        <p className="screening-credit">
          {synthetic
            ? "离线合成契约样例 · 不代表真实推荐"
            : "电影资料与海报来自 Apple 美国区 · 来源榜单不代表口碑评分"}
        </p>
      </div>
    </section>
  );
}
