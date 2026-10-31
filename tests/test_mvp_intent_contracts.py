"""Offline acceptance specifications, not a claim that the Agent is implemented."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.mvp_intent_contracts import IntentDecision, load_cases

ROOT = Path(__file__).resolve().parents[1]


def test_all_nine_approved_cases_have_valid_requests_and_expected_outputs():
    cases = load_cases(ROOT / "contracts/mvp/intent-cases.json")
    assert [case.case_id for case in cases] == [f"E{i:02}" for i in range(1, 10)]
    assert all(case.request.memory_enabled is False for case in cases)


def test_refinement_updates_only_mentioned_fields_and_reset_clears_explicitly():
    cases = {c.case_id: c for c in load_cases(ROOT / "contracts/mvp/intent-cases.json")}
    refine = cases["E05"]
    assert refine.expected_intent.updates.model_dump(exclude_unset=True) == {"max_runtime_minutes": 90}
    assert refine.expected_constraints.genres == ["喜剧"]
    assert refine.expected_constraints.exclude_genres == ["恐怖"]
    assert cases["E08"].expected_intent.action == "reset"
    assert cases["E08"].expected_constraints.exclude_movie_ids == []


def test_conflict_and_unsupported_require_confirmation_not_recommendation():
    cases = {c.case_id: c for c in load_cases(ROOT / "contracts/mvp/intent-cases.json")}
    for case_id in ("E03", "E04"):
        case = cases[case_id]
        assert case.expected_intent.needs_confirmation
        assert case.response.status == "needs_clarification"
        assert not case.response.candidates
    assert not cases["E02"].expected_intent.needs_confirmation


def test_model_decision_rejects_fabricated_movies_and_invalid_actions():
    with pytest.raises(ValidationError):
        IntentDecision.model_validate({"action": "recommend", "movies": ["编造的影片"]})
    with pytest.raises(ValidationError):
        IntentDecision.model_validate({"action": "save_long_term_preference"})


def test_sample_checker_rejects_inconsistent_effective_conditions(tmp_path):
    source = ROOT / "contracts/mvp/intent-cases.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    data["cases"][4]["expected_constraints"]["max_runtime_minutes"] = 120
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="E05"):
        load_cases(broken)
