"""Opt-in English review excerpts under TMDB's non-commercial API terms.

Only confirmed work IDs; one page, one request, at most three excerpts. Authors
and original links are retained. Originality and spoilers are not inferred.
"""
from datetime import datetime, timezone
import re
import unicodedata

import httpx

from app.services.budget import consume, current_budget
from scripts.s0_contracts import Evidence, SourceEvidenceResult
from scripts.tmdb_adapter import metadata_text


class TMDBReviewSource:
    source = "TMDB Reviews"
    provides_reviews = True
    identity_provider = "tmdb"

    def __init__(self, token, *, client=None):
        self.token, self.client = token.strip(), client

    def fetch(self, movie_id, external_id):
        if not re.fullmatch(r"[1-9][0-9]*", external_id):
            raise ValueError("invalid TMDB ID")
        def result(status, **extra):
            return SourceEvidenceResult(movie_id=movie_id, source=self.source, status=status, **extra)
        if not self.token:
            return result("not_configured")
        timeout = consume(timeout=8)
        def get(client):
            return client.get(f"https://api.themoviedb.org/3/movie/{external_id}/reviews",
                params={"language": "en-US", "page": 1},
                headers={"Authorization": "Bearer " + self.token}, timeout=timeout, follow_redirects=False)
        try:
            if self.client is None:
                with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                    response = get(client)
            else:
                response = get(self.client)
            if current_budget.get():
                current_budget.get().check()
        except httpx.TimeoutException:
            return result("timeout")
        except httpx.HTTPError:
            return result("upstream_error")
        if response.status_code != 200:
            status = {401: "not_configured", 403: "access_limited", 404: "no_results",
                      429: "access_limited"}.get(response.status_code, "upstream_error")
            return result("access_limited" if response.is_redirect else status)
        try:
            data = response.json()
        except ValueError:
            return result("parse_error")
        if (not isinstance(data, dict) or type(data.get("id")) is not int
                or data["id"] != int(external_id) or not isinstance(data.get("results"), list)):
            return result("parse_error")
        evidence, seen = [], set()
        for row in data["results"][:20]:
            if not isinstance(row, dict):
                continue
            rid = row.get("id")
            if not isinstance(rid, str) or not re.fullmatch(r"[a-f0-9]{24}", rid) or rid in seen:
                continue
            url = f"https://www.themoviedb.org/review/{rid}"
            author = metadata_text(row.get("author"))
            content = row.get("content")
            if row.get("url") != url or not author or not isinstance(content, str):
                continue
            content = unicodedata.normalize("NFKC", content)
            # Keep plain source text only; do not silently strip links/markup
            # from a syndicated review and relabel it as an original opinion.
            if (not content.strip() or len(content) > 100_000
                    or re.search(r"https?://|www\.|[<>]", content, re.IGNORECASE)
                    or any(unicodedata.category(c).startswith("C") and c not in "\r\n\t" for c in content)):
                continue
            claim = " ".join(content.split())[:600]
            seen.add(rid)
            evidence.append(Evidence(evidence_id=f"tmdb-review-{external_id}-{rid}",
                movie_id=movie_id, source=self.source, url=url,
                retrieved_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                kind="review", granularity="excerpt", claim=claim, author=author,
                source_content_id=rid, spoiler_level="unknown", usage_basis="provider_terms"))
            if len(evidence) == 3:
                break
        return result("ok" if evidence else "parse_error" if data["results"] else "no_results",
            evidence=evidence, warnings=[
                "英文影评首屏，最多3条、每条最多600字符；非全量口碑。剧透与作者独立性未核验，不作为默认推荐理由。",
                "仅用于有TMDB署名的非商业原型；保留作者和原文链接，不表示已获商业转载授权。"])
