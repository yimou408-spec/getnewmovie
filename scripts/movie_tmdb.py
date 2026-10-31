"""TMDB read-only catalog. Small live candidate pools; no synthetic fallback."""
import re
import time

from scripts.movie_catalog import AppleCatalog, CatalogError
from scripts.movie_ranking import content_clues
from scripts.s0_contracts import Movie, Rating

GENRE_IDS = {"喜剧": [35], "科幻与奇幻": [878, 14], "惊悚": [53, 9648], "动作": [28, 12],
             "爱情": [10749], "动画": [16], "剧情": [18], "家庭": [10751], "纪录片": [99], "恐怖": [27]}
LABELS = {value: label for label, values in GENRE_IDS.items() for value in values}


class TMDBCatalog(AppleCatalog):
    base_url = "https://api.themoviedb.org/3"
    source_name = "TMDB"
    id_prefix = "tmdb"

    def __init__(self, token, **kwargs):
        super().__init__(**kwargs)
        self.token = token

    def get(self, path, params=None):
        if not self.token or any(c in self.token for c in "\r\n"):
            raise CatalogError("NOT_CONFIGURED", "TMDB 未配置有效的 API Read Access Token，请检查本机 .env。")
        if not re.fullmatch(r"/(movie/popular|discover/movie|search/movie|movie/[1-9][0-9]*)", path):
            raise ValueError("unsupported TMDB path")
        return super().get(path, params)

    @property
    def headers(self):
        return {"Authorization": "Bearer " + self.token}

    def lookup(self, ids):
        ids = list(dict.fromkeys(ids))
        if any(not re.fullmatch(r"[1-9][0-9]*", mid) for mid in ids):
            raise CatalogError("NOT_FOUND", "没有找到这部影片，请重新查找。", 404)
        now = time.monotonic()
        for mid in ids:
            if mid in self.records and now - self.records[mid][0] < 1800:
                continue
            data, at = self.get(f"/movie/{mid}", {"language": "zh-CN", "append_to_response": "credits"})
            if data.get("id") != int(mid) or not isinstance(data.get("title"), str) or not data["title"].strip():
                raise CatalogError()
            if data.get("adult") is True:
                continue
            try:
                runtime = data.get("runtime")
                runtime = runtime if type(runtime) is int and 1 <= runtime <= 600 else None
                date = str(data.get("release_date") or "")[:4]
                year = int(date) if date.isdigit() and 1888 <= int(date) <= 2200 else None
                genres = data.get("genres", [])
                if not isinstance(genres, list) or any(not isinstance(g, dict) for g in genres):
                    raise ValueError("invalid genres")
                labels = list(dict.fromkeys(LABELS[g["id"]] for g in genres if g.get("id") in LABELS))
                credits = data.get("credits") or {}
                crew = credits.get("crew", []) if isinstance(credits, dict) else []
                directors = [r["name"] for r in crew if isinstance(r, dict) and r.get("job") == "Director" and isinstance(r.get("name"), str)] if isinstance(crew, list) else []
                score, votes = data.get("vote_average"), data.get("vote_count")
                ratings = [Rating(source="TMDB", value=score, scale=10, vote_count=votes, evidence_id=f"tmdb-rating-{mid}")] if type(score) in (int, float) and 0 <= score <= 10 and type(votes) is int and votes > 0 else []
                poster = data.get("poster_path")
                poster = "https://image.tmdb.org/t/p/w500" + poster if isinstance(poster, str) and re.fullmatch(r"/[A-Za-z0-9_-]+\.(?:jpg|png)", poster) else None
                movie = Movie(movie_id=f"tmdb:{mid}", title=data["title"], year=year, runtime_minutes=runtime,
                    genres=labels, director=" / ".join(directors)[:160] or None, ratings=ratings,
                    poster_url=poster, source_url=f"https://www.themoviedb.org/movie/{mid}",
                    tags=content_clues(data.get("overview") if isinstance(data.get("overview"), str) else ""))
            except (ValueError, TypeError, KeyError) as exc:
                raise CatalogError() from exc
            self.records[mid] = (now, movie, at)
            self.records.move_to_end(mid)
        while len(self.records) > 2000:
            self.records.popitem(last=False)
        return [(self.records[mid][1].model_copy(deep=True), self.records[mid][2]) for mid in ids if mid in self.records and now - self.records[mid][0] < 1800]

    def candidates(self, path, params):
        data, _ = self.get(path, {"language": "zh-CN", "include_adult": "false", "page": 1, **params})
        rows = data.get("results")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise CatalogError()
        # One list + at most eight details requests, shared cached for 30 minutes.
        ids = [str(row["id"]) for row in rows if type(row.get("id")) is int and row["id"] > 0 and row.get("adult") is not True]
        return self.lookup(list(dict.fromkeys(ids))[:8])

    def pool(self, genres):
        ids = sorted({gid for genre in genres for gid in GENRE_IDS.get(genre, [])})
        return self.candidates("/discover/movie", {"sort_by": "popularity.desc", **({"with_genres": "|".join(map(str, ids))} if ids else {})})

    def search(self, query, year=None):
        films = self.candidates("/search/movie", {"query": query, **({"year": year} if year else {})})
        return [(m, at) for m, at in films if year is None or m.year == year]
