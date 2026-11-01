"""Cross-source links require explicit confirmation; fixtures are synthetic."""
import pytest
from pydantic import ValidationError

from scripts.s0_contracts import Evidence, ExternalMovieIdentity, Movie, SourceEvidenceResult
from scripts.movie_identity import confirm_external_identity


def test_mapping_preserves_itunes_identity_and_original_metadata():
    movie = Movie(movie_id="itunes:999", title="Original title", runtime_minutes=91)
    link = ExternalMovieIdentity(provider="douban", external_id="101", status="confirmed",
                                 url="https://movie.douban.com/subject/101/", basis="human_verified")
    result = confirm_external_identity(movie, link)
    assert result.movie_id == "itunes:999" and result.runtime_minutes == 91
    assert result.title == "Original title" and result.external_ids == [link]
    assert not movie.external_ids
    assert confirm_external_identity(result, link) == result


def test_candidates_conflicting_ids_and_invalid_namespace_are_rejected():
    movie = Movie(movie_id="itunes:999", title="Same title")
    candidate = ExternalMovieIdentity(provider="douban", external_id="101", status="candidate",
                                      url="https://movie.douban.com/subject/101/", basis="title_year")
    with pytest.raises(ValueError):
        confirm_external_identity(movie, candidate)
    first = candidate.model_copy(update={"status": "confirmed", "basis": "human_verified"})
    result = confirm_external_identity(movie, first)
    with pytest.raises(ValueError):
        confirm_external_identity(result, first.model_copy(update={"external_id": "202"}))
    with pytest.raises(ValidationError):
        ExternalMovieIdentity(provider="douban", external_id="../evil", status="confirmed",
                              url="https://movie.douban.com/", basis="human_verified")


def test_evidence_granularity_cannot_mislabel_rating_as_review_text():
    fields = dict(evidence_id="test", movie_id="itunes:999", source="Douban",
                  url="https://movie.douban.com/subject/101/", retrieved_at="2026-10-26T00:00:00Z",
                  kind="rating", claim="8.2/10", spoiler_level="safe")
    with pytest.raises(ValidationError):
        Evidence(**fields, granularity="full_text")
    assert Evidence(**fields).granularity is None  # legacy responses remain valid


def test_tool_result_rejects_evidence_bound_to_a_different_movie():
    evidence = Evidence(evidence_id="test", movie_id="itunes:111", source="Douban",
                        url="https://movie.douban.com/subject/101/", retrieved_at="2026-10-26T00:00:00Z",
                        kind="review", claim="Invented", spoiler_level="unknown", granularity="excerpt")
    with pytest.raises(ValidationError):
        SourceEvidenceResult(movie_id="itunes:999", source="Douban", status="ok", evidence=[evidence])


def test_external_link_must_match_its_provider_and_id():
    for url in ["http://movie.douban.com/subject/101/", "https://evil.test/subject/101/",
                "https://movie.douban.com/subject/202/", "https://movie.douban.com/subject/101/?token=x"]:
        with pytest.raises(ValidationError):
            ExternalMovieIdentity(provider="douban", external_id="101", status="candidate",
                                  basis="title_year", url=url)


def test_multifield_verification_records_agent_review_without_claiming_human_review():
    link = ExternalMovieIdentity(provider="tmdb", external_id="123", status="confirmed",
        basis="multi_field_verified", url="https://www.themoviedb.org/movie/123")
    result = confirm_external_identity(Movie(movie_id="itunes:999", title="Offline movie"), link)
    assert result.external_ids[0].basis == "multi_field_verified"
    assert result.title == "Offline movie"


def test_duplicate_external_provider_ids_are_rejected():
    link = dict(provider="douban", external_id="101", status="candidate", basis="title_year",
                url="https://movie.douban.com/subject/101/")
    with pytest.raises(ValidationError):
        Movie(movie_id="itunes:999", title="Test", external_ids=[link, link])


def test_source_status_is_additive_and_cannot_belong_to_unreturned_film():
    import json
    from pathlib import Path
    from scripts.s0_contracts import RecommendationResponse
    data = json.loads(Path("contracts/examples/success.json").read_text(encoding="utf-8"))
    mid = data["candidates"][0]["movie"]["movie_id"]
    data["source_results"] = [dict(movie_id=mid, source="Douban", status="access_limited")]
    assert RecommendationResponse.model_validate(data).source_results[0].status == "access_limited"
    data["source_results"][0]["movie_id"] = "syn:not-returned"
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)
