"""TMDB metadata for independently confirmed mappings; no ratings or plot text.

Non-commercial prototype usage with application attribution. The adapter accepts
only numeric provider IDs and never searches or promotes title/year matches.
"""
from datetime import datetime, timezone
import re
import unicodedata

import httpx

from app.services.budget import consume, current_budget
from scripts.s0_contracts import Evidence, SourceEvidenceResult


def metadata_text(value, limit=160):
    """Reject obvious links/markup/control characters in untrusted name fields."""
    if not isinstance(value, str):
        return None
    value = unicodedata.normalize("NFKC", value).strip()
    if (not value or len(value) > limit or re.search(
            r"https?://|www\.|[<>]|(?:[\w-]+\.)+(?:com|net|org|cn|xyz|top|site|info|cc|tv|io)\b",
            value, re.IGNORECASE) or any(unicodedata.category(c).startswith("C") for c in value)):
        return None
    return value


class TMDBSource:
    source = "TMDB"

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
        try:
            if self.client is None:
                with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                    response = self._get(client, external_id, timeout)
            else:
                response = self._get(self.client, external_id, timeout)
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
        if not isinstance(data, dict) or type(data.get("id")) is not int or data["id"] != int(external_id):
            return result("parse_error")
        title = metadata_text(data.get("title"))
        if title is None:
            return result("parse_error", warnings=["来源片名缺失或包含异常内容，未展示该来源资料。"])
        original = metadata_text(data.get("original_title"))
        date = data.get("release_date")
        year = date[:4] if isinstance(date, str) and re.fullmatch(r"(?:18|19|20|21)\d{2}-\d{2}-\d{2}", date) else "未知"
        runtime = data.get("runtime")
        runtime = runtime if type(runtime) is int and 1 <= runtime <= 600 else "未知"
        aliases = []
        group = data.get("alternative_titles")
        rows = group.get("titles", []) if isinstance(group, dict) else []
        for row in rows[:200] if isinstance(rows, list) else []:
            alias = metadata_text(row.get("title"), 80) if isinstance(row, dict) else None
            if alias and alias not in {title, original} and alias not in aliases:
                aliases.append(alias)
            if len(aliases) == 5:
                break
        claim = f"TMDB 中文片名：{title}；原名：{original or '未知'}；年份：{year}；时长：{runtime} 分钟。"
        if aliases:
            claim += "别名（最多5条）：" + "、".join(aliases) + "。"
        return result("ok", evidence=[Evidence(evidence_id=f"tmdb-metadata-{external_id}",
            movie_id=movie_id, source=self.source, url=f"https://www.themoviedb.org/movie/{external_id}",
            retrieved_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            kind="metadata", granularity="metadata", claim=claim, spoiler_level="safe",
            source_content_id=external_id, usage_basis="provider_terms")],
            warnings=["TMDB仅补充影片资料；未获取影评、独立口碑或地区播放渠道。"])

    def _get(self, client, external_id, timeout):
        return client.get(f"https://api.themoviedb.org/3/movie/{external_id}",
            params={"language": "zh-CN", "append_to_response": "alternative_titles"},
            headers={"Authorization": "Bearer " + self.token}, timeout=timeout, follow_redirects=False)
