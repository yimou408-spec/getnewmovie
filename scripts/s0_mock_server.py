"""Local-only contract fixture server. No recommendation engine, auth or memory."""
import json
from pathlib import Path

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from scripts.s0_contracts import (
    ComparisonRequest, ErrorResponse, Movie, MovieSearchResponse,
    RecommendationRequest, RecommendationResponse, VERSION,
)

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="Movie Agent S0 synthetic mock", version=VERSION,
              description="Local development only. Every fixture is synthetic; no persistence or model calls.")


def load(name):
    return json.loads((ROOT / "contracts/examples" / f"{name}.json").read_text(encoding="utf-8"))


def catalog():
    return [Movie.model_validate(item) for item in json.loads((ROOT / "data/s0/synthetic_catalog.json").read_text(encoding="utf-8"))]


def error(code, message, status):
    return JSONResponse(status_code=status, content=ErrorResponse(
        trace_id="s0-mock-error", data_mode="synthetic", code=code,
        message=message, retryable=False,
    ).model_dump(mode="json"))


@app.middleware("http")
async def mark_synthetic(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Data-Mode"] = "synthetic"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", include_in_schema=False)
def prototype():
    return FileResponse(ROOT / "web/s0/index.html")


@app.post("/recommendations", response_model=RecommendationResponse, responses={
    400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 504: {"model": ErrorResponse},
})
def recommendations(body: RecommendationRequest, x_mock_scenario: str = Header(default="success")):
    if x_mock_scenario in ("timeout", "unconfigured"):
        return JSONResponse(status_code=504 if x_mock_scenario == "timeout" else 503, content=load(x_mock_scenario))
    if x_mock_scenario not in ("success", "empty", "clarification", "degraded"):
        return error("INVALID_SCENARIO", "Unknown mock scenario", 400)
    # Input validation is real; returned scenarios intentionally remain fixed.
    return RecommendationResponse.model_validate(load(x_mock_scenario))


@app.get("/movies", response_model=MovieSearchResponse)
def movies(query: str = Query(min_length=1, max_length=100), year: int | None = None):
    found = [movie for movie in catalog() if query.casefold() in movie.title.casefold()
             and (year is None or movie.year == year)]
    return MovieSearchResponse(data_mode="synthetic", movies=found, requires_confirmation=len(found) > 1)


@app.get("/movies/{movie_id}", response_model=Movie, responses={404: {"model": ErrorResponse}})
def movie(movie_id: str):
    found = next((item for item in catalog() if item.movie_id == movie_id), None)
    return found if found else error("NOT_FOUND", "Movie not in synthetic catalog", 404)


@app.post("/comparisons", response_model=MovieSearchResponse, responses={404: {"model": ErrorResponse}})
def comparisons(body: ComparisonRequest):
    by_id = {movie.movie_id: movie for movie in catalog()}
    if any(movie_id not in by_id for movie_id in body.movie_ids):
        return error("NOT_FOUND", "Movie not in synthetic catalog", 404)
    return MovieSearchResponse(data_mode="synthetic", movies=[by_id[mid] for mid in body.movie_ids], requires_confirmation=False)
