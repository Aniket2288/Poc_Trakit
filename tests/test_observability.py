import json
import logging

import pytest
from sqlalchemy import event

from app.core.config import settings
from app.core.database import engine
from app.core.logging import JsonFormatter
from app.core.request_context import request_id_var
from tests.conftest import auth, signup, unique_email

# ---------- Request IDs ----------


def test_every_response_has_a_request_id(client):
    res = client.get("/health")
    assert len(res.headers["X-Request-ID"]) == 32


def test_callers_request_id_is_reused(client):
    res = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert res.headers["X-Request-ID"] == "trace-abc-123"


def test_unsafe_request_id_is_replaced(client):
    res = client.get("/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert res.headers["X-Request-ID"] != "bad id\nwith newline"


def test_error_body_contains_the_same_request_id(client):
    res = client.get("/me", headers={"X-Request-ID": "req-401-test"})
    assert res.json()["error"]["request_id"] == "req-401-test"


# ---------- JSON logs ----------


def test_access_log_line_has_request_fields(client, caplog):
    with caplog.at_level(logging.INFO, logger="trackit.request"):
        client.get("/health", headers={"X-Request-ID": "log-test-1"})
    record = next(r for r in caplog.records if r.name == "trackit.request")
    line = json.loads(JsonFormatter().format(record))
    assert line["message"] == "request"
    assert line["path"] == "/health" and line["method"] == "GET" and line["status"] == 200
    assert line["db_queries"] == 1  # the SELECT 1
    assert isinstance(line["duration_ms"], float)


def test_json_formatter_includes_request_id_from_context():
    token = request_id_var.set("ctx-id-42")
    try:
        record = logging.makeLogRecord({"name": "x", "levelname": "INFO", "msg": "hello %s", "args": ("world",)})
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert line == {**line, "message": "hello world", "request_id": "ctx-id-42", "level": "INFO"}


# ---------- Rate limiting ----------


def test_auth_endpoints_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit", 3)
    body = {"email": unique_email(), "password": "wrong-pass"}
    codes = [client.post("/auth/login", json=body).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_rate_limited_response_says_when_to_retry(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit", 1)
    client.post("/auth/login", json={"email": unique_email(), "password": "x"})
    res = client.post("/auth/login", json={"email": unique_email(), "password": "x"})
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(res.headers["Retry-After"]) <= settings.auth_rate_window_seconds


def test_non_auth_endpoints_are_not_rate_limited(client, monkeypatch):
    user = signup(client)
    monkeypatch.setattr(settings, "auth_rate_limit", 1)
    assert all(client.get("/me", headers=auth(user["access_token"])).status_code == 200 for _ in range(5))


def test_rate_limiter_fails_open_if_redis_is_down(client, monkeypatch):
    import redis

    class DownRedis:
        def pipeline(self):
            raise redis.ConnectionError("down")

    monkeypatch.setattr("app.core.rate_limit.get_redis", lambda: DownRedis())
    res = client.post("/auth/login", json={"email": unique_email(), "password": "x"})
    assert res.status_code == 401  # not 500, and not blocked


# ---------- N+1 ----------


@pytest.fixture
def count_queries():
    statements = []

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    yield statements
    event.remove(engine, "before_cursor_execute", record)


def _queries_for_list(client, db, n, count_queries):
    admin = signup(client, f"n{n}")
    h = auth(admin["access_token"])
    project = client.post("/projects", json={"key": "NP", "name": "NP"}, headers=h).json()
    for i in range(n):
        client.post(f"/projects/{project['id']}/issues", json={"title": f"I{i}", "labels": ["a", f"b{i}"], "assignee_id": admin["user_id"]}, headers=h)
    db.expunge_all()  # empty session, like a fresh request
    count_queries.clear()
    assert client.get("/issues", params={"limit": 100}, headers=h).json()["total"] == n
    return len(count_queries)


def test_issue_list_query_count_does_not_grow_with_issue_count(client, db, count_queries):
    """Regression test for the N+1 fix (docs/n-plus-one.md). Removing the eager loading makes this fail."""
    few = _queries_for_list(client, db, 3, count_queries)
    many = _queries_for_list(client, db, 30, count_queries)
    assert few == many == 3
