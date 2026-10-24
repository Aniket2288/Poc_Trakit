from app.models import AuditLog
from tests.conftest import add_member_and_login, auth, signup


def logs(client, admin, **params):
    return client.get("/audit-logs", params=params, headers=auth(admin["access_token"])).json()


def test_signup_records_workspace_created(client):
    admin = signup(client, "admin")
    actions = [e["action"] for e in logs(client, admin)["items"]]
    assert "workspace.created" in actions


def test_project_create_update_delete_are_all_logged_with_before_and_after(client):
    admin = signup(client, "admin")
    h = auth(admin["access_token"])
    project = client.post("/projects", json={"key": "TRK", "name": "Old"}, headers=h).json()
    client.patch(f"/projects/{project['id']}", json={"name": "New"}, headers=h)
    client.delete(f"/projects/{project['id']}", headers=h)

    entries = logs(client, admin, entity_type="project", entity_id=project["id"])["items"]
    by_action = {e["action"]: e for e in entries}
    assert by_action["project.created"]["after"]["name"] == "Old"
    assert by_action["project.updated"]["before"]["name"] == "Old"
    assert by_action["project.updated"]["after"]["name"] == "New"
    # The project row is gone, but the audit log kept its last state.
    assert by_action["project.deleted"]["before"]["name"] == "New"
    assert all(e["actor_id"] == admin["user_id"] for e in entries)


def test_failed_change_writes_no_audit_row(client, db):
    """A 409 means nothing was saved, so there must be no log entry either (same transaction)."""
    admin = signup(client, "admin")
    h = auth(admin["access_token"])
    client.post("/projects", json={"key": "TRK", "name": "A"}, headers=h)
    before = db.query(AuditLog).count()
    assert client.post("/projects", json={"key": "TRK", "name": "B"}, headers=h).status_code == 409
    assert db.query(AuditLog).count() == before


def test_member_added_is_logged(client):
    admin = signup(client, "admin")
    add_member_and_login(client, admin, "viewer")
    assert "member.added" in [e["action"] for e in logs(client, admin)["items"]]


def test_only_admins_can_read_the_audit_log(client):
    admin = signup(client, "admin")
    member = add_member_and_login(client, admin, "member")
    assert client.get("/audit-logs", headers=auth(member["access_token"])).status_code == 403


def test_audit_log_is_scoped_to_the_workspace(client):
    admin = signup(client, "admin")
    client.post("/projects", json={"key": "TRK", "name": "Secret"}, headers=auth(admin["access_token"]))
    outsider = signup(client, "outsider")
    assert all(e["entity_type"] != "project" for e in logs(client, outsider)["items"])


def test_list_members_shows_names_and_roles(client):
    admin = signup(client, "admin")
    viewer = add_member_and_login(client, admin, "viewer")
    members = client.get("/workspace/members", headers=auth(viewer["access_token"])).json()
    assert {m["role"] for m in members} == {"admin", "viewer"}
    assert all(m["email"] and m["full_name"] for m in members)
