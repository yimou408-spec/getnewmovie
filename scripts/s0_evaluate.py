"""Score externally supplied responses against S0 contract and hard constraints.

This is an evaluation harness, not a recommendation implementation or user-value test.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from scripts.s0_contracts import RecommendationResponse


def evaluate(tasks, predictions):
    task_ids = {task["task_id"] for task in tasks}
    counts = Counter(prediction["task_id"] for prediction in predictions)
    duplicates = sorted(task_id for task_id, count in counts.items() if count > 1)
    missing = sorted(task_ids - counts.keys())
    extra = sorted(counts.keys() - task_ids)
    by_id = {item["task_id"]: item["response"] for item in predictions}
    results = []
    manual_pending = [{"task_id": task["task_id"], "checks": task["manual_checks"]}
                      for task in tasks if task.get("manual_checks")]
    for task in tasks:
        task_id = task["task_id"]
        if task_id not in by_id:
            results.append({"task_id": task_id, "violations": ["missing_prediction"]})
            continue
        violations = []
        try:
            response = RecommendationResponse.model_validate(by_id[task_id])
        except ValidationError:
            results.append({"task_id": task_id, "violations": ["contract_invalid"]})
            continue
        if response.status != task["expected_status"]:
            violations.append("status_mismatch")
        for card in response.candidates:
            movie = card.movie
            maximum = task.get("max_runtime_minutes")
            if maximum is not None and (movie.runtime_minutes is None or movie.runtime_minutes > maximum):
                violations.append("runtime_constraint")
            if movie.movie_id in task.get("exclude_movie_ids", []):
                violations.append("excluded_movie")
            allowed = task.get("allowed_movie_ids", [])
            if allowed and movie.movie_id not in allowed:
                violations.append("watchlist_scope")
            if not set(task.get("required_tags", [])).issubset(movie.tags):
                violations.append("required_tag_missing")
            if set(task.get("exclude_genres", [])) & set(movie.genres):
                violations.append("excluded_genre")
            if not all(item.region == task.get("region", "CN") for item in card.availability):
                violations.append("region_mismatch")
        results.append({"task_id": task_id, "violations": sorted(set(violations))})
    return {"task_count": len(tasks), "prediction_count": len(predictions),
            "missing_task_ids": missing, "duplicate_task_ids": duplicates, "extra_task_ids": extra,
            "passed": bool(tasks) and not (missing or duplicates or extra or any(r["violations"] for r in results)),
            "human_relevance": "not_measured", "spoiler_safety": "not_measured",
            "factual_truth": "not_measured", "manual_checks_pending": manual_pending, "results": results}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=root / "data/s0/eval_tasks.json")
    parser.add_argument("--predictions", type=Path, required=True, help="JSON array of {task_id,response}")
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument("--output", type=Path, default=root / "artifacts/s0/evaluation-report.json")
    args = parser.parse_args()
    tasks = [task for task in json.loads(args.tasks.read_text(encoding="utf-8")) if task["split"] == args.split]
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    report = evaluate(tasks, predictions)
    report["split"] = args.split
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "tasks": len(tasks), "report": str(args.output)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
