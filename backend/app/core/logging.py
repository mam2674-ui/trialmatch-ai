"""Privacy-preserving logging.

Request bodies, patient narratives and profiles are never logged. The access log records only
method, route template, status and latency. A filter additionally truncates any log message that
looks like it might contain free text from a request.
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("trialmatch")


class _NoPayloadFilter(logging.Filter):
    MAX = 300

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if len(msg) > self.MAX:
            record.msg = msg[: self.MAX] + " …[truncated]"
            record.args = ()
        return True


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for name in ("trialmatch", "uvicorn.access"):
        logging.getLogger(name).addFilter(_NoPayloadFilter())
    # httpx logs full URLs at INFO; trial search URLs can contain condition terms. Keep them out.
    logging.getLogger("httpx").setLevel(logging.WARNING)


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        logger.info(
            "%s %s -> %s (%.0f ms)", request.method, path, response.status_code,
            (time.perf_counter() - start) * 1000,
        )
        return response
