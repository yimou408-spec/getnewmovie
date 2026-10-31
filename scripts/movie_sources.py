"""Real-source recovery. Movie identities and source retrieval clocks stay intact."""
import time
from threading import RLock

from scripts.movie_catalog import AppleCatalog, CatalogError


class CatalogRouter:
    def __init__(self, primary, backup=None):
        self.primary = primary
        self.backup = (backup or AppleCatalog()) if getattr(primary, 'id_prefix', 'itunes') == 'tmdb' else None
        self.lock = getattr(primary, 'lock', RLock())
        self.failed_until = 0

    @property
    def active(self):
        return self.backup if self.failed_until else self.primary

    @property
    def id_prefix(self):
        return getattr(self.active, 'id_prefix', 'itunes')

    @property
    def source_name(self):
        return getattr(self.active, 'source_name', 'Apple iTunes US')

    @property
    def client(self):
        return self.active.client

    @property
    def fetch_count(self):
        return self.primary.fetch_count + (self.backup.fetch_count if self.backup else 0)

    @property
    def warnings(self):
        notices = ['TMDB 暂时不可用，已切换至 Apple 真实电影榜单；片名与来源沿用 Apple，暂不提供 TMDB 评分。'] if self.failed_until else []
        return notices + getattr(self.active, 'warnings', [])

    def listing(self, operation, *args):
        if not self.failed_until or time.monotonic() >= self.failed_until:
            try:
                films = getattr(self.primary, operation)(*args)
                self.failed_until = 0
                return films
            except CatalogError as exc:
                if self.backup is None or exc.status < 500:
                    raise
                self.failed_until = time.monotonic() + 60
        with self.backup.lock:
            return getattr(self.backup, operation)(*args)

    def pool(self, genres):
        return self.listing('pool', genres)

    def search(self, query, year):
        return self.listing('search', query, year)

    def find(self, movie_id):
        for catalog in (self.primary, self.backup):
            if catalog is not None and movie_id.startswith(getattr(catalog, 'id_prefix', 'itunes') + ':'):
                with catalog.lock:
                    found = catalog.lookup([movie_id.split(':', 1)[1]])
                if found:
                    return found[0]
                break
        raise CatalogError('NOT_FOUND', '资料源未返回这部影片，请重新查找并确认。', 404)
