import pytest

from tests.conftest import add_member_and_login, auth, signup


@pytest.fixture
def setup(client):
    """A workspace with one project and 6 issues of different kinds."""
    admin = signup(client, "admin")
    member = add_member_and_login(client, admin, "member")
    h = auth(admin["access_token"])
    project = client.post("/projects", json={"key": "TRK", "name": "TrackIt"}, headers=h).json()

    def make(title, **fields):
        return client.post(f"/projects/{project['id']}/issues", json={"title": title, **fields}, headers=h).json()

    issues = {
        "login": make("Login button broken", priority="urgent", labels=["bug"], assignee_id=member["user_id"], due_date="2026-11-01"),
        "signup": make("Signup email typo", priority="low", labels=["bug", "copy"]),
        "dark": make("Add dark mode", priority="medium", labels=["feature"], due_date="2026-12-15"),
        "perf": make("Speed up issue list", priority="high", description="the LOGIN page is slow too"),
        "docs": make("Write API docs", priority="low", labels=["docs"], assignee_id=member["user_id"]),
        "pct": make("Show 50% progress bar", priority="medium"),
    }
    client.post(f"/issues/{issues['login']['id']}/transition", json={"status": "in_progress"}, headers=h)
    return {"admin": admin, "member": member, "h": h, "project": project, "issues": issues}


def list_issues(client, setup, **params):
    res = client.get("/issues", params=params, headers=setup["h"])
    assert res.status_code == 200, res.text
    return res.json()


def titles(page):
    return [i["title"] for i in page["items"]]


def test_default_list_returns_every_issue(client, setup):
    # (Not checking created_at order here: inside one test transaction Postgres' now() is the same for every row.)
    page = list_issues(client, setup)
    assert page["total"] == 6
    assert len(page["items"]) == 6


def test_offset_pagination_pages_do_not_overlap(client, setup):
    first = list_issues(client, setup, limit=4, offset=0)
    second = list_issues(client, setup, limit=4, offset=4)
    assert len(first["items"]) == 4 and len(second["items"]) == 2
    assert not set(titles(first)) & set(titles(second))
    assert first["total"] == second["total"] == 6


def test_filter_by_status(client, setup):
    assert titles(list_issues(client, setup, status="in_progress")) == ["Login button broken"]


def test_filter_by_assignee(client, setup):
    page = list_issues(client, setup, assignee_id=setup["member"]["user_id"])
    assert set(titles(page)) == {"Login button broken", "Write API docs"}


def test_filter_by_label(client, setup):
    assert set(titles(list_issues(client, setup, label="bug"))) == {"Login button broken", "Signup email typo"}


def test_filters_combine(client, setup):
    assert titles(list_issues(client, setup, label="bug", priority="low")) == ["Signup email typo"]


def test_search_matches_title_and_description_case_insensitive(client, setup):
    assert set(titles(list_issues(client, setup, q="login"))) == {"Login button broken", "Speed up issue list"}


def test_search_treats_percent_as_plain_text(client, setup):
    assert titles(list_issues(client, setup, q="50%")) == ["Show 50% progress bar"]


def test_sort_by_priority_uses_real_order_not_alphabetical(client, setup):
    priorities = [i["priority"] for i in list_issues(client, setup, sort="priority", order="desc")["items"]]
    assert priorities == ["urgent", "high", "medium", "medium", "low", "low"]


def test_sort_by_due_date_puts_missing_dates_last(client, setup):
    page = list_issues(client, setup, sort="due_date", order="asc")
    assert titles(page)[:2] == ["Login button broken", "Add dark mode"]
    assert all(i["due_date"] is None for i in page["items"][2:])


def test_bad_query_params_are_422(client, setup):
    assert client.get("/issues", params={"limit": 0}, headers=setup["h"]).status_code == 422
    assert client.get("/issues", params={"sort": "title"}, headers=setup["h"]).status_code == 422


def test_list_is_scoped_to_workspace(client, setup):
    outsider = signup(client, "outsider")
    assert client.get("/issues", headers=auth(outsider["access_token"])).json()["total"] == 0


def test_list_endpoint_is_documented_with_examples(client):
    spec = client.get("/openapi.json").json()
    params = {p["name"]: p for p in spec["paths"]["/issues"]["get"]["parameters"]}
    assert {"status", "assignee_id", "label", "q", "sort", "order", "limit", "offset"} <= params.keys()
    assert params["label"]["schema"]["examples"] == ["bug"]
