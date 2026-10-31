"""Small, bounded public-page adapter. No login, challenge bypass, or retries.

Successful parsing establishes availability only, not publication permission.
Search matches are candidates. Call fetch only for an independently confirmed
external ID; the probe uses it solely to investigate candidate availability.
"""
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from scripts.s0_contracts import Evidence, Rating, SourceEvidenceResult
from app.services.budget import consume

BASE_URL = "https://movie.douban.com"
SOURCE = "Douban"


def normalized(value):
    return "".join(char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum())


@dataclass
class IdentityMatch:
    status: str
    subject_id: str | None = None
    candidates: list[dict] = field(default_factory=list)


def select_identity(payload, aliases, year):
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        return IdentityMatch("parse_error")
    names = {normalized(name) for name in aliases if normalized(name)}
    candidates = {}
    for item in payload:
        mid = str(item.get("id", ""))
        if item.get("type") != "movie" or not re.fullmatch(r"[1-9][0-9]*", mid):
            continue
        if not names.intersection({normalized(str(item.get(key, ""))) for key in ("title", "sub_title")}):
            continue
        item_year = str(item.get("year", ""))
        if not re.fullmatch(r"\d{4}", item_year) or (year is not None and item_year != str(year)):
            continue
        candidates[mid] = {"subject_id": mid, "title": str(item.get("title", "")),
                           "original_title": str(item.get("sub_title", "")), "year": int(item_year)}
    rows = list(candidates.values())
    if not rows:
        return IdentityMatch("no_results")
    if len(rows) != 1 or year is None:
        return IdentityMatch("ambiguous", candidates=rows)
    return IdentityMatch("candidate", rows[0]["subject_id"], rows)


@dataclass
class Observation:
    path: str
    status: str
    http_status: int | None = None
    elapsed_ms: int = 0
    byte_count: int = 0
    redirect_host: str | None = None
    redirect_path: str | None = None

    def as_dict(self):
        return asdict(self)


class PageParser(HTMLParser):
    """Extract JSON-LD and visible short-comment blocks, keeping text in memory."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.json_ld, self.comments = [], [], []
        self.script, self.script_text = False, []
        self.comment = None
        self.capture, self.capture_depth = None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"meta", "link", "img", "br", "input", "hr", "source", "wbr"}:
            return
        self.stack.append(tag)
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.script, self.script_text = True, []
        classes = attrs.get("class", "").split()
        if "comment-item" in classes:
            self.comment = {"id": attrs.get("data-cid"), "text": [], "author": [], "depth": len(self.stack)}
        if self.comment is not None and ("short" in classes or tag == "a" and "/people/" in attrs.get("href", "")):
            self.capture = "text" if "short" in classes else "author"
            self.capture_depth = len(self.stack)

    def handle_endtag(self, tag):
        if self.script and tag == "script":
            try:
                value = json.loads("".join(self.script_text))
                self.json_ld.extend(value if isinstance(value, list) else [value])
            except ValueError:
                pass
            self.script = False
        if self.capture_depth == len(self.stack):
            self.capture, self.capture_depth = None, None
        if self.comment is not None and self.comment["depth"] == len(self.stack):
            self.comments.append(self.comment)
            self.comment = None
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if self.script:
            self.script_text.append(data)
        if self.comment is not None and self.capture:
            self.comment[self.capture].append(data)


class DoubanAdapter:
    source = SOURCE
    def __init__(self, client, max_requests=9):
        if not 1 <= max_requests <= 30:
            raise ValueError("request budget must be 1..30")
        self.client, self.max_requests, self.calls = client, max_requests, 0
        self.observations = []

    def get(self, path, params=None):
        if not re.fullmatch(r"/j/subject_suggest|/subject/[1-9][0-9]*/(?:comments/)?", path):
            raise ValueError("unsupported Douban path")
        if self.calls >= self.max_requests:
            return None, "budget_exhausted"
        timeout = consume(search=path == "/j/subject_suggest", timeout=self.client.timeout.read or 8)
        self.calls += 1
        started = time.perf_counter()
        status, response, host, redirect_path = "upstream_error", None, None, None
        try:
            response = self.client.get(BASE_URL + path, params=params, follow_redirects=False, timeout=timeout)
            code = response.status_code
            if response.is_redirect:
                location = urlparse(response.headers.get("location", ""))
                host = location.hostname
                redirect_path = location.path if host in {"movie.douban.com", "sec.douban.com", "accounts.douban.com", "www.douban.com"} else None
                status = "access_limited"
            elif code in {401, 403, 418, 429}:
                status = "access_limited"
            elif code == 404:
                status = "no_results"
            elif code == 200:
                content = response.text[:200_000].lower()
                status = "access_limited" if any(mark in content for mark in ("<title>安全验证", "<title>登录豆瓣", "captcha", "sec.douban.com")) else "ok"
        except httpx.TimeoutException:
            status = "timeout"
        except httpx.HTTPError:
            status = "upstream_error"
        self.observations.append(Observation(path=path, status=status,
            http_status=response.status_code if response is not None else None,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            byte_count=len(response.content) if response is not None else 0,
            redirect_host=host, redirect_path=redirect_path))
        return response, status

    def search(self, aliases, year):
        if not aliases or not aliases[0].strip():
            raise ValueError("a movie title is required")
        response, status = self.get("/j/subject_suggest", {"q": aliases[0]})
        if status != "ok":
            return IdentityMatch(status)
        try:
            return select_identity(response.json(), aliases, year)
        except ValueError:
            return IdentityMatch("parse_error")

    def fetch(self, movie_id, subject_id):
        if not re.fullmatch(r"[1-9][0-9]*", subject_id):
            raise ValueError("invalid subject ID")
        evidence, ratings, statuses = [], [], []
        for suffix in ("", "comments/"):
            url = f"{BASE_URL}/subject/{subject_id}/{suffix}"
            response, status = self.get(f"/subject/{subject_id}/{suffix}",
                {"limit": 20, "status": "P", "sort": "new_score"} if suffix else None)
            if status == "ok":
                page = PageParser()
                try:
                    page.feed(response.text[:1_000_000])
                except (ValueError, RecursionError):
                    statuses.append("parse_error")
                    continue
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                count = len(evidence)
                if not suffix:
                    for data in page.json_ld:
                        if not isinstance(data, dict) or data.get("@type") != "Movie":
                            continue
                        if data.get("url") != f"{BASE_URL}/subject/{subject_id}/":
                            continue
                        group = data.get("aggregateRating")
                        if not isinstance(group, dict):
                            continue
                        try:
                            eid = f"douban-{subject_id}-rating"
                            rating = Rating(source=SOURCE, value=group["ratingValue"], scale=group["bestRating"],
                                            vote_count=group.get("ratingCount"), evidence_id=eid)
                        except (ValueError, KeyError):
                            continue
                        ratings.append(rating)
                        evidence.append(Evidence(evidence_id=eid, movie_id=movie_id, source=SOURCE, url=url,
                            retrieved_at=stamp, kind="rating", granularity="rating",
                            claim=f"{rating.value}/{rating.scale}", spoiler_level="safe",
                            source_content_id=subject_id, usage_basis="unverified"))
                        break
                else:
                    seen = set()
                    for comment in page.comments[:20]:
                        cid, text = comment["id"], "".join(comment["text"]).strip()
                        if not cid or not re.fullmatch(r"[1-9][0-9]*", cid) or not text or cid in seen:
                            continue
                        seen.add(cid)
                        evidence.append(Evidence(evidence_id=f"douban-{subject_id}-comment-{cid}", movie_id=movie_id,
                            source=SOURCE, url=f"{url}#comment-{cid}", retrieved_at=stamp,
                            kind="review", granularity="excerpt", claim=text[:1000], spoiler_level="unknown",
                            author="".join(comment["author"]).strip()[:160] or None,
                            source_content_id=cid, usage_basis="unverified"))
                status = "ok" if len(evidence) > count else "parse_error"
                if suffix and not page.comments and "还没有人写过短评" in response.text:
                    status = "no_results"
            statuses.append(status)
        final = "ok" if evidence else "no_results"
        if not evidence:
            final = next((s for s in ("budget_exhausted", "access_limited", "timeout", "upstream_error", "parse_error") if s in statuses), "no_results")
        warnings = [f"{('subject', 'comments')[i]}:{s}" for i, s in enumerate(statuses) if s != "ok"]
        warnings.append("Content use permission is unverified; review text is not safe for default preview.")
        return SourceEvidenceResult(movie_id=movie_id, source=SOURCE, status=final,
                                    evidence=evidence, ratings=ratings, warnings=warnings)
