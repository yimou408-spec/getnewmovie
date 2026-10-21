"""Real catalog API. Start: python -m uvicorn scripts.movie_server:app --port 8000."""
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from scripts.movie_catalog import AppleCatalog, CatalogError, MOODS
from scripts.movie_ranking import MOOD_CLUES, rank_movies
from scripts.s0_contracts import (Availability, Candidate, ComparisonRequest, ErrorResponse, Evidence, HealthResponse, Movie,
                                  MovieSearchResponse, Reason, RecommendationRequest, RecommendationResponse, ServiceCapabilities)


def create_app(catalog=None):
    catalog = catalog or AppleCatalog()
    app = FastAPI(title="Tonight movie catalog", version="0.1.0", description="Apple US real charts. Rule-based matching, no synthetic fallback.")

    @app.exception_handler(CatalogError)
    async def source_error(request: Request, exc: CatalogError):
        return JSONResponse(status_code=exc.status, content=ErrorResponse(trace_id=uuid4().hex, data_mode="live",
            code=exc.code, message=exc.message, retryable=exc.status != 404).model_dump(mode="json"))

    @app.get("/health", response_model=HealthResponse)
    def health():
        return HealthResponse(service="real-catalog", provider="Apple iTunes US", synthetic_fallback=False,
                              cache_ttl_seconds=1800, capabilities=ServiceCapabilities(metadata=True))

    def find(mid):
        if not mid.startswith("itunes:"):
            raise CatalogError("NOT_FOUND", "影片不在当前真实片库中，请重新查找。", 404)
        found = catalog.lookup([mid.removeprefix("itunes:")])
        if not found:
            raise CatalogError("NOT_FOUND", "资料源未返回这部影片。", 404)
        return found[0]

    @app.post("/recommendations", response_model=RecommendationResponse, responses={503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
    def recommendations(body: RecommendationRequest):
        with catalog.lock:
            before = catalog.fetch_count
            c = body.constraints
            mood_genres = set().union(*(MOODS[m] for m in c.moods)) if c.moods else set()
            pool_genres = c.genres or sorted(mood_genres) or (["家庭"] if c.company == "和家人" else [])
            if body.mode == "known_movie":
                films = [find(body.movie_id)]
            elif body.mode == "watchlist":
                films = [find(mid) for mid in dict.fromkeys(body.watchlist_movie_ids)]
            else:
                films = catalog.pool(pool_genres)
            eligible = []
            for movie, at in films:
                genres = set(movie.genres)
                if movie.movie_id in c.exclude_movie_ids or genres.intersection(c.exclude_genres):
                    continue
                if c.genres and not genres.intersection(c.genres):
                    continue
                if mood_genres and not genres.intersection(mood_genres):
                    continue
                if c.company == "和家人" and not genres.intersection({"家庭", "动画"}):
                    continue
                if c.max_runtime_minutes is not None and (movie.runtime_minutes is None or movie.runtime_minutes > c.max_runtime_minutes):
                    continue
                if c.era != "any":
                    if movie.year is None:
                        continue
                    bounds = {"recent": (2020, datetime.now(timezone.utc).year), "2000s": (2000, 2019), "classic": (1888, 1999)}
                    low, high = bounds[c.era]
                    if not low <= movie.year <= high:
                        continue
                eligible.append((movie, at))
            eligible = rank_movies(eligible, c)
            candidates, evidence = [], []
            for movie, at in eligible[:3]:
                eid = f"apple-{movie.movie_id.split(':')[1]}"
                facts = f"Apple 美国区分类：{'、'.join(movie.genres)}；正片时长：{movie.runtime_minutes or '未知'} 分钟。"
                facts += f"导演：{movie.director or '未知'}；美国内容分级：{movie.content_advisory or '未知'}。"
                evidence.append(Evidence(evidence_id=eid, movie_id=movie.movie_id, source="Apple iTunes US", url=movie.source_url or "https://itunes.apple.com/us/", retrieved_at=at, kind="metadata", claim=facts, spoiler_level="safe"))
                match = [f"类型符合：{'、'.join(c.genres)}。"] if c.genres else []
                if c.moods:
                    clues = set().union(*(MOOD_CLUES[m] for m in c.moods)) & set(movie.tags)
                    match.append(f"简介词法线索：{'、'.join(sorted(clues))}；用于「{'、'.join(c.moods)}」匹配推断。" if clues else f"类型接近「{'、'.join(c.moods)}」，简介缺少明确的心情线索，感受待确认。")
                if c.max_runtime_minutes:
                    match.append(f"{movie.runtime_minutes} 分钟，不超过你的 {c.max_runtime_minutes} 分钟上限。")
                if not match:
                    match.append(f"{movie.year or '年份未知'} 年 · {'、'.join(movie.genres)}；来自当前榜单候选。")
                if c.era != "any":
                    match.append(f"{movie.year} 年，符合所选年代。")
                match.append("保留来源顺序。" if c.sort_by == "popular" else "结合匹配线索与类型、导演差异安排本次短名单。")
                caveats = ["心情为类型及简介关键词推断，未经过人工内容审查。"] if c.moods else []
                risks = set(movie.tags) & {"恐怖线索", "沉重线索"}
                if risks:
                    caveats.append(f"简介词法提示：{'、'.join(sorted(risks))}，不等于完整内容预警。")
                if c.company == "和家人":
                    caveats.append(f"美国分级 {movie.content_advisory or '未知'}，不是中国适龄结论；请自行核对。")
                candidates.append(Candidate(movie=movie, reason=Reason(text="".join(match), evidence_ids=[eid], kind="matching_inference"),
                    caveats=caveats,
                    availability=[Availability(region=body.region, status="unknown")]))
            warnings = ["范围：Apple 美国区当前分类榜单；片名沿用来源原文。评分及所选地区播放渠道未接入。",
                        "类型与心情类别先交叉筛选；片长、年代、排除影片是硬条件，未知字段不进入对应限定结果。",
                        "排序：来源顺序，不代表口碑或适合程度。" if c.sort_by == "popular" else "排序：均衡探索。简介关键词辅助心情匹配，并分散类型和导演；无偏好时降低恐怖类别优先级。这不是评分或个人喜爱概率。"]
            if c.company:
                warnings.append("和家人会限定家庭/动画类别，仍需自行核对适龄；其他同行选项仅记录本次情境，不影响排序。")
            if body.query and ("补充：" in body.query or body.mode != "discover"):
                warnings.append("补充文字暂不参与匹配；当前使用点选条件和已确认影片。")
            if not eligible:
                warnings.insert(0, f"当前查得的 {len(films)} 部影片没有符合全部条件的结果。请放宽时长、减少心情或类型条件；不会用样例补齐。")
            return RecommendationResponse(trace_id=uuid4().hex, data_mode="cached" if before == catalog.fetch_count else "live", status="ready" if candidates else "empty",
                candidates=candidates, evidence=evidence, questions=[], warnings=warnings, memory_used=False, catalog_size=len(films), matched_count=len(eligible))

    @app.get("/movies", response_model=MovieSearchResponse)
    def movies(query: str = Query(min_length=1, max_length=100), year: int | None = None):
        with catalog.lock:
            before = catalog.fetch_count
            found = catalog.search(query.strip(), year)
            return MovieSearchResponse(data_mode="cached" if before == catalog.fetch_count else "live", movies=[m for m, at in found], requires_confirmation=len(found)>1)

    @app.get("/movies/{movie_id}", response_model=Movie, responses={404: {"model": ErrorResponse}})
    def movie(movie_id: str):
        with catalog.lock:
            return find(movie_id)[0]

    @app.post("/comparisons", response_model=MovieSearchResponse)
    def comparisons(body: ComparisonRequest):
        with catalog.lock:
            before = catalog.fetch_count
            found = [find(mid)[0] for mid in body.movie_ids]
            return MovieSearchResponse(data_mode="cached" if before == catalog.fetch_count else "live", movies=found, requires_confirmation=False)

    return app


app = create_app()
