import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core import security
from app.core.config import settings
from app.models import Membership, Role, User
from tests.conftest import add_member_and_login, auth, signup, unique_email


def decode_payload(token: str) -> dict:
    """Read a JWT's payload without checking the signature (anyone can do this)."""
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


# ---------- Signup ----------

def test_signup_returns_a_token_pair(client):
    res = client.post("/auth/signup", json={"email": unique_email(), "password": "secret123", "full_name": "A", "workspace_name": "Team"})
    assert res.status_code == 201
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_minutes * 60
    assert body["access_token"] and body["refresh_token"]


def test_signup_makes_the_user_admin_of_a_new_workspace(client):
    user = signup(client, "owner")
    me = client.get("/me", headers=auth(user["access_token"])).json()
    assert me["role"] == "admin"


def test_signup_with_same_email_in_capitals_is_a_conflict(client):
    user = signup(client)
    res = client.post("/auth/signup", json={"email": user["email"].upper(), "password": "secret123", "full_name": "B", "workspace_name": "X"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "conflict"


def test_signup_validation_errors_list_each_bad_field(client):
    res = client.post("/auth/signup", json={"email": "not-an-email", "password": "short"})
    assert res.status_code == 422
    fields = {d["field"] for d in res.json()["error"]["details"]}
    assert {"body.email", "body.password", "body.full_name", "body.workspace_name"} <= fields


def test_password_is_stored_hashed_never_plain(client, db):
    user = signup(client)
    row = db.query(User).filter_by(email=user["email"]).one()
    assert row.password_hash != user["password"]
    assert row.password_hash.startswith("$argon2")


# ---------- Login ----------

def test_login_with_correct_password(client):
    user = signup(client)
    res = client.post("/auth/login", json={"email": user["email"], "password": user["password"]})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password_and_unknown_email_give_the_same_401(client):
    user = signup(client)
    wrong_pw = client.post("/auth/login", json={"email": user["email"], "password": "wrong-pass"})
    no_user = client.post("/auth/login", json={"email": unique_email(), "password": "wrong-pass"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["error"]["message"] == no_user.json()["error"]["message"]


def test_login_disabled_user_is_rejected(client, db):
    user = signup(client)
    db.query(User).filter_by(email=user["email"]).update({"is_active": False})
    res = client.post("/auth/login", json={"email": user["email"], "password": user["password"]})
    assert res.status_code == 401


def test_login_into_a_workspace_you_are_not_in_is_403(client):
    a = signup(client, "a")
    b = signup(client, "b")
    res = client.post("/auth/login", json={"email": a["email"], "password": a["password"], "workspace_id": b["workspace_id"]})
    assert res.status_code == 403


# ---------- /me and token checks ----------

def test_me_returns_profile_without_password_hash(client):
    user = signup(client)
    res = client.get("/me", headers=auth(user["access_token"]))
    assert res.status_code == 200
    assert res.json()["user"]["email"] == user["email"]
    assert "password_hash" not in res.json()["user"]


def test_me_without_token_is_401_with_www_authenticate(client):
    res = client.get("/me")
    assert res.status_code == 401
    assert res.headers["WWW-Authenticate"] == "Bearer"


def test_me_with_tampered_signature_is_401(client):
    user = signup(client)
    header, payload, signature = user["access_token"].split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}AAAA"
    res = client.get("/me", headers=auth(tampered))
    assert res.status_code == 401
    assert res.json()["error"]["message"] == "Invalid token"


def test_me_with_changed_role_in_payload_is_401(client):
    """Editing the payload (viewer -> admin) breaks the signature."""
    user = signup(client)
    header, payload, signature = user["access_token"].split(".")
    claims = decode_payload(user["access_token"])
    claims["role"] = "admin"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    res = client.get("/me", headers=auth(f"{header}.{forged}.{signature}"))
    assert res.status_code == 401


def test_me_with_token_signed_by_another_secret_is_401(client):
    user = signup(client)
    claims = decode_payload(user["access_token"])
    fake = jwt.encode(claims, "a-completely-different-secret-that-is-long-enough", algorithm="HS256")
    assert client.get("/me", headers=auth(fake)).status_code == 401


def test_me_with_expired_token_is_401(client):
    user = signup(client)
    claims = decode_payload(user["access_token"])
    past = datetime.now(timezone.utc) - timedelta(minutes=30)
    claims.update(iat=past, exp=past + timedelta(minutes=15))
    expired = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    res = client.get("/me", headers=auth(expired))
    assert res.status_code == 401
    assert res.json()["error"]["message"] == "Token has expired"


def test_refresh_token_cannot_be_used_as_access_token(client):
    user = signup(client)
    res = client.get("/me", headers=auth(user["refresh_token"]))
    assert res.status_code == 401
    assert res.json()["error"]["message"] == "Wrong token type"


def test_access_token_has_all_required_claims(client):
    user = signup(client)
    claims = decode_payload(user["access_token"])
    assert {"sub", "iat", "exp", "jti", "type", "workspace_id", "role"} <= claims.keys()
    assert claims["exp"] - claims["iat"] == settings.access_token_minutes * 60
    assert "password" not in json.dumps(claims)


# ---------- Refresh rotation ----------

def test_refresh_gives_a_new_pair_and_retires_the_old_token(client):
    user = signup(client)
    first = client.post("/auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert first.status_code == 200
    assert first.json()["refresh_token"] != user["refresh_token"]
    again = client.post("/auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert again.status_code == 401


def test_reusing_an_old_refresh_token_revokes_every_token(client):
    user = signup(client)
    new = client.post("/auth/refresh", json={"refresh_token": user["refresh_token"]}).json()
    client.post("/auth/refresh", json={"refresh_token": user["refresh_token"]})  # reuse = theft signal
    res = client.post("/auth/refresh", json={"refresh_token": new["refresh_token"]})
    assert res.status_code == 401


def test_access_token_cannot_be_used_to_refresh(client):
    user = signup(client)
    res = client.post("/auth/refresh", json={"refresh_token": user["access_token"]})
    assert res.status_code == 401


def test_refresh_picks_up_a_role_change(client, db):
    admin = signup(client, "admin")
    viewer = add_member_and_login(client, admin, "viewer")
    db.query(Membership).filter_by(user_id=uuid.UUID(viewer["user_id"])).filter_by(
        workspace_id=uuid.UUID(admin["workspace_id"])
    ).update({"role": Role.MEMBER})
    new = client.post("/auth/refresh", json={"refresh_token": viewer["refresh_token"]}).json()
    assert decode_payload(new["access_token"])["role"] == "member"


# ---------- Logout ----------

def test_logout_revokes_the_refresh_token(client):
    user = signup(client)
    assert client.post("/auth/logout", json={"refresh_token": user["refresh_token"]}).status_code == 204
    assert client.post("/auth/refresh", json={"refresh_token": user["refresh_token"]}).status_code == 401


def test_logout_twice_is_harmless(client):
    user = signup(client)
    client.post("/auth/logout", json={"refresh_token": user["refresh_token"]})
    assert client.post("/auth/logout", json={"refresh_token": user["refresh_token"]}).status_code == 204


# ---------- Security helpers (unit tests, no HTTP) ----------

def test_password_hash_and_verify():
    hashed = security.hash_password("secret123")
    assert security.verify_password("secret123", hashed)
    assert not security.verify_password("wrong", hashed)
