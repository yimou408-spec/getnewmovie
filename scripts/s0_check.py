"""Run the offline S0 gate, without external service keys or HTTP calls."""
import json
import subprocess
import sys
from pathlib import Path

from scripts.s0_contracts import ErrorResponse, HealthResponse, Movie, RecommendationRequest, RecommendationResponse

ROOT = Path(__file__).resolve().parents[1]


def check_data():
    folder = ROOT / "contracts/examples"
    for path in folder.glob("*.json"):
        models = {"request": RecommendationRequest, "health": HealthResponse,
                  "timeout": ErrorResponse, "unconfigured": ErrorResponse}
        model = models.get(path.stem, RecommendationResponse)
        model.model_validate_json(path.read_text(encoding="utf-8"))
    tasks = json.loads((ROOT / "data/s0/eval_tasks.json").read_text(encoding="utf-8"))
    if len(tasks) != 30 or len({task["task_id"] for task in tasks}) != 30:
        raise ValueError("Expected 30 unique evaluation tasks")
    if sum(t["split"] == "dev" for t in tasks) != 20 or sum(t["split"] == "holdout" for t in tasks) != 10:
        raise ValueError("Expected 20 dev / 10 holdout tasks")
    if any(task["provenance"] != "synthetic" for task in tasks):
        raise ValueError("Evaluation provenance must remain synthetic")
    movies = [Movie.model_validate(m) for m in json.loads((ROOT / "data/s0/synthetic_catalog.json").read_text(encoding="utf-8"))]
    if len({movie.movie_id for movie in movies}) != len(movies):
        raise ValueError("Duplicate synthetic movie ID")
    samples = json.loads((ROOT / "data/s0/tmdb_samples.json").read_text(encoding="utf-8"))
    if len(samples) != 30 or len({s["sample_id"] for s in samples}) != 30:
        raise ValueError("Expected 30 unique TMDB query seeds")
    print("PASS: examples, catalog and 30+30 task/query seeds", flush=True)


def main():
    check_data()
    for command in ([sys.executable, "-m", "scripts.s0_export_contracts", "--check"],
                    [sys.executable, "-m", "pytest", "-q"]):
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    print("S0 offline gate passed; live feasibility and human review remain pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
