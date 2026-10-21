"""Generate reviewable JSON schemas/OpenAPI from the same types the real API uses."""
import argparse
import json
from pathlib import Path

from scripts.s0_contracts import RecommendationRequest, RecommendationResponse, ErrorResponse, HealthResponse
from scripts.movie_server import app

ROOT = Path(__file__).resolve().parents[1]


def documents():
    return {
        "recommendation-request.schema.json": RecommendationRequest.model_json_schema(),
        "recommendation-response.schema.json": RecommendationResponse.model_json_schema(),
        "error-response.schema.json": ErrorResponse.model_json_schema(),
        "health-response.schema.json": HealthResponse.model_json_schema(),
        "openapi.json": app.openapi(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if generated contracts are stale")
    args = parser.parse_args()
    folder = ROOT / "contracts/generated"
    stale = []
    for name, content in documents().items():
        expected = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
        path = folder / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                stale.append(name)
        else:
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
    if stale:
        parser.exit(1, "Stale contracts: " + ", ".join(stale) + "\n")
    print("Contract check passed" if args.check else f"Exported {len(documents())} contract files")


if __name__ == "__main__":
    main()
