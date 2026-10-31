"""Project-owned, loopback-only Qwen runtime. No accounts or cloud API keys."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from threading import Event
import zipfile

import httpx

from scripts.movie_config import ROOT, LOCAL_BASE_URL, LOCAL_MODEL

HOME = ROOT / "artifacts/local-model"
MODEL_SHA = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
MODEL_SIZE = 1117320736
RUNTIME_SHA = "07e81782f5a16c7ffef42403183808e02f271c9ece3aa2d64040b2620ae8d519"
RUNTIME_SIZE = 24574627
MODEL_URL = ("https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/"
             "91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf")
RUNTIME_URL = "https://api.github.com/repos/ggml-org/llama.cpp/releases/assets/694792300"


def checksum(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def download(url, target, size, expected):
    """Bounded, resumable ranges also work with proxies that stall large responses."""
    if target.is_file() and target.stat().st_size == size and checksum(target) == expected:
        return
    pieces = HOME / (target.name + ".parts")
    pieces.mkdir(parents=True, exist_ok=True)
    chunk_size = 4 * 1024 * 1024
    count = (size + chunk_size - 1) // chunk_size
    cancelled = Event()
    # Resolve the signed asset URL once. Repeating the origin redirect for every
    # megabyte adds TLS handshakes and fails frequently on some local proxies.
    with httpx.Client(trust_env=False, proxy=os.getenv("MOVIE_DOWNLOAD_PROXY") or None,
                      timeout=20, follow_redirects=True) as resolver:
        with resolver.stream("GET", url, headers={"Range": "bytes=0-0", "Accept": "application/octet-stream"}) as response:
            response.raise_for_status()
            asset_url = str(response.url)
    def piece(index):
        start, end = index * chunk_size, min((index + 1) * chunk_size, size) - 1
        path = pieces / f"{index:04d}"
        if path.is_file() and path.stat().st_size == end - start + 1:
            return index
        with httpx.Client(trust_env=False, proxy=os.getenv("MOVIE_DOWNLOAD_PROXY") or None,
                          timeout=httpx.Timeout(20, connect=15), follow_redirects=True) as client:
            temporary = path.with_suffix(".partial")
            with temporary.open("wb") as output:
                for sub_start in range(start, end + 1, 1024 * 1024):
                    if cancelled.is_set():
                        raise RuntimeError("Download cancelled after a failed part")
                    sub_end = min(sub_start + 1024 * 1024 - 1, end)
                    for attempt in range(6):
                        started = time.monotonic()
                        data = bytearray()
                        try:
                            with client.stream("GET", asset_url, headers={"Range": f"bytes={sub_start}-{sub_end}",
                                    "Accept-Encoding": "identity", "Accept": "application/octet-stream"}) as response:
                                response.raise_for_status()
                                if response.status_code != 206 or response.headers.get("content-range") != f"bytes {sub_start}-{sub_end}/{size}":
                                    raise RuntimeError("Download range could not be verified")
                                for block in response.iter_bytes(16384):
                                    if time.monotonic() - started > 45:
                                        raise httpx.ReadTimeout("Download range exceeded its time budget")
                                    data.extend(block)
                                if len(data) != sub_end - sub_start + 1:
                                    raise httpx.ReadError("Download range was incomplete")
                            output.write(data)
                            break
                        except httpx.TransportError:
                            if attempt == 5:
                                raise
                            time.sleep(min(2 ** attempt, 8))
            temporary.replace(path)
        return index
    with ThreadPoolExecutor(max_workers=8) as pool:
        completed = 0
        futures = [pool.submit(piece, i) for i in range(count)]
        try:
            for future in as_completed(futures):
                future.result()
                completed += 1
                if completed % 8 == 0 or completed == count:
                    print(f"{target.name}: {completed}/{count} parts", flush=True)
        except BaseException:
            cancelled.set()
            for future in futures:
                future.cancel()
            raise
    temporary = target.with_suffix(target.suffix + ".verified-part")
    with temporary.open("wb") as output:
        for i in range(count):
            with (pieces / f"{i:04d}").open("rb") as source:
                while data := source.read(1024 * 1024):
                    output.write(data)
    if checksum(temporary) != expected:
        raise RuntimeError("Download SHA256 mismatch; the file will not be executed")
    temporary.replace(target)
    print(f"{target.name}: SHA256 verified", flush=True)


def installed():
    return ((HOME / "runtime/llama-server.exe").is_file()
            and (HOME / f"{LOCAL_MODEL}.gguf").is_file()
            and (HOME / f"{LOCAL_MODEL}.gguf").stat().st_size == MODEL_SIZE
            and (HOME / "installation.json").is_file())


def install():
    HOME.mkdir(parents=True, exist_ok=True)
    print("Installing local Qwen (about 1.1 GB); files stay inside this project.", flush=True)
    download(RUNTIME_URL, HOME / "runtime.zip", RUNTIME_SIZE, RUNTIME_SHA)
    download(MODEL_URL, HOME / f"{LOCAL_MODEL}.gguf", MODEL_SIZE, MODEL_SHA)
    destination = HOME / "runtime"
    with zipfile.ZipFile(HOME / "runtime.zip") as archive:
        if any(not (destination / entry.filename).resolve().is_relative_to(destination.resolve()) for entry in archive.infolist()):
            raise RuntimeError("Unsafe archive path")
        archive.extractall(destination)
    if not (destination / "llama-server.exe").is_file():
        raise RuntimeError("Official archive did not contain llama-server.exe")
    (HOME / "installation.json").write_text(json.dumps({"model": LOCAL_MODEL,
        "model_sha256": MODEL_SHA, "runtime": "llama.cpp b12020", "runtime_sha256": RUNTIME_SHA,
        "model_license": "Apache-2.0", "runtime_license": "MIT"}, indent=2), encoding="utf-8")


def enable_local_mode():
    from dotenv import dotenv_values, set_key
    path = ROOT / ".env"
    values = dotenv_values(path, interpolate=False)
    if any(values.get(k) for k in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")):
        raise RuntimeError("Existing cloud model selection was preserved; local mode was not enabled")
    set_key(path, "MOVIE_MODEL_BACKEND", "local")


class LocalRuntime:
    """Stop only a child created here; an existing matching server is reused."""
    def __init__(self):
        self.process = None
        self.log = None

    def ready(self):
        try:
            with httpx.Client(trust_env=False, timeout=2) as client:
                response = client.get(LOCAL_BASE_URL + "/models")
                return response.status_code == 200 and any(m.get("id") == LOCAL_MODEL for m in response.json().get("data", []))
        except (httpx.HTTPError, ValueError, TypeError):
            return False

    def __enter__(self):
        if self.ready():
            return self
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", 18181)) == 0:
                raise RuntimeError("Port 18181 belongs to another service; it was preserved")
        if not installed():
            raise RuntimeError("Local model is not installed; run python -m scripts.movie_local --install")
        self.log = (HOME / "server.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen([str(HOME / "runtime/llama-server.exe"), "-m", str(HOME / f"{LOCAL_MODEL}.gguf"),
            "--host", "127.0.0.1", "--port", "18181", "--alias", LOCAL_MODEL,
            "--ctx-size", "4096", "--parallel", "1", "--threads", "12", "--n-predict", "512",
            "--no-webui"], stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("Local model process exited; see artifacts/local-model/server.log")
                if self.ready():
                    print(f"Local model ready: {LOCAL_MODEL}", flush=True)
                    return self
                time.sleep(0.5)
            raise RuntimeError("Local model startup timed out")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--enable", action="store_true")
    args = parser.parse_args()
    if args.install:
        install()
    if args.enable:
        enable_local_mode()
    if not args.install and not args.enable:
        with LocalRuntime():
            print("Loopback model ready. Ctrl+C stops this instance.", flush=True)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
