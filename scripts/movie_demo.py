"""Build and serve the local demo on one loopback port, without embedded keys."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import webbrowser
from contextlib import contextmanager, ExitStack

import httpx

from scripts.movie_config import ROOT, Settings, LOCAL_BASE_URL, LOCAL_MODEL

TEMPLATE = """# Local only. Default: keyless Apple catalog + local Qwen model.
# auto chooses TMDB only when TMDB_READ_TOKEN is present. apple/tmdb also supported.
MOVIE_CATALOG_PROVIDER=auto
TMDB_READ_TOKEN=
# local uses the project-owned Qwen runtime; cloud fields below remain optional.
MOVIE_MODEL_BACKEND=local
# OpenAI-compatible HTTPS Chat Completions endpoint, model and API key from your provider.
LLM_BASE_URL=
LLM_MODEL=
LLM_API_KEY=
"""


@contextmanager
def optional_local_runtime(settings):
    from scripts.movie_local import LocalRuntime, install, installed
    with ExitStack() as resources:
        if settings.llm_base_url == LOCAL_BASE_URL and settings.llm_model == LOCAL_MODEL:
            try:
                if not installed():
                    install()
                resources.enter_context(LocalRuntime())
            except (RuntimeError, OSError, httpx.HTTPError) as error:
                print(f"Local model unavailable ({type(error).__name__}); starting the frontend with automatic rule fallback.", flush=True)
        yield


def build_frontend(folder):
    """Reinstall on lock changes, including a teammate's subsequent git pull."""
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("Node.js/npm is missing. Use start-demo.cmd on Windows.")
    fingerprint = hashlib.sha256((folder / "package-lock.json").read_bytes()).hexdigest()
    stamp = folder / "node_modules/.movie-lock.sha256"
    if not stamp.is_file() or stamp.read_text(encoding="ascii").strip() != fingerprint:
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=folder, check=True)
        stamp.write_text(fingerprint, encoding="ascii")
    subprocess.run([npm, "run", "build"], cwd=folder, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="Print redacted setup states only; no network")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    try:
        with (ROOT / ".env").open("x", encoding="utf-8") as handle:
            handle.write(TEMPLATE)
    except FileExistsError:
        pass
    settings = Settings.load()
    report = settings.report()
    if args.check:
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
        return 0
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", args.port)) == 0:
            print(f"Port {args.port} is already in use. Existing services were preserved. Use --port with another port.")
            return 2
    folder = ROOT / "web/app"
    if not args.no_build:
        try:
            build_frontend(folder)
        except (RuntimeError, subprocess.CalledProcessError) as error:
            print(f"Frontend build failed ({type(error).__name__}); the server was not started.")
            return 1
    if not (folder / "dist/index.html").is_file():
        print("Frontend build is missing. Run without --no-build.")
        return 2
    import uvicorn
    from scripts.movie_server import create_app
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Local demo: {url}  Setup: {url}setup")
    print(f"Catalog: {report.catalog_provider}; text parser: {report.intent_method}. Configuration does not establish live verification.")
    print("Keep this terminal open. Press Ctrl+C to stop this demo.")
    with optional_local_runtime(settings):
        if not args.no_browser:
            timer = threading.Timer(1.5, webbrowser.open, args=(url,))
            timer.daemon = True
            timer.start()
        uvicorn.run(create_app(settings=settings), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
