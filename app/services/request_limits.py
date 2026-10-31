"""ASGI deadline: cancel waiting without delaying the error response for a worker."""
import logging
import time
from uuid import uuid4

import anyio
from starlette.responses import JSONResponse

from app.services.budget import budget_scope
from scripts.s0_contracts import ErrorResponse


class RequestLimits:
    def __init__(self, app, budget_factory):
        self.app, self.budget_factory = app, budget_factory

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        trace_id, budget = uuid4().hex, self.budget_factory()
        scope.setdefault("state", {})["trace_id"] = trace_id
        started, response_started, status = time.monotonic(), False, 500

        async def traced_send(message):
            nonlocal response_started, status
            if message["type"] == "http.response.start":
                response_started, status = True, message["status"]
                headers = [(key, value) for key, value in message.get("headers", []) if key.lower() not in {b"x-trace-id", b"x-upstream-calls", b"x-content-type-options"}]
                headers.extend([(b"x-trace-id", trace_id.encode()), (b"x-upstream-calls", str(budget.http_calls).encode()), (b"x-content-type-options", b"nosniff")])
                if scope["path"].startswith(("/identities", "/sessions", "/me/", "/feedback")):
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        with budget_scope(budget):
            try:
                with anyio.fail_after(budget.seconds):
                    await self.app(scope, receive, traced_send)
            except TimeoutError:
                if not response_started:
                    error = ErrorResponse(trace_id=trace_id, data_mode="live", code="UPSTREAM_TIMEOUT",
                        message="本次请求已超时，请重试；原有结果仍可查看。", retryable=True)
                    await JSONResponse(error.model_dump(mode="json"), status_code=504)(scope, receive, traced_send)
                else:
                    raise
            finally:
                logging.getLogger("movie.requests").info("trace=%s route=%s status=%s elapsed_ms=%s http=%s search=%s",
                    trace_id, getattr(scope.get("route"), "path", "unmatched"), status,
                    round((time.monotonic() - started) * 1000), budget.http_calls, budget.search_calls)
