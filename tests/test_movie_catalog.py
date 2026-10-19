"""Offline provider tests. Invented IDs here are test data, never a live fallback."""
import httpx
import pytest
from fastapi.testclient import TestClient

from scripts.movie_catalog import AppleCatalog, CatalogError
from scripts.movie_server import create_app


def transport(request):
    records = [
        dict(trackId=101, trackName="Test Comedy", primaryGenreName="Comedy", trackTimeMillis=5_400_001),
        dict(trackId=102, trackName="Test Drama", primaryGenreName="Drama", trackTimeMillis=7_200_000),
        dict(trackId=103, trackName="Test Family", primaryGenreName="Kids & Family", trackTimeMillis=4_800_000),
        dict(trackId=104, trackName="Unknown duration", primaryGenreName="Comedy"),
    ]
    for r in records:
        r.update(kind="feature-movie", releaseDate="2020-01-01T00:00:00Z", trackViewUrl=f"https://itunes.apple.com/us/movie/id{r['trackId']}")
    if request.url.path == "/lookup":
        ids = request.url.params["id"].split(",")
        return httpx.Response(200, json={"results": [r for r in records if str(r["trackId"]) in ids]})
    if request.url.path == "/search":
        assert request.url.params["entity"] == "movie"
        return httpx.Response(200, json={"results": [records[1]] if request.url.params["term"] == "off-chart search" else []})
    category = next((g for g in ["4404", "4406", "4410"] if f"genre={g}" in request.url.path), None)
    selected = {"4404": [101, 104], "4406": [102], "4410": [103]}.get(category, [101, 102, 103, 104])
    return httpx.Response(200, json={"feed": {"entry": [
        {"id": {"attributes": {"im:id": str(i)}}, "im:name": {"label": next(r["trackName"] for r in records if r["trackId"] == i)}} for i in selected
    ]}})


def client():
    return TestClient(create_app(AppleCatalog(httpx.Client(transport=httpx.MockTransport(transport)), rate_limit=100)))


def recommend(c, **constraints):
    return c.post("/recommendations", json={"mode": "discover", "query": "no input", "session_id": "test", "constraints": constraints})


def test_default_real_contract_and_sources_and_cache():
    with client() as c:
        r = recommend(c).json()
        assert r["data_mode"] == "live" and len(r["candidates"]) == 3
        assert all(x["movie"]["movie_id"].startswith("itunes:") for x in r["candidates"])
        assert all(x["movie"]["ratings"] == [] for x in r["candidates"])
        assert all(e["source"] == "Apple iTunes US" for e in r["evidence"])
        assert recommend(c).json()["data_mode"] == "cached"


def test_genre_mood_and_strict_runtime_actually_filter():
    with client() as c:
        comedy = recommend(c, genres=["喜剧"]).json()
        drama = recommend(c, moods=["感动一下"]).json()
        assert {x["movie"]["movie_id"] for x in comedy["candidates"]} == {"itunes:101", "itunes:104"}
        assert [x["movie"]["movie_id"] for x in drama["candidates"]] == ["itunes:102"]
        # 90m + 1ms must not sneak through a 90 minute ceiling; missing runtime excluded too.
        assert recommend(c, genres=["喜剧"], max_runtime_minutes=90).json()["status"] == "empty"
        assert len(recommend(c, genres=["喜剧"], max_runtime_minutes=91).json()["candidates"]) == 1


def test_family_intersection_exclusions_and_empty_explanation():
    with client() as c:
        r = recommend(c, company="和家人").json()
        assert [x["movie"]["movie_id"] for x in r["candidates"]] == ["itunes:103"]
        assert recommend(c, genres=["喜剧"], moods=["感动一下"]).json()["status"] == "empty"
        assert recommend(c, exclude_movie_ids=["itunes:101", "itunes:102", "itunes:103", "itunes:104"]).json()["warnings"]


def test_lookup_comparison_and_invalid_identity_are_not_synthetic():
    with client() as c:
        assert c.get("/movies/itunes:101").json()["title"] == "Test Comedy"
        assert c.post("/comparisons", json={"movie_ids": ["itunes:101", "itunes:102"]}).json()["data_mode"] == "live"
        assert c.get("/movies/syn:demo").status_code == 404
        assert recommend(c, genres=["not supported"]).status_code == 422


def test_store_search_is_not_limited_to_chart_substrings_and_year_is_exact():
    with client() as c:
        assert c.get("/movies", params={"query": "off-chart search", "year": 2020}).json()["movies"][0]["movie_id"] == "itunes:102"
        assert c.get("/movies", params={"query": "off-chart search", "year": 1990}).json()["movies"] == []


def test_empty_store_search_falls_back_to_real_chart_titles_without_fake_results():
    with client() as c:
        assert c.get("/movies", params={"query": "Test Comedy"}).json()["movies"][0]["movie_id"] == "itunes:101"
        assert c.get("/movies", params={"query": "nonexistent film"}).json()["movies"] == []


def test_era_filter_and_exclusion_are_hard_constraints_in_both_sort_modes():
    with client() as c:
        for order in ["balanced", "popular"]:
            assert recommend(c, era="classic", sort_by=order).json()["status"] == "empty"
            r = recommend(c, era="recent", sort_by=order, exclude_movie_ids=["itunes:101"]).json()
            assert all(x["movie"]["year"] >= 2020 and x["movie"]["movie_id"] != "itunes:101" for x in r["candidates"])


@pytest.mark.parametrize("status", [429, 500])
def test_upstream_failure_is_error_never_fake_movies(status):
    provider = AppleCatalog(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status))))
    with TestClient(create_app(provider)) as c:
        response = recommend(c)
        assert response.status_code == 503
        assert "candidates" not in response.json()


def test_timeout_and_malformed_upstream_and_missing_runtime():
    for handler in [lambda r: httpx.Response(200, json={"unexpected": True}), lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("test"))]:
        with TestClient(create_app(AppleCatalog(httpx.Client(transport=httpx.MockTransport(handler))))) as c:
            assert recommend(c).status_code in (503, 504)
