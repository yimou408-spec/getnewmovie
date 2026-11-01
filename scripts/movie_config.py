"""Rooted local configuration. Reports contain presence/state, never credentials."""
from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from scripts.s0_contracts import IntegrationState, RuntimeConfiguration

ROOT = Path(__file__).resolve().parents[1]
LOCAL_MODEL = "qwen2.5-1.5b-instruct-q4_k_m"
LOCAL_BASE_URL = "http://127.0.0.1:18181/v1"


def is_local_endpoint(value):
    try:
        url = urlsplit(value)
        return (url.scheme == "http" and url.hostname in ("127.0.0.1", "::1")
                and bool(url.port) and not any((url.username, url.password, url.query, url.fragment)))
    except ValueError:
        return False


def valid_model_endpoint(value):
    try:
        url = urlsplit(value)
        return is_local_endpoint(value) or (url.scheme == "https" and bool(url.hostname)
            and not any((url.username, url.password, url.query, url.fragment)))
    except ValueError:
        return False


@dataclass(frozen=True)
class Settings:
    llm_base_url: str = field(default="", repr=False)
    llm_model: str = ""
    llm_api_key: str = field(default="", repr=False)
    tmdb_read_token: str = field(default="", repr=False)
    catalog_provider: str = "auto"

    @classmethod
    def load(cls, path=None, environ=None):
        values = dict(dotenv_values(path or ROOT / ".env", encoding="utf-8-sig", interpolate=False))
        values.update(os.environ if environ is None else environ)
        def get(key, default=""):
            return str(values.get(key) or default).strip()
        base, model, key = get("LLM_BASE_URL"), get("LLM_MODEL"), get("LLM_API_KEY")
        if get("MOVIE_MODEL_BACKEND") == "local" and not any((base, model, key)):
            base, model = LOCAL_BASE_URL, LOCAL_MODEL
        return cls(base, model, key,
                   get("TMDB_READ_TOKEN"), get("MOVIE_CATALOG_PROVIDER", "auto").lower())

    @property
    def is_local_model(self):
        return is_local_endpoint(self.llm_base_url)

    @property
    def provider(self):
        if self.catalog_provider not in ("auto", "apple", "tmdb"):
            raise ValueError("MOVIE_CATALOG_PROVIDER must be auto, apple or tmdb")
        return ("tmdb" if self.tmdb_read_token else "apple") if self.catalog_provider == "auto" else self.catalog_provider

    def report(self):
        keys = ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")
        values = (self.llm_base_url, self.llm_model, self.llm_api_key)
        missing = [key for key, value in zip(keys, values) if not value
                   and not (self.is_local_model and key == "LLM_API_KEY")]
        state = "not_configured" if len(missing) == 3 else "incomplete" if missing else "configured"
        if self.llm_base_url and not valid_model_endpoint(self.llm_base_url):
            state = "invalid"
        if any("\n" in v or "\r" in v for v in values):
            state = "invalid"
        tmdb_state = "configured" if self.tmdb_read_token else "not_configured"
        if any(c in self.tmdb_read_token for c in "\r\n"):
            tmdb_state = "invalid"
        return RuntimeConfiguration(catalog_provider=self.provider,
            llm=IntegrationState(state=state, missing=missing, live_verified=False),
            tmdb=IntegrationState(state=tmdb_state, missing=[] if self.tmdb_read_token else ["TMDB_READ_TOKEN"], live_verified=False),
            intent_method="llm-v1" if state == "configured" else "rules-v1",
            model_location="local" if self.is_local_model else "remote" if any(values) else "rules",
            model_name=self.llm_model or None)
