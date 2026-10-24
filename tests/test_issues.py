import pytest

from app.models import IssueStatus
from app.services.issue_service import ALLOWED_TRANSITIONS, check_transition
from app.core.exceptions import InvalidTransitionError
from tests.conftest import add_member_and_login, auth, signup


@pytest.fixture
def admin(client):
    return signup(client, "admin")


@pytest.fixture
def project(client, admin):
    return client.post("/projects", json={"key": "TRK", "name": "TrackIt"}, headers=auth(admin["access_token"])).json()


def new_issue(client, user, project, **fields):
    body = {"title": "Something is broken", **fields}
    res = client.post(f"/projects/{project['id']}/issues", json=body, headers=auth(user["access_token"]))
    assert res.status_code == 201, res.text
    return res.json()


def move(client, user, issue, status):
    return client.post(f"/issues/{issue['id']}/transition", json={"status": status}, headers=auth(user["access_token"]))


# ---------- Create ----------

def test_create_issue_starts_in_backlog_with_a_key(client, admin, project):
    issue = new_issue(client, admin, project, priority="high", due_date="2026-12-01", labels=[" Bug", "bug ", "UI"])
    assert issue["status"] == "backlog"
    assert issue["key"] == "TRK-1"
    assert issue["priority"] == "high"
    assert issue["due_date"] == "2026-12-01"
    assert issue["labels"] == ["bug", "ui"]  # trimmed, lowercased, de-duplicated


def test_issue_numbers_count_up_per_project(client, admin, project):
    assert [new_issue(client, admin, project)["key"] for _ in range(3)] == ["TRK-1", "TRK-2", "TRK-3"]


def test_viewer_cannot_create_issue(client, admin, project):
    viewer = add_member_and_login(client, admin, "viewer")
    res = client.post(f"/projects/{project['id']}/issues", json={"title": "x"}, headers=auth(viewer["access_token"]))
    assert res.status_code == 403


def test_cannot_create_issue_in_another_workspaces_project(client, project):
    outsider = signup(client, "outsider")
    res = client.post(f"/projects/{project['id']}/issues", json={"title": "x"}, headers=auth(outsider["access_token"]))
    assert res.status_code == 404


def test_assignee_must_be_in_the_workspace(client, admin, project):
    outsider = signup(client, "outsider")
    res = client.post(
        f"/projects/{project['id']}/issues", json={"title": "x", "assignee_id": outsider["user_id"]}, headers=auth(admin["access_token"])
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "unprocessable"


# ---------- State machine ----------

def test_full_happy_path_through_the_state_machine(client, admin, project):
    issue = new_issue(client, admin, project)
    for status in ["in_progress", "review", "done"]:
        res = move(client, admin, issue, status)
        assert res.status_code == 200
        assert res.json()["status"] == status


def test_backlog_straight_to_done_is_rejected_with_422_and_clear_message(client, admin, project):
    issue = new_issue(client, admin, project)
    res = move(client, admin, issue, "done")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_transition"
    assert res.json()["error"]["message"] == "Cannot move an issue from Backlog to Done. Allowed next: In Progress."


def test_done_can_be_reopened_but_not_sent_to_backlog(client, admin, project):
    issue = new_issue(client, admin, project)
    for status in ["in_progress", "review", "done"]:
        move(client, admin, issue, status)
    assert move(client, admin, issue, "backlog").status_code == 422
    assert move(client, admin, issue, "in_progress").status_code == 200


def test_moving_to_the_same_status_is_a_harmless_no_op(client, admin, project):
    issue = new_issue(client, admin, project)
    assert move(client, admin, issue, "backlog").status_code == 200


def test_unknown_status_is_a_validation_error(client, admin, project):
    issue = new_issue(client, admin, project)
    assert move(client, admin, issue, "archived").json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("current", list(IssueStatus))
@pytest.mark.parametrize("new", list(IssueStatus))
def test_state_machine_table(current, new):
    """Unit test of every pair (16 combinations): allowed ones pass, everything else raises."""
    if current == new:
        return
    if new in ALLOWED_TRANSITIONS[current]:
        check_transition(current, new)
    else:
        with pytest.raises(InvalidTransitionError):
            check_transition(current, new)


# ---------- Update and assign ----------

def test_update_changes_only_sent_fields(client, admin, project):
    issue = new_issue(client, admin, project, description="keep", labels=["bug"])
    res = client.patch(f"/issues/{issue['id']}", json={"priority": "urgent", "labels": ["ui"]}, headers=auth(admin["access_token"]))
    assert res.json()["priority"] == "urgent"
    assert res.json()["labels"] == ["ui"]
    assert res.json()["description"] == "keep"


def test_assign_and_unassign(client, admin, project):
    member = add_member_and_login(client, admin, "member")
    issue = new_issue(client, admin, project)
    res = client.post(f"/issues/{issue['id']}/assign", json={"assignee_id": member["user_id"]}, headers=auth(admin["access_token"]))
    assert res.json()["assignee"]["id"] == member["user_id"]
    res = client.post(f"/issues/{issue['id']}/assign", json={"assignee_id": None}, headers=auth(admin["access_token"]))
    assert res.json()["assignee"] is None


def test_every_issue_change_is_audited(client, admin, project):
    member = add_member_and_login(client, admin, "member")
    issue = new_issue(client, admin, project)
    h = auth(admin["access_token"])
    client.patch(f"/issues/{issue['id']}", json={"title": "New title"}, headers=h)
    client.post(f"/issues/{issue['id']}/assign", json={"assignee_id": member["user_id"]}, headers=h)
    move(client, admin, issue, "in_progress")
    entries = client.get("/audit-logs", params={"entity_id": issue["id"]}, headers=h).json()["items"]
    actions = {e["action"] for e in entries}
    assert actions == {"issue.created", "issue.updated", "issue.assigned", "issue.status_changed"}
    status_entry = next(e for e in entries if e["action"] == "issue.status_changed")
    assert status_entry["before"] == {"status": "backlog"} and status_entry["after"] == {"status": "in_progress"}


def test_rejected_transition_writes_no_audit_entry(client, admin, project):
    issue = new_issue(client, admin, project)
    move(client, admin, issue, "done")
    entries = client.get("/audit-logs", params={"entity_id": issue["id"]}, headers=auth(admin["access_token"])).json()["items"]
    assert [e["action"] for e in entries] == ["issue.created"]
