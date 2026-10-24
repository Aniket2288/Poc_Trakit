from sqlalchemy import inspect

from app.core.database import engine


def test_health_reports_database_ok(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "database": "ok"}


def test_migrations_created_every_table_in_the_real_database():
    """Integration test: the schema in Postgres comes from the real Alembic migrations, not from the models."""
    tables = set(inspect(engine).get_table_names())
    assert {"users", "workspaces", "memberships", "projects", "refresh_tokens", "alembic_version"} <= tables


def test_unknown_url_uses_the_error_envelope(client):
    res = client.get("/does-not-exist")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "http_error"
