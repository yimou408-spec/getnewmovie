"""Versioned S0 wire types; schema shared by mock API and experiment validation."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

VERSION = "0.1.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Constraints(StrictModel):
    max_runtime_minutes: int | None = Field(default=None, ge=1, le=600)
    exclude_movie_ids: list[str] = Field(default_factory=list, max_length=500)
    exclude_genres: list[str] = Field(default_factory=list, max_length=20)
    preferred_tags: list[str] = Field(default_factory=list, max_length=20)


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

    @model_validator(mode="after")
    def check_mode(self):
        if self.mode == "watchlist" and not self.watchlist_movie_ids:
            raise ValueError("watchlist mode needs confirmed movie IDs")
        if self.mode == "known_movie" and not self.movie_id:
            raise ValueError("known_movie mode needs resolved movie_id; use /movies for lookup")
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


class Movie(StrictModel):
    movie_id: str = Field(pattern=r"^(syn:[A-Za-z0-9_-]+|tmdb:[1-9][0-9]*)$")
    title: str
    year: int | None = Field(default=None, ge=1888, le=2200)
    runtime_minutes: int | None = Field(default=None, ge=1, le=600)
    countries: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    ratings: list[Rating] = Field(default_factory=list)


class Evidence(StrictModel):
    evidence_id: str
    movie_id: str
    source: str
    url: HttpUrl
    retrieved_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    kind: Literal["metadata", "review", "rating", "synthetic"]
    claim: str = Field(min_length=1, max_length=1000)
    spoiler_level: Literal["safe", "unknown", "contains_spoilers"]


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
    code: Literal["UPSTREAM_TIMEOUT", "NOT_CONFIGURED", "NOT_FOUND", "INVALID_SCENARIO"]
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
