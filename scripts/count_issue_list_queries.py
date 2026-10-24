"""
Evidence for the N+1 fix: how many SQL queries does GET /issues run for 5, 25 and 50 issues?

    python -m scripts.count_issue_list_queries          (add --show-sql to print every statement)

Runs against the trackit_test database inside a transaction that is rolled back, so it leaves nothing behind.
With an N+1 problem the count grows with the number of issues. After the fix it stays flat.
"""

import os
import sys

os.environ["DATABASE_NAME"] = "trackit_test"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import jobs  # noqa: E402

# Everything here is rolled back, so no real jobs may reach Redis: the worker would look for events that never existed.
jobs.enqueue_assignment_email = lambda audit_id: None

SHOW_SQL = "--show-sql" in sys.argv


def run(issue_count: int) -> int:
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False, expire_on_commit=False)
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        signup = client.post("/auth/signup", json={"email": f"n1-{issue_count}@example.com", "password": "secret123", "full_name": "N1", "workspace_name": "N1"})
        h = {"Authorization": f"Bearer {signup.json()['access_token']}"}
        project = client.post("/projects", json={"key": "N1", "name": "N1"}, headers=h).json()
        me = client.get("/me", headers=h).json()
        for i in range(issue_count):
            client.post(
                f"/projects/{project['id']}/issues",
                json={"title": f"Issue {i}", "labels": ["bug", f"label{i % 3}"], "assignee_id": me["user"]["id"]},
                headers=h,
            )
        db.expunge_all()  # start the list request with an empty session, like a real request would

        statements = []

        def record(conn, cursor, statement, *args):
            statements.append(" ".join(statement.split()))

        event.listen(engine, "before_cursor_execute", record)
        try:
            res = client.get("/issues", params={"limit": 100}, headers=h)
        finally:
            event.remove(engine, "before_cursor_execute", record)
        assert res.status_code == 200 and res.json()["total"] == issue_count

        if SHOW_SQL:
            for s in statements:
                print("   ", s[:140])
        # The first queries of the request come from auth/session setup; count everything the request ran.
        return len(statements)
    finally:
        app.dependency_overrides.clear()
        db.close()
        outer.rollback()
        connection.close()


if __name__ == "__main__":
    for n in (5, 25, 50):
        print(f"GET /issues with {n:>2} issues -> {run(n)} SQL queries")
