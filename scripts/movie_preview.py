"""Serve the built UI and real catalog API from one origin.

Build first: cd web/app && npm ci && npm run build
Run from repository root: python -m uvicorn scripts.movie_preview:app --port 8000
Only web/app/dist is published; repository files and credentials are not served.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from scripts.movie_server import app as catalog_api

DIST = Path(__file__).resolve().parents[1] / "web" / "app" / "dist"

app = FastAPI(title="Tonight preview", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/api", catalog_api)
app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
