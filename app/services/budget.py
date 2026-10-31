"""Request-scoped counters shared by model, catalog and evidence adapters."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
import time

from scripts.movie_catalog_errors import CatalogError


@dataclass
class RequestBudget:
    max_http: int = 20
    max_search: int = 3
    seconds: float = 45
    clock: object = time.monotonic
    http_calls: int = 0
    search_calls: int = 0
    started: float = field(init=False)
    lock: object = field(default_factory=Lock, repr=False)

    def __post_init__(self):
        self.started = self.clock()

    def check(self):
        remaining = self.seconds - (self.clock() - self.started)
        if remaining <= 0:
            raise CatalogError("UPSTREAM_TIMEOUT", "本次请求已超过时间上限，请重试。", 504)
        return remaining

    def consume(self, *, search=False, timeout=10):
        with self.lock:
            remaining = self.check()
            if self.http_calls >= self.max_http or search and self.search_calls >= self.max_search:
                raise CatalogError("BUDGET_EXHAUSTED", "本次资料查询已达到调用上限，请缩小范围后重试。", 503)
            self.http_calls += 1
            self.search_calls += int(search)
            return max(.001, min(timeout, remaining))


current_budget = ContextVar("movie_request_budget", default=None)


@contextmanager
def budget_scope(budget):
    token = current_budget.set(budget)
    try:
        yield budget
    finally:
        current_budget.reset(token)


def consume(*, search=False, timeout=10):
    budget = current_budget.get()
    return budget.consume(search=search, timeout=timeout) if budget else timeout


@contextmanager
def catalog_lock(lock):
    budget = current_budget.get()
    acquired = lock.acquire(timeout=budget.check()) if budget else lock.acquire()
    if not acquired:
        raise CatalogError("UPSTREAM_TIMEOUT", "资料源正忙，本次等待已超时。", 504)
    try:
        if budget:
            budget.check()
        yield
    finally:
        lock.release()
