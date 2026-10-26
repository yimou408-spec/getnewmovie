"""Core MVP recommendation behavior; all films are offline test doubles."""
import pytest

from scripts.mvp_intent_contracts import IntentDecision, ROOT, load_cases
from scripts.mvp_recommendation_rules import merge_conditions, select_movies
from scripts.s0_contracts import Constraints, Movie


@pytest.mark.parametrize("case", load_cases(ROOT / "contracts/mvp/intent-cases.json"), ids=lambda c: c.case_id)
def test_approved_cases_merge_into_expected_conditions(case):
    resolution = merge_conditions(case.expected_intent, previous=case.context.previous_constraints,
                                  selected=case.request.constraints, displayed=case.context.displayed_movie_ids)
    assert resolution.constraints == case.expected_constraints
    assert resolution.needs_confirmation == case.expected_intent.needs_confirmation


def film(mid, runtime=80, genre="喜剧", year=2024):
    return (Movie(movie_id=f"itunes:{mid}", title=f"Offline {mid}", genres=[genre],
                  runtime_minutes=runtime, year=year), "2026-10-26T00:00:00Z")


def test_followup_preserves_conditions_and_original_objects():
    original = Constraints(genres=["喜剧"], max_runtime_minutes=120, exclude_genres=["恐怖"])
    result = merge_conditions(IntentDecision(action="refine", updates={"max_runtime_minutes": 90}), previous=original)
    assert result.constraints.max_runtime_minutes == 90
    assert result.constraints.genres == ["喜剧"]
    assert result.constraints.exclude_genres == ["恐怖"]
    assert original.max_runtime_minutes == 120
    assert not result.needs_confirmation


def test_same_turn_picks_and_text_conflict_require_confirmation():
    result = merge_conditions(IntentDecision(updates={"genres": ["剧情"]}), selected=Constraints(genres=["喜剧"]))
    assert result.needs_confirmation
    result = merge_conditions(IntentDecision(updates={"genres": ["恐怖"], "exclude_genres": ["恐怖"]}))
    assert result.needs_confirmation


def test_reroll_preserves_dismissed_ids_and_deduplicates_displayed_ids():
    previous = Constraints(genres=["喜剧"], max_runtime_minutes=90, exclude_movie_ids=["itunes:1"])
    result = merge_conditions(IntentDecision(action="reroll"), previous=previous,
                              displayed=["itunes:1", "itunes:2", "itunes:2"])
    assert result.constraints.exclude_movie_ids == ["itunes:1", "itunes:2"]
    assert result.constraints.genres == ["喜剧"]
    assert result.constraints.max_runtime_minutes == 90


def test_hard_filters_are_applied_before_ranking_without_filling_results():
    rows = [film(1, 90), film(2, 91), film(3, None), film(4, 80, "恐怖"), film(5), film(6, 80, "剧情")]
    selected = select_movies(rows, Constraints(genres=["喜剧"], max_runtime_minutes=90,
                                              exclude_movie_ids=["itunes:5"], exclude_genres=["恐怖"]))
    assert [r[0].movie_id for r in selected.eligible] == ["itunes:1"]
    assert [r[0].movie_id for r in selected.candidates] == ["itunes:1"]
    assert select_movies(rows, Constraints(max_runtime_minutes=10)).candidates == []


def test_shortlist_is_at_most_three_and_duplicate_ids_are_not_recommended_twice():
    selected = select_movies([film(1), film(1), film(2), film(3), film(4)], Constraints(sort_by="popular"))
    assert len(selected.eligible) == 4
    assert [r[0].movie_id for r in selected.candidates] == ["itunes:1", "itunes:2", "itunes:3"]


def test_year_filter_and_family_filter_reuse_existing_meaning():
    selected = select_movies([film(1, year=2024), film(2, year=1999), film(3, year=None)], Constraints(era="recent"), current_year=2026)
    assert [r[0].movie_id for r in selected.candidates] == ["itunes:1"]
    selected = select_movies([film(1), film(2, genre="家庭")], Constraints(company="和家人"))
    assert [r[0].movie_id for r in selected.candidates] == ["itunes:2"]
