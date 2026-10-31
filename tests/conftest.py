"""Default regression tests never inherit a developer's live credentials or model."""
import pytest


@pytest.fixture(autouse=True)
def isolated_runtime_configuration(monkeypatch):
    for key in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "TMDB_READ_TOKEN", "MOVIE_MODEL_BACKEND"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("MOVIE_CATALOG_PROVIDER", "auto")
