"""Serve the built UI and real catalog API from one origin.

Build first: cd web/app && npm ci && npm run build
Run from repository root: python -m uvicorn scripts.movie_preview:app --port 8000
Only web/app/dist is published; repository files and credentials are not served.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from scripts.movie_server import app as catalog_api

DIST = Path(__file__).resolve().parents[1] / "web" / "app" / "dist"


class FrontendFiles(StaticFiles):
    """Allow client-side routes to survive refresh without hiding missing assets."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or Path(path).suffix or scope["method"] not in {"GET", "HEAD"}:
                raise
            return await super().get_response("index.html", scope)


app = FastAPI(title="Tonight preview", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/api", catalog_api)
app.mount("/", FrontendFiles(directory=DIST, html=True), name="frontend")
