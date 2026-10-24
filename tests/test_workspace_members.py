from tests.conftest import auth, signup


def test_admin_adds_existing_user(client):
    admin, person = signup(client, "admin"), signup(client, "person")
    res = client.post("/workspace/members", json={"email": person["email"], "role": "viewer"}, headers=auth(admin["access_token"]))
    assert res.status_code == 201
    assert res.json()["role"] == "viewer"


def test_adding_same_person_twice_is_409(client):
    admin, person = signup(client, "admin"), signup(client, "person")
    body = {"email": person["email"], "role": "viewer"}
    client.post("/workspace/members", json=body, headers=auth(admin["access_token"]))
    assert client.post("/workspace/members", json=body, headers=auth(admin["access_token"])).status_code == 409


def test_adding_unknown_email_is_404(client):
    admin = signup(client, "admin")
    res = client.post("/workspace/members", json={"email": "ghost@example.com", "role": "viewer"}, headers=auth(admin["access_token"]))
    assert res.status_code == 404


def test_only_admin_can_add_members(client):
    from tests.conftest import add_member_and_login

    admin = signup(client, "admin")
    member = add_member_and_login(client, admin, "member")
    newcomer = signup(client, "newcomer")
    res = client.post("/workspace/members", json={"email": newcomer["email"], "role": "admin"}, headers=auth(member["access_token"]))
    assert res.status_code == 403
