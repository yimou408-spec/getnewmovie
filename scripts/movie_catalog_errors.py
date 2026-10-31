"""Shared errors, independent of transport and persistence modules."""


class CatalogError(Exception):
    def __init__(self, code="UPSTREAM_UNAVAILABLE", message="电影资料源暂时不可用，请稍后重试。", status=503):
        self.code, self.message, self.status = code, message, status
