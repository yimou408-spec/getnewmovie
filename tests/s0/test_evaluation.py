import copy
import json
from pathlib import Path

from scripts.s0_evaluate import evaluate

ROOT = Path(__file__).resolve().parents[2]


def fixture(name):
    return json.loads((ROOT / "contracts/examples" / f"{name}.json").read_text(encoding="utf-8"))


def task():
    return {"task_id": "test", "expected_status": "ready", "max_runtime_minutes": 100,
            "exclude_movie_ids": [], "allowed_movie_ids": [], "required_tags": ["轻松"]}


def test_evaluator_detects_unknown_duration_and_outside_watchlist():
    response = fixture("success")
    response["candidates"][0]["movie"]["runtime_minutes"] = None
    spec = task()
    spec["allowed_movie_ids"] = ["syn:other"]
    result = evaluate([spec], [{"task_id": "test", "response": response}])
    assert result["passed"] is False
    assert "runtime_constraint" in result["results"][0]["violations"]
    assert "watchlist_scope" in result["results"][0]["violations"]


def test_evaluator_does_not_count_missing_or_duplicate_predictions_as_success():
    spec = task()
    result = evaluate([spec], [])
    assert result["missing_task_ids"] == ["test"]
    assert not result["passed"]
    prediction = {"task_id": "test", "response": fixture("success")}
    result = evaluate([spec], [prediction, copy.deepcopy(prediction)])
    assert result["duplicate_task_ids"] == ["test"]
    assert not result["passed"]


def test_evaluator_passes_valid_synthetic_case_without_claiming_user_value():
    result = evaluate([task()], [{"task_id": "test", "response": fixture("success")}])
    assert result["passed"]
    assert result["human_relevance"] == "not_measured"
    assert result["spoiler_safety"] == "not_measured"
