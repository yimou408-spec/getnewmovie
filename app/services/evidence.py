"""Same-movie evidence, explicit mappings and persistent bounded TTL cache.

Independent publisher groups and usage permissions come from source adapters,
never from domain counts. Stale records retain their original retrieval times.
"""
import time
from threading import RLock
import os

from scripts.movie_catalog_errors import CatalogError
from scripts.s0_contracts import SourceEvidenceResult
from app.services.budget import current_budget


class DoubanSource:
    source = "Douban"

    def fetch(self, movie_id, external_id):
        import httpx
        from scripts.douban_adapter import DoubanAdapter
        with httpx.Client(timeout=8, follow_redirects=False, trust_env=False,
                          headers={"User-Agent": "getnewmovie-feasibility/1.1"}) as client:
            # A fresh two-call adapter; the request-scoped ledger is shared.
            return DoubanAdapter(client, max_requests=2).fetch(movie_id, external_id)


def configured_adapters():
    adapters = {"douban": DoubanSource()} if os.getenv("MOVIE_DOUBAN_LIVE") == "1" else {}
    token = os.getenv("TMDB_READ_TOKEN", "").strip()
    if token and os.getenv("MOVIE_TMDB_LIVE", "1") == "1":
        from scripts.tmdb_adapter import TMDBSource
        adapters["tmdb"] = TMDBSource(token)
        if os.getenv("MOVIE_TMDB_REVIEWS_LIVE") == "1":
            from scripts.tmdb_reviews import TMDBReviewSource
            adapters["tmdb_reviews"] = TMDBReviewSource(token)
    return adapters


class EvidenceService:
    def __init__(self, repository, adapters=None, *, ttl=1800, clock=time.time):
        self.repository, self.adapters = repository, adapters or {}
        self.ttl, self.clock, self.lock = ttl, clock, RLock()

    def collect(self, movie):
        from scripts.movie_identity import confirm_external_identity
        target = movie
        for identity in self.repository.mappings(movie.movie_id):
            movie = confirm_external_identity(movie, identity)
        # Caller owns a request-local Movie; expose confirmed links without
        # replacing Apple title/runtime or modifying the shared catalog.
        target.external_ids = movie.model_copy(deep=True).external_ids
        results = []
        providers = {"douban", *self.adapters, *(link.provider for link in movie.external_ids or []
                                                if link.provider in {"douban", "tmdb"})}
        for provider in sorted(providers):
            adapter = self.adapters.get(provider)
            source = getattr(adapter, "source", {"douban": "Douban", "tmdb": "TMDB"}.get(provider, provider))
            identity_provider = getattr(adapter, "identity_provider", provider)
            link = next((item for item in movie.external_ids or [] if item.provider == identity_provider), None)
            if adapter is None or link is None:
                results.append(SourceEvidenceResult(movie_id=movie.movie_id, source=source, status="not_configured",
                    warnings=["来源适配或经核验的影片映射尚未配置。未请求来源。 "]))
                continue
            if link.status != "confirmed":
                results.append(SourceEvidenceResult(movie_id=movie.movie_id, source=source, status="ambiguous"))
                continue
            # No catalog lock is held while source tools run.
            with self.lock:
                cached = self.repository.cache_get(movie.movie_id, source, link.external_id)
                if cached and self.clock() - cached[0] < self.ttl:
                    result = SourceEvidenceResult.model_validate(cached[1])
                    result.cache_status = "fresh"
                    results.append(result)
                    continue
            try:
                result = SourceEvidenceResult.model_validate(adapter.fetch(movie.movie_id, link.external_id))
                if result.movie_id != movie.movie_id or result.source != source:
                    raise ValueError("adapter result bound to wrong movie/source")
            except CatalogError as error:
                result = SourceEvidenceResult(movie_id=movie.movie_id, source=source,
                    status="budget_exhausted" if error.code == "BUDGET_EXHAUSTED" else "timeout")
            except (ValueError, TypeError):
                result = SourceEvidenceResult(movie_id=movie.movie_id, source=source, status="parse_error")
            # Acquisition is not clearance to persist or republish third-party text.
            permitted = [item for item in result.evidence if item.usage_basis in {"licensed", "provider_terms", "synthetic"}]
            if len(permitted) != len(result.evidence):
                result.warnings.append("材料使用条件尚未核验；未存储或发布正文与评分。")
            result.evidence = permitted
            ids = {item.evidence_id for item in permitted}
            result.ratings = [rating for rating in result.ratings if rating.evidence_id in ids]
            if result.status in {"ok", "no_results"}:
                if current_budget.get():
                    current_budget.get().check()
                self.repository.cache_put(movie.movie_id, source, link.external_id, self.clock(), result.model_dump(mode="json"))
            elif cached:
                result.cache_status = "stale"
                result.evidence = SourceEvidenceResult.model_validate(cached[1]).evidence
                # Stale ratings are not promoted to current movie facts.
                result.warnings.append("更新失败；保留旧材料及原采集时间，未当作最新证据。")
            results.append(result)
        return results
