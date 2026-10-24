"""
Per-request values that any code can read without passing them around: the request id and a SQL query counter.

contextvars keep a separate value for each request, even when many requests run at the same time,
and FastAPI copies them into the thread that runs a `def` endpoint.
"""

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
# A dict (not an int) so the thread running the endpoint and the middleware share the SAME counter object.
query_count_var: ContextVar[dict | None] = ContextVar("query_count", default=None)


def current_request_id() -> str | None:
    return request_id_var.get()


def count_query() -> None:
    counter = query_count_var.get()
    if counter is not None:
        counter["n"] += 1
