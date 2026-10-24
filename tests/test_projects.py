import pytest

from tests.conftest import add_member_and_login, auth, signup


def create_project(client, user, key="TRK", name="TrackIt"):
    return client.post("/projects", json={"key": key, "name": name}, headers=auth(user["access_token"]))


@pytest.fixture
def admin(client):
    return signup(client, "admin")


def test_admin_creates_project_and_key_is_uppercased(client, admin):
    res = create_project(client, admin, key="trk")
    assert res.status_code == 201
    assert res.json()["key"] == "TRK"
    assert res.json()["workspace_id"] == admin["workspace_id"]


def test_duplicate_key_in_same_workspace_is_409(client, admin):
    create_project(client, admin)
    assert create_project(client, admin).status_code == 409


def test_same_key_in_different_workspaces_is_fine(client, admin):
    other = signup(client, "other")
    assert create_project(client, admin).status_code == 201
    assert create_project(client, other).status_code == 201


def test_invalid_key_is_422(client, admin):
    assert create_project(client, admin, key="a b").status_code == 422


def test_member_can_create(client, admin):
    member = add_member_and_login(client, admin, "member")
    assert create_project(client, member).status_code == 201


def test_viewer_cannot_create_403(client, admin):
    viewer = add_member_and_login(client, admin, "viewer")
    res = create_project(client, viewer)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "forbidden"


def test_no_token_is_401_not_403(client):
    assert client.post("/projects", json={"key": "TRK", "name": "x"}).status_code == 401


def test_viewer_can_list_and_read(client, admin):
    project = create_project(client, admin).json()
    viewer = add_member_and_login(client, admin, "viewer")
    assert len(client.get("/projects", headers=auth(viewer["access_token"])).json()) == 1
    assert client.get(f"/projects/{project['id']}", headers=auth(viewer["access_token"])).status_code == 200


def test_member_can_rename_and_other_fields_stay(client, admin):
    project = client.post("/projects", json={"key": "TRK", "name": "Old", "description": "keep me"}, headers=auth(admin["access_token"])).json()
    member = add_member_and_login(client, admin, "member")
    res = client.patch(f"/projects/{project['id']}", json={"name": "New"}, headers=auth(member["access_token"]))
    assert res.status_code == 200
    assert res.json()["name"] == "New"
    assert res.json()["description"] == "keep me"


def test_viewer_cannot_update_403(client, admin):
    project = create_project(client, admin).json()
    viewer = add_member_and_login(client, admin, "viewer")
    res = client.patch(f"/projects/{project['id']}", json={"name": "x"}, headers=auth(viewer["access_token"]))
    assert res.status_code == 403


def test_member_cannot_delete_403(client, admin):
    project = create_project(client, admin).json()
    member = add_member_and_login(client, admin, "member")
    assert client.delete(f"/projects/{project['id']}", headers=auth(member["access_token"])).status_code == 403


def test_admin_deletes_then_it_is_gone(client, admin):
    project = create_project(client, admin).json()
    assert client.delete(f"/projects/{project['id']}", headers=auth(admin["access_token"])).status_code == 204
    assert client.get(f"/projects/{project['id']}", headers=auth(admin["access_token"])).status_code == 404


def test_other_workspace_cannot_read_or_delete_404(client, admin):
    """IDOR check: knowing the id is not enough. Other tenants get 404, so they can't even confirm it exists."""
    project = create_project(client, admin).json()
    outsider = signup(client, "outsider")
    assert client.get(f"/projects/{project['id']}", headers=auth(outsider["access_token"])).status_code == 404
    assert client.delete(f"/projects/{project['id']}", headers=auth(outsider["access_token"])).status_code == 404


def test_list_only_shows_own_workspace(client, admin):
    create_project(client, admin)
    outsider = signup(client, "outsider")
    assert client.get("/projects", headers=auth(outsider["access_token"])).json() == []
