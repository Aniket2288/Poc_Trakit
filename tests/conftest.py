import os

# Point the app at a separate test database BEFORE anything imports the settings.
# Real environment variables win over .env, so this overrides DATABASE_NAME only.
os.environ["DATABASE_NAME"] = "trackit_test"

import uuid

import fakeredis
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine, get_db
from app.main import app


def _create_test_database_if_missing():
    """Connect to the server's default 'postgres' database and create trackit_test once."""
    with psycopg.connect(
        host=settings.database_host,
        port=settings.database_port,
        user=settings.database_user,
        password=settings.database_password,
        dbname="postgres",
        autocommit=True,
    ) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.database_name,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{settings.database_name}"')


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Runs once per test run: make sure the test DB exists and is on the latest migration."""
    _create_test_database_if_missing()
    command.upgrade(Config("alembic.ini"), "head")
    yield


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Each test gets its own empty in-memory Redis, and a limit high enough not to get in the way."""
    server = fakeredis.FakeRedis()
    monkeypatch.setattr("app.core.rate_limit.get_redis", lambda: server)
    monkeypatch.setattr(settings, "auth_rate_limit", 1000)
    return server


@pytest.fixture(autouse=True)
def enqueued(monkeypatch):
    """Instead of sending jobs to Redis, tests collect them in this list."""
    calls = []
    monkeypatch.setattr("app.services.jobs.enqueue_assignment_email", lambda audit_id: calls.append(audit_id))
    return calls


@pytest.fixture
def db():
    """
    One database session per test, inside a transaction that is rolled back at the end.

    The services call db.commit(). With join_transaction_mode="create_savepoint" those commits
    only release a SAVEPOINT inside our outer transaction, so the final rollback still undoes
    everything and every test starts from an empty database.
    """
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def client(db):
    """An HTTP client for the app, using the test session instead of a real one."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------- Helpers used by many tests ----------

def unique_email(name: str = "user") -> str:
    return f"{name}-{uuid.uuid4().hex[:8]}@example.com"


def signup(client, name: str = "user", password: str = "secret123") -> dict:
    """Sign up a new user (who becomes admin of a new workspace). Returns tokens, email and headers."""
    email = unique_email(name)
    res = client.post(
        "/auth/signup",
        json={"email": email, "password": password, "full_name": name.title(), "workspace_name": f"{name} team"},
    )
    assert res.status_code == 201, res.text
    tokens = res.json()
    me = client.get("/me", headers=auth(tokens["access_token"])).json()
    return {**tokens, "email": email, "password": password, "workspace_id": me["workspace_id"], "user_id": me["user"]["id"]}


def auth(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def add_member_and_login(client, admin: dict, role: str, name: str = "other") -> dict:
    """Create a second user, add them to the admin's workspace with `role`, and log them in there."""
    person = signup(client, name)
    res = client.post("/workspace/members", json={"email": person["email"], "role": role}, headers=auth(admin["access_token"]))
    assert res.status_code == 201, res.text
    login = client.post(
        "/auth/login",
        json={"email": person["email"], "password": person["password"], "workspace_id": admin["workspace_id"]},
    ).json()
    return {**person, **login, "workspace_id": admin["workspace_id"]}
