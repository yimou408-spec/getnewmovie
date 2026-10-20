"""Frozen rule cases, not evidence of subjective recommendation quality."""
from scripts.movie_ranking import rank_movies
from scripts.s0_contracts import Constraints, Movie


def film(mid, genre, tags=(), director="", year=2020):
    return (Movie(movie_id=f"itunes:{mid}", title=f"Test {mid}", genres=[genre],
                  tags=list(tags), director=director, year=year, runtime_minutes=95), "2026-10-19T00:00:00Z")


def test_calm_content_outweighs_chart_position_and_risk_is_not_quality():
    rows = [film(1, "喜剧", ["恐怖线索"]), film(2, "喜剧", ["友谊", "成长"]), film(3, "喜剧")]
    ranked = rank_movies(rows, Constraints(moods=["温暖治愈"]))
    assert ranked[0][0].movie_id == "itunes:2"
    assert ranked[-1][0].movie_id == "itunes:1"
    assert rank_movies(rows, Constraints(sort_by="popular"))[0][0].movie_id == "itunes:1"


def test_balanced_shortlist_diversifies_genre_and_director():
    rows = [film(1, "动作", director="A"), film(2, "动作", director="A"),
            film(3, "喜剧", director="B"), film(4, "剧情", director="C")]
    assert [r[0].movie_id for r in rank_movies(rows, Constraints())[:3]] == ["itunes:1", "itunes:3", "itunes:4"]
    assert [r[0].movie_id for r in rank_movies(rows, Constraints(sort_by="popular"))[:3]] == ["itunes:1", "itunes:2", "itunes:3"]


def test_ranking_is_deterministic_and_does_not_mutate_metadata():
    rows = [film(1, "喜剧"), film(2, "剧情")]
    before = [r[0].model_dump() for r in rows]
    assert rank_movies(rows, Constraints()) == rank_movies(rows, Constraints())
    assert [r[0].model_dump() for r in rows] == before
