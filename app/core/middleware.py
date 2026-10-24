import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.request_context import query_count_var, request_id_var

logger = logging.getLogger("trackit.request")

# Accept a caller's request id only if it looks safe; otherwise make our own (it ends up in logs).
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    For every request:
      1. pick a request id (the caller's X-Request-ID, or a new one),
      2. start a SQL query counter,
      3. after the response, add X-Request-ID to it and write one JSON access-log line.
    """

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        id_token = request_id_var.set(request_id)
        counter = {"n": 0}
        count_token = query_count_var.set(counter)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "db_queries": counter["n"],
                    "client_ip": request.client.host if request.client else None,
                },
            )
            request_id_var.reset(id_token)
            query_count_var.reset(count_token)
