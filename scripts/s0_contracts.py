"""Versioned S0 wire types; schema shared by mock API and experiment validation."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

VERSION = "0.1.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceCapabilities(StrictModel):
    """Implemented paths only, not a claim of upstream availability or quality."""
    metadata: bool = False
    ratings: bool = False
    reviews: bool = False
    natural_language: bool = False
    model_understanding: bool = False
    long_term_memory: bool = False
    local_availability: bool = False


class HealthResponse(StrictModel):
    service: str
    provider: str
    synthetic_fallback: bool
    cache_ttl_seconds: int = Field(ge=0)
    # Optional for compatibility with the previously deployed health response.
    capabilities: ServiceCapabilities | None = None


class IntegrationState(StrictModel):
    state: Literal["not_configured", "incomplete", "invalid", "configured"]
    missing: list[str] = Field(default_factory=list)
    live_verified: bool = False
    verified_at: str | None = None


class RuntimeConfiguration(StrictModel):
    catalog_provider: Literal["apple", "tmdb"]
    intent_method: Literal["rules-v1", "llm-v1"]
    llm: IntegrationState
    tmdb: IntegrationState
    model_location: Literal["local", "remote", "rules"] = "rules"
    model_name: str | None = None
    catalog_fallback_active: bool = False


class Constraints(StrictModel):
    max_runtime_minutes: int | None = Field(default=None, ge=1, le=600)
    exclude_movie_ids: list[str] = Field(default_factory=list, max_length=500)
    exclude_genres: list[str] = Field(default_factory=list, max_length=20)
    preferred_tags: list[str] = Field(default_factory=list, max_length=20)
    moods: list[Literal["轻松解压", "温暖治愈", "烧脑过瘾", "浪漫心动", "惊奇冒险", "感动一下"]] = Field(default_factory=list, max_length=6)
    genres: list[Literal["喜剧", "科幻与奇幻", "惊悚", "动作", "爱情", "动画", "剧情", "家庭", "纪录片", "恐怖"]] = Field(default_factory=list, max_length=10)
    company: Literal["", "一个人", "两个人", "和朋友", "和家人"] = ""
    sort_by: Literal["balanced", "popular"] = "balanced"
    era: Literal["any", "recent", "2000s", "classic"] = "any"


class ClarificationAnswer(StrictModel):
    question_id: str = Field(min_length=1, max_length=100)
    option: str = Field(min_length=1, max_length=100)


class ClarificationSubmission(StrictModel):
    clarification_id: str = Field(min_length=1, max_length=100)
    answers: list[ClarificationAnswer] = Field(min_length=1, max_length=2)


class SessionResponse(StrictModel):
    session_id: str
    expires_in_seconds: int


class Interpretation(StrictModel):
    method: Literal["rules-v1", "llm-v1"] = "rules-v1"
    effective_constraints: Constraints
    hard_conditions: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    unhandled: list[str] = Field(default_factory=list)


class RecommendationRequest(StrictModel):
    mode: Literal["discover", "watchlist", "known_movie"]
    query: str = Field(min_length=1, max_length=2000)
    region: str = Field(default="CN", pattern=r"^[A-Z]{2}$")
    session_id: str = Field(min_length=1, max_length=100)
    memory_enabled: bool = False
    clarification_count: int = Field(default=0, ge=0, le=2)
    movie_id: str | None = None
    watchlist_movie_ids: list[str] = Field(default_factory=list, max_length=500)
    constraints: Constraints = Field(default_factory=Constraints)
    input_source: Literal["structured", "natural_language"] = "structured"
    clarification: ClarificationSubmission | None = None

    @model_validator(mode="after")
    def check_mode(self):
        if self.mode == "watchlist" and not self.watchlist_movie_ids:
            raise ValueError("watchlist mode needs confirmed movie IDs")
        if self.mode == "known_movie" and not self.movie_id:
            raise ValueError("known_movie mode needs resolved movie_id; use /movies for lookup")
        if self.clarification is not None and self.input_source != "natural_language":
            raise ValueError("clarification requires natural language input")
        return self


class Rating(StrictModel):
    source: str
    value: float = Field(ge=0)
    scale: float = Field(gt=0)
    vote_count: int | None = Field(default=None, ge=0)
    evidence_id: str

    @model_validator(mode="after")
    def within_scale(self):
        if self.value > self.scale:
            raise ValueError("rating exceeds its scale")
        return self


class ExternalMovieIdentity(StrictModel):
    provider: Literal["douban", "tmdb", "itunes"]
    external_id: str = Field(pattern=r"^[1-9][0-9]*$")
    status: Literal["candidate", "confirmed"]
    url: HttpUrl
    basis: Literal["title_year", "human_verified", "provider_mapping"]

    @model_validator(mode="after")
    def check_confirmation(self):
        if self.status == "confirmed" and self.basis == "title_year":
            raise ValueError("title/year match alone cannot confirm a cross-source identity")
        hosts = {"douban": {"movie.douban.com"}, "tmdb": {"www.themoviedb.org"},
                 "itunes": {"itunes.apple.com", "tv.apple.com"}}
        paths = {"douban": f"/subject/{self.external_id}/", "tmdb": f"/movie/{self.external_id}"}
        if (self.url.scheme != "https" or self.url.host not in hosts[self.provider]
                or self.url.username or self.url.password or self.url.query or self.url.fragment
                or self.url.port not in {None, 443}):
            raise ValueError("external identity requires a public provider HTTPS URL")
        if self.provider in paths and self.url.path != paths[self.provider]:
            raise ValueError("external identity URL must match its provider ID")
        return self


class Movie(StrictModel):
    movie_id: str = Field(pattern=r"^(syn:[A-Za-z0-9_-]+|tmdb:[1-9][0-9]*|itunes:[1-9][0-9]*)$")
    title: str
    year: int | None = Field(default=None, ge=1888, le=2200)
    runtime_minutes: int | None = Field(default=None, ge=1, le=600)
    countries: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    ratings: list[Rating] = Field(default_factory=list)
    poster_url: HttpUrl | None = None
    source_url: HttpUrl | None = None
    director: str | None = None
    content_advisory: str | None = None
    # Additive: the original movie_id remains the public selection identity.
    external_ids: list[ExternalMovieIdentity] | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def unique_external_providers(self):
        providers = [link.provider for link in self.external_ids or []]
        if len(providers) != len(set(providers)):
            raise ValueError("external provider mapping must be unique")
        return self


class Evidence(StrictModel):
    evidence_id: str
    movie_id: str
    source: str
    url: HttpUrl
    retrieved_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    kind: Literal["metadata", "review", "rating", "synthetic"]
    claim: str = Field(min_length=1, max_length=1000)
    spoiler_level: Literal["safe", "unknown", "contains_spoilers"]
    granularity: Literal["metadata", "rating", "excerpt", "full_text"] | None = None
    author: str | None = Field(default=None, max_length=160)
    source_content_id: str | None = Field(default=None, max_length=160)
    independent_source_group: str | None = Field(default=None, max_length=160)
    usage_basis: Literal["unverified", "licensed", "provider_terms", "synthetic"] | None = None

    @model_validator(mode="after")
    def check_granularity(self):
        allowed = {"metadata": {None, "metadata"}, "rating": {None, "rating"},
                   "review": {None, "excerpt", "full_text"},
                   "synthetic": {None, "metadata", "rating", "excerpt", "full_text"}}
        if self.granularity not in allowed[self.kind]:
            raise ValueError("evidence kind must match its content granularity")
        return self


class SourceEvidenceResult(StrictModel):
    """Adapter result; availability is separate from the amount of evidence."""
    movie_id: str
    source: str
    status: Literal["ok", "no_results", "not_configured", "access_limited", "timeout",
                    "parse_error", "upstream_error", "budget_exhausted", "ambiguous"]
    evidence: list[Evidence] = Field(default_factory=list)
    ratings: list[Rating] = Field(default_factory=list)
    cache_status: Literal["none", "fresh", "stale"] = "none"
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_binding(self):
        evidence_map = {item.evidence_id: item for item in self.evidence}
        if len(evidence_map) != len(self.evidence):
            raise ValueError("duplicate evidence ID")
        if any(e.movie_id != self.movie_id or e.source != self.source for e in self.evidence):
            raise ValueError("adapter evidence must belong to its movie and source")
        for rating in self.ratings:
            evidence = evidence_map.get(rating.evidence_id)
            if evidence is None or evidence.kind != "rating" or rating.source != self.source:
                raise ValueError("rating requires matching rating evidence")
        return self


class Reason(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)
    kind: Literal["metadata_fact", "source_opinion", "matching_inference"]


class Availability(StrictModel):
    region: str = Field(pattern=r"^[A-Z]{2}$")
    status: Literal["unknown", "stale", "listed", "search_entry"]
    provider: str | None = None
    offer_type: Literal["cinema", "subscription", "rent", "buy", "free", "unknown"] = "unknown"
    url: HttpUrl | None = None
    checked_at: str | None = None


class Candidate(StrictModel):
    movie: Movie
    reason: Reason
    caveats: list[str] = Field(default_factory=list)
    uncertain_conditions: list[str] = Field(default_factory=list)
    availability: list[Availability] = Field(min_length=1)


class Question(StrictModel):
    question_id: str
    text: str
    options: list[str] = Field(default_factory=list, max_length=5)


class RecommendationResponse(StrictModel):
    contract_version: Literal["0.1.0"] = VERSION
    trace_id: str
    data_mode: Literal["synthetic", "live", "cached"]
    status: Literal["ready", "empty", "needs_clarification", "degraded"]
    candidates: list[Candidate] = Field(max_length=3)
    evidence: list[Evidence]
    questions: list[Question] = Field(max_length=2)
    warnings: list[str]
    memory_used: bool
    catalog_size: int | None = Field(default=None, ge=0)
    matched_count: int | None = Field(default=None, ge=0)
    interpretation: Interpretation | None = None
    clarification_id: str | None = None
    source_results: list[SourceEvidenceResult] | None = None

    @model_validator(mode="after")
    def validate_state_and_references(self):
        if self.status in ("empty", "needs_clarification") and self.candidates:
            raise ValueError("empty/clarification state cannot contain candidates")
        if self.status == "needs_clarification" and not self.questions:
            raise ValueError("clarification state requires questions")
        if self.status != "needs_clarification" and self.questions:
            raise ValueError("questions require clarification state")
        if self.status == "ready" and not self.candidates:
            raise ValueError("ready state requires candidates")
        if self.status in ("empty", "degraded") and not self.warnings:
            raise ValueError("empty/degraded state requires explanation")
        ids = [item.movie.movie_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate movie ID")
        evidence_map = {e.evidence_id: e for e in self.evidence}
        for result in self.source_results or []:
            if result.movie_id not in ids:
                raise ValueError("source result must belong to a returned film")
            for item in result.evidence:
                if evidence_map.get(item.evidence_id) != item:
                    raise ValueError("source result evidence must match the response evidence")
        if len(evidence_map) != len(self.evidence):
            raise ValueError("duplicate evidence ID")
        for candidate in self.candidates:
            refs = candidate.reason.evidence_ids + [r.evidence_id for r in candidate.movie.ratings]
            for ref in refs:
                if ref not in evidence_map or evidence_map[ref].movie_id != candidate.movie.movie_id:
                    raise ValueError("evidence must exist and refer to the same film")
                if evidence_map[ref].spoiler_level != "safe":
                    raise ValueError("default card cannot cite unsafe evidence")
            for rating in candidate.movie.ratings:
                if evidence_map[rating.evidence_id].source != rating.source:
                    raise ValueError("rating source must match the cited evidence source")
            if self.data_mode == "synthetic" and not candidate.movie.movie_id.startswith("syn:"):
                raise ValueError("synthetic fixtures must use synthetic identities")
        return self


class ErrorResponse(StrictModel):
    contract_version: Literal["0.1.0"] = VERSION
    trace_id: str
    data_mode: Literal["synthetic", "live", "cached"]
    code: Literal["UPSTREAM_TIMEOUT", "UPSTREAM_UNAVAILABLE", "UPSTREAM_RATE_LIMIT", "NOT_CONFIGURED", "NOT_FOUND", "INVALID_SCENARIO", "SESSION_EXPIRED", "STALE_CLARIFICATION", "INVALID_CLARIFICATION"]
    message: str
    retryable: bool


class MovieSearchResponse(StrictModel):
    data_mode: Literal["synthetic", "live", "cached"]
    movies: list[Movie]
    requires_confirmation: bool


class ComparisonRequest(StrictModel):
    movie_ids: list[str] = Field(min_length=2, max_length=3)

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.movie_ids)) != len(self.movie_ids):
            raise ValueError("comparison IDs must be distinct")
        return self
