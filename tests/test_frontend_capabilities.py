"""P01 additive service declaration; this does not probe the upstream provider."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from scripts.movie_server import create_app


def test_health_declares_metadata_separately_from_reputation_without_network():
    class NoNetworkCatalog:
        pass

    with TestClient(create_app(NoNetworkCatalog())) as client:
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "real-catalog"
    assert data["provider"] == "Apple iTunes US"
    assert data["synthetic_fallback"] is False
    assert data == json.loads((Path(__file__).resolve().parents[1] / "contracts/examples/health.json").read_text(encoding="utf-8"))
    assert data["capabilities"] == {
        "metadata": True,
        "ratings": False,
        "reviews": False,
        "natural_language": True,
        "model_understanding": False,
        "long_term_memory": False,
        "local_availability": False,
    }
