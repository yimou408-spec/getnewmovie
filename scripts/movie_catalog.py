"""Keyless Apple US movie charts + lookup metadata. No synthetic fallback.

RSS duration is a trailer length. Only lookup trackTimeMillis is used for films.
Mood matching uses local genre and synopsis clues, not provider sentiment.
"""
import math
import os
import re
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone
from threading import RLock
from urllib.parse import urlparse

import httpx
from pydantic import HttpUrl

from scripts.s0_contracts import Movie
from scripts.movie_ranking import content_clues

GENRES = {"喜剧": "4404", "科幻与奇幻": "4413", "惊悚": "4416", "动作": "4401",
          "爱情": "4412", "动画": "4402", "剧情": "4406", "家庭": "4410", "纪录片": "4405", "恐怖": "4408"}
ENGLISH = {"Comedy": "喜剧", "Sci-Fi & Fantasy": "科幻与奇幻", "Thriller": "惊悚", "Action & Adventure": "动作",
           "Romance": "爱情", "Anime": "动画", "Drama": "剧情", "Kids & Family": "家庭", "Documentary": "纪录片", "Horror": "恐怖"}
MOODS = {"轻松解压": {"喜剧", "家庭"}, "温暖治愈": {"家庭", "动画"}, "烧脑过瘾": {"惊悚", "科幻与奇幻"},
         "浪漫心动": {"爱情"}, "惊奇冒险": {"动作", "科幻与奇幻"}, "感动一下": {"剧情"}}


def stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CatalogError(Exception):
    def __init__(self, code="UPSTREAM_UNAVAILABLE", message="电影资料源暂时不可用，请稍后重试。", status=503):
        self.code, self.message, self.status = code, message, status


def apple_url(value, artwork=False):
    try:
        u = urlparse(value or "")
        host = u.hostname or ""
        allowed = host.endswith(".mzstatic.com") if artwork else host in ("itunes.apple.com", "tv.apple.com")
        return value if u.scheme == "https" and allowed and not u.username and not u.password else None
    except ValueError:
        return None


class AppleCatalog:
    def __init__(self, client=None, rate_limit=20):
        # Explicit proxy avoids invalid global NO_PROXY entries on Windows.
        self.client = client or httpx.Client(timeout=10, follow_redirects=False, trust_env=False,
                                            proxy=os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY"))
        self.cache, self.records = OrderedDict(), OrderedDict()
        self.lock, self.calls = RLock(), deque()
        self.rate_limit, self.fetch_count = rate_limit, 0

    def get(self, path, params=None):
        key = (path, tuple(sorted((params or {}).items())))
        now = time.monotonic()
        hit = self.cache.get(key)
        if hit and now - hit[0] < 1800:
            self.cache.move_to_end(key)
            return hit[1], hit[2]
        while self.calls and now - self.calls[0] >= 60:
            self.calls.popleft()
        if len(self.calls) >= self.rate_limit:
            raise CatalogError("UPSTREAM_RATE_LIMIT", "资料源请求较多，请一分钟后重试；已有结果仍可查看。")
        self.calls.append(now)
        try:
            response = self.client.get("https://itunes.apple.com" + path, params=params)
            if response.status_code == 429:
                raise CatalogError("UPSTREAM_RATE_LIMIT", "资料源暂时限流，请一分钟后重试。")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except httpx.TimeoutException as exc:
            raise CatalogError("UPSTREAM_TIMEOUT", "电影资料源响应超时，请重新尝试。", 504) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise CatalogError() from exc
        self.fetch_count += 1
        retrieved = stamp()
        self.cache[key] = (now, data, retrieved)
        while len(self.cache) > 128:
            self.cache.popitem(last=False)
        return data, retrieved

    def chart(self, genre=None):
        suffix = f"/genre={GENRES[genre]}" if genre else ""
        data, _ = self.get(f"/us/rss/topmovies/limit=100{suffix}/json")
        feed = data.get("feed")
        if not isinstance(feed, dict) or "entry" not in feed:
            raise CatalogError()
        entries = feed["entry"]
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            raise CatalogError()
        found = []
        for entry in entries:
            try:
                mid = str(entry["id"]["attributes"]["im:id"])
                if not re.fullmatch(r"[1-9][0-9]*", mid):
                    continue
                images = [x.get("label") for x in entry.get("im:image", []) if apple_url(x.get("label"), True)]
                found.append((mid, entry.get("im:name", {}).get("label", ""), images[-1] if images else None))
            except (KeyError, TypeError, AttributeError):
                raise CatalogError()
        return found

    def lookup(self, ids):
        ids = list(dict.fromkeys(ids))
        if any(not re.fullmatch(r"[1-9][0-9]*", mid) for mid in ids):
            raise CatalogError("NOT_FOUND", "没有找到这部影片，请重新查找并确认。", 404)
        now = time.monotonic()
        missing = [mid for mid in ids if mid not in self.records or now - self.records[mid][0] >= 1800]
        for start in range(0, len(missing), 50):
            data, retrieved = self.get("/lookup", {"id": ",".join(missing[start:start+50]), "country": "us"})
            if not isinstance(data.get("results"), list):
                raise CatalogError()
            for row in data["results"]:
                if not isinstance(row, dict):
                    raise CatalogError()
                if row.get("kind") != "feature-movie" or not row.get("trackId") or not row.get("trackName"):
                    continue
                mid = str(row["trackId"])
                millis = row.get("trackTimeMillis")
                runtime = math.ceil(millis / 60000) if isinstance(millis, (float, int)) and 0 < millis <= 36000000 else None
                date = str(row.get("releaseDate") or "")[:4]
                year = int(date) if date.isdigit() and 1888 <= int(date) <= 2200 else None
                movie = Movie(movie_id=f"itunes:{mid}", title=row["trackName"], year=year, runtime_minutes=runtime,
                              genres=[ENGLISH.get(row.get("primaryGenreName"), row.get("primaryGenreName", "类型未知"))],
                              poster_url=apple_url(row.get("artworkUrl100"), True), source_url=apple_url(row.get("trackViewUrl")),
                              director=str(row.get("artistName") or "")[:160] or None,
                              content_advisory=str(row.get("contentAdvisoryRating") or "")[:20] or None,
                              tags=content_clues(row.get("longDescription") or row.get("shortDescription")))
                self.records[mid] = (now, movie, retrieved)
                self.records.move_to_end(mid)
        while len(self.records) > 2000:
            self.records.popitem(last=False)
        return [(self.records[mid][1].model_copy(deep=True), self.records[mid][2]) for mid in ids if mid in self.records and now-self.records[mid][0] < 1800]

    def pool(self, genres):
        entries, membership, posters = {}, {}, {}
        for genre in genres or [None, "喜剧", "剧情"]:
            for rank, (mid, title, poster) in enumerate(self.chart(genre)):
                entries.setdefault(mid, (rank, title))
                membership.setdefault(mid, set()).update([genre] if genre else [])
                if poster:
                    posters[mid] = poster
        films = self.lookup(list(entries))
        for movie, retrieved in films:
            mid = movie.movie_id.split(":")[1]
            movie.genres = sorted(set(movie.genres) | membership[mid])
            if mid in posters:
                movie.poster_url = HttpUrl(posters[mid])
        return films

    def search(self, query, year=None):
        # Store search currently returns no movies in some regions. An empty
        # response can fall back to chart titles; transport errors remain errors.
        data, _ = self.get("/search", {"term": query, "country": "us", "media": "movie", "entity": "movie", "limit": 50})
        if not isinstance(data.get("results"), list) or any(not isinstance(r, dict) for r in data["results"]):
            raise CatalogError()
        ids = [str(r["trackId"]) for r in data["results"] if r.get("kind") == "feature-movie" and r.get("trackId")]
        if not ids:
            titles = {}
            for genre in [None, *GENRES]:
                for mid, title, _ in self.chart(genre):
                    if query.casefold() in title.casefold():
                        titles.setdefault(mid, title)
            ids = list(titles)[:50]
        return [(m, at) for m, at in self.lookup(ids) if year is None or m.year == year]
