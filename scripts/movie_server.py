"""Real catalog API. Start: python -m uvicorn scripts.movie_server:app --port 8000."""
from uuid import uuid4
from collections import OrderedDict
from threading import Lock
from urllib.parse import urlparse
import re
import time

import httpx

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, Response

from scripts.movie_catalog import AppleCatalog, CatalogError, MOODS
from scripts.movie_ranking import MOOD_CLUES
from scripts.mvp_recommendation_rules import MovieSelection, select_movies
from scripts.mvp_model import ModelAdapter, ModelSettings
from scripts.mvp_workflow import AgentContext, AgentWorkflow
from scripts.movie_intent import IntentSessions, explain
from scripts.s0_contracts import (Availability, Candidate, ComparisonRequest, ErrorResponse, Evidence, HealthResponse, Movie,
                                  MovieSearchResponse, Reason, RecommendationRequest, RecommendationResponse, ServiceCapabilities, SessionResponse)


def create_app(catalog=None, *, model_factory=None):
    if catalog is None and model_factory is None:
        settings = ModelSettings.from_env()
        if settings is not None:
            model_factory = lambda: ModelAdapter(settings, max_requests=1)
    catalog = catalog or AppleCatalog()
    sessions = IntentSessions()
    agent_contexts = {}
    workflow = AgentWorkflow(catalog, model_factory) if model_factory else None
    artwork_cache = OrderedDict()
    artwork_lock = Lock()
    app = FastAPI(title="Tonight movie catalog", version="0.1.0", description="Apple US real charts. Rule-based matching, no synthetic fallback.")

    @app.exception_handler(CatalogError)
    async def source_error(request: Request, exc: CatalogError):
        return JSONResponse(status_code=exc.status, content=ErrorResponse(trace_id=uuid4().hex, data_mode="live",
            code=exc.code, message=exc.message, retryable=exc.status >= 500).model_dump(mode="json"))

    @app.post("/sessions", response_model=SessionResponse)
    def create_session():
        return SessionResponse(session_id=sessions.create(), expires_in_seconds=sessions.ttl)

    @app.get("/health", response_model=HealthResponse)
    def health():
        return HealthResponse(service="real-catalog", provider="Apple iTunes US", synthetic_fallback=False,
                              cache_ttl_seconds=1800, capabilities=ServiceCapabilities(metadata=True, natural_language=True,
                                                                                      model_understanding=workflow is not None))

    def find(mid):
        if not mid.startswith("itunes:"):
            raise CatalogError("NOT_FOUND", "影片不在当前真实片库中，请重新查找。", 404)
        found = catalog.lookup([mid.removeprefix("itunes:")])
        if not found:
            raise CatalogError("NOT_FOUND", "资料源未返回这部影片。", 404)
        return found[0]

    @app.get("/artwork/{movie_id}", include_in_schema=False)
    def artwork(movie_id: str):
        # Only catalog-owned IDs can resolve artwork; callers never supply a URL.
        with catalog.lock:
            film, _ = find(movie_id)
        url = str(film.poster_url or "")
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or parsed.port not in (None, 443)
                or not re.fullmatch(r"is[0-9]+(?:-ssl)?\.mzstatic\.com", parsed.hostname or "")):
            raise CatalogError("NOT_FOUND", "这部影片暂未提供可用海报。", 404)
        # Keep provider identity/path; request a readable portrait rendition.
        url = re.sub(r"/[0-9]+x[0-9]+bb\.(?:jpg|png)$", "/600x900bb.jpg", url)
        now = time.monotonic()
        headers = {"Cache-Control": "public, max-age=1800", "X-Content-Type-Options": "nosniff"}
        with artwork_lock:
            cached = artwork_cache.get(url)
            if cached and now - cached[0] < 1800:
                artwork_cache.move_to_end(url)
                return Response(cached[1], media_type=cached[2], headers=headers)
        try:
            with catalog.client.stream("GET", url, timeout=10, follow_redirects=False) as upstream:
                media_type = upstream.headers.get("content-type", "").split(";")[0]
                if upstream.status_code != 200 or media_type not in ("image/jpeg", "image/png", "image/webp"):
                    raise CatalogError("UPSTREAM_UNAVAILABLE", "海报源暂时不可用，请稍后重试。", 503)
                content = bytearray()
                for chunk in upstream.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 2 * 1024 * 1024:
                        raise CatalogError("UPSTREAM_UNAVAILABLE", "海报文件过大，暂时无法展示。", 503)
        except httpx.HTTPError as exc:
            raise CatalogError("UPSTREAM_UNAVAILABLE", "海报加载失败，请稍后重试。", 503) from exc
        if not content:
            raise CatalogError("UPSTREAM_UNAVAILABLE", "海报源返回了空文件。", 503)
        data = bytes(content)
        with artwork_lock:
            artwork_cache[url] = (now, data, media_type)
            artwork_cache.move_to_end(url)
            while len(artwork_cache) > 32:
                artwork_cache.popitem(last=False)
        return Response(data, media_type=media_type, headers=headers)

    @app.post("/recommendations", response_model=RecommendationResponse, responses={503: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
    def recommendations(body: RecommendationRequest):
        agent_result = None
        workflow_before = catalog.fetch_count
        if workflow is not None and body.mode == "discover":
            context = None
            if body.input_source == "natural_language":
                with sessions.lock:
                    valid_ids = {sid for sid, entry in sessions.sessions.items() if entry[0] > sessions.clock()}
                    for sid in list(agent_contexts):
                        if sid not in valid_ids:
                            del agent_contexts[sid]
                    if body.session_id not in valid_ids:
                        raise CatalogError("SESSION_EXPIRED", "临时会话已过期，请重新提交观影想法。", 409)
                    context = agent_contexts.get(body.session_id, AgentContext())
            agent_result = workflow.run(body, context)
            if agent_result.status == "error":
                code = agent_result.error_code
                if code in ("STALE_CLARIFICATION", "INVALID_CLARIFICATION"):
                    raise CatalogError(code, "确认条件已变化，请修改或重新提交。", 409 if code == "STALE_CLARIFICATION" else 422)
                timeout = code in ("MODEL_TIMEOUT", "WORKFLOW_TIMEOUT")
                raise CatalogError("UPSTREAM_TIMEOUT" if timeout else "UPSTREAM_UNAVAILABLE",
                                   "模型理解暂时未完成，请重试；原有结果仍保留。", 504 if timeout else 503)
            if body.input_source == "natural_language":
                with sessions.lock:
                    agent_contexts[body.session_id] = agent_result.context
            interpretation = explain(agent_result.constraints, method=agent_result.method,
                                     conflicts=agent_result.conflicts, unhandled=agent_result.unhandled)
            clarification_id, questions = agent_result.clarification_id, agent_result.questions
        else:
            interpretation, clarification_id, questions = (sessions.resolve(body) if body.input_source == "natural_language"
                                                           else (explain(body.constraints), None, []))
        if questions:
            return RecommendationResponse(trace_id=uuid4().hex, data_mode="live", status="needs_clarification",
                candidates=[], evidence=[], questions=questions, warnings=["尚未查询片库。请确认冲突或无法执行的要求，也可以修改输入重新提交。"],
                memory_used=False, interpretation=interpretation, clarification_id=clarification_id)
        with catalog.lock:
            before = workflow_before if agent_result is not None else catalog.fetch_count
            c = interpretation.effective_constraints
            mood_genres = set().union(*(MOODS[m] for m in c.moods)) if c.moods else set()
            pool_genres = c.genres or sorted(mood_genres) or (["家庭"] if c.company == "和家人" else [])
            if agent_result is not None:
                films = agent_result.candidates
            elif body.mode == "known_movie":
                films = [find(body.movie_id)]
            elif body.mode == "watchlist":
                films = [find(mid) for mid in dict.fromkeys(body.watchlist_movie_ids)]
            else:
                films = catalog.pool(pool_genres)
            selection = MovieSelection(films, films) if agent_result is not None else select_movies(films, c)
            eligible = selection.eligible
            candidates, evidence = [], []
            for movie, at in selection.candidates:
                eid = f"apple-{movie.movie_id.split(':')[1]}"
                facts = f"Apple 美国区分类：{'、'.join(movie.genres)}；正片时长：{movie.runtime_minutes or '未知'} 分钟。"
                facts += f"导演：{movie.director or '未知'}；美国内容分级：{movie.content_advisory or '未知'}。"
                evidence.append(Evidence(evidence_id=eid, movie_id=movie.movie_id, source="Apple iTunes US", url=movie.source_url or "https://itunes.apple.com/us/", retrieved_at=at, kind="metadata", claim=facts, spoiler_level="safe"))
                match = [f"类型符合：{'、'.join(c.genres)}。"] if c.genres else []
                if c.moods:
                    clues = set().union(*(MOOD_CLUES[m] for m in c.moods)) & set(movie.tags)
                    match.append(f"简介词法线索：{'、'.join(sorted(clues))}；用于「{'、'.join(c.moods)}」匹配推断。" if clues else f"简介缺少「{'、'.join(c.moods)}」的明确线索，心情匹配待确认。")
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
                        "类型、片长、年代和排除是硬条件；心情只辅助召回与排序，未知字段不进入对应限定结果。",
                        "排序：来源顺序，不代表口碑或适合程度。" if c.sort_by == "popular" else "排序：均衡探索。简介关键词辅助心情匹配，并分散类型和导演；无偏好时降低恐怖类别优先级。这不是评分或个人喜爱概率。"]
            if c.company:
                warnings.append("和家人会限定家庭/动画类别，仍需自行核对适龄；其他同行选项仅记录本次情境，不影响排序。")
            if body.input_source == "natural_language":
                warnings.append("文字由模型理解并经代码筛选；心情为软偏好，不能保证内容感受。" if interpretation.method == "llm-v1" else "文字由规则解析器处理，支持常见类型、心情、时长、年代与排除；不代表通用模型理解。心情为软偏好，不能保证内容感受。")
                if interpretation.unhandled:
                    warnings.append("经你确认未采用：" + "；".join(interpretation.unhandled))
            elif body.query and ("补充：" in body.query or body.mode != "discover"):
                warnings.append("补充文字暂不参与匹配；当前使用点选条件和已确认影片。")
            if not eligible:
                total = agent_result.catalog_size if agent_result is not None else len(films)
                warnings.insert(0, f"当前查得的 {total} 部影片没有符合全部条件的结果。请放宽时长、年代或类型条件；不会用样例补齐。")
            return RecommendationResponse(trace_id=uuid4().hex, data_mode="cached" if before == catalog.fetch_count else "live", status="ready" if candidates else "empty",
                candidates=candidates, evidence=evidence, questions=[], warnings=warnings, memory_used=False,
                catalog_size=agent_result.catalog_size if agent_result is not None else len(films),
                matched_count=agent_result.matched_count if agent_result is not None else len(eligible), interpretation=interpretation)

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
