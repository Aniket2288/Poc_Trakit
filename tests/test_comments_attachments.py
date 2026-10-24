import time
import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from app.core import storage
from app.core.config import settings
from tests.conftest import add_member_and_login, auth, signup

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))


@pytest.fixture
def ctx(client):
    admin = signup(client, "admin")
    h = auth(admin["access_token"])
    project = client.post("/projects", json={"key": "TRK", "name": "TrackIt"}, headers=h).json()
    issue = client.post(f"/projects/{project['id']}/issues", json={"title": "Bug"}, headers=h).json()
    return {"admin": admin, "h": h, "issue": issue}


def upload(client, ctx, name, data, content_type="application/octet-stream"):
    return client.post(f"/issues/{ctx['issue']['id']}/attachments", files={"file": (name, data, content_type)}, headers=ctx["h"])


# ---------- Comments ----------

def test_add_and_list_comments(client, ctx):
    client.post(f"/issues/{ctx['issue']['id']}/comments", json={"body": "First"}, headers=ctx["h"])
    comments = client.get(f"/issues/{ctx['issue']['id']}/comments", headers=ctx["h"]).json()
    assert [c["body"] for c in comments] == ["First"]
    assert comments[0]["author"]["email"] == ctx["admin"]["email"]
    assert comments[0]["edited_at"] is None


def test_editing_keeps_the_old_text_in_history(client, ctx):
    comment = client.post(f"/issues/{ctx['issue']['id']}/comments", json={"body": "v1"}, headers=ctx["h"]).json()
    client.patch(f"/comments/{comment['id']}", json={"body": "v2"}, headers=ctx["h"])
    edited = client.patch(f"/comments/{comment['id']}", json={"body": "v3"}, headers=ctx["h"]).json()
    assert edited["body"] == "v3" and edited["edited_at"] is not None
    history = client.get(f"/comments/{comment['id']}/history", headers=ctx["h"]).json()
    assert [r["body"] for r in history] == ["v2", "v1"]  # newest first


def test_only_the_author_can_edit(client, ctx):
    comment = client.post(f"/issues/{ctx['issue']['id']}/comments", json={"body": "mine"}, headers=ctx["h"]).json()
    member = add_member_and_login(client, ctx["admin"], "member")
    res = client.patch(f"/comments/{comment['id']}", json={"body": "hijacked"}, headers=auth(member["access_token"]))
    assert res.status_code == 403


def test_viewer_cannot_comment(client, ctx):
    viewer = add_member_and_login(client, ctx["admin"], "viewer")
    res = client.post(f"/issues/{ctx['issue']['id']}/comments", json={"body": "hi"}, headers=auth(viewer["access_token"]))
    assert res.status_code == 403


def test_comment_edits_are_audited(client, ctx):
    comment = client.post(f"/issues/{ctx['issue']['id']}/comments", json={"body": "v1"}, headers=ctx["h"]).json()
    client.patch(f"/comments/{comment['id']}", json={"body": "v2"}, headers=ctx["h"])
    entries = client.get("/audit-logs", params={"entity_id": comment["id"]}, headers=ctx["h"]).json()["items"]
    edit = next(e for e in entries if e["action"] == "comment.edited")
    assert edit["before"] == {"body": "v1"} and edit["after"] == {"body": "v2"}


# ---------- Attachments: validation ----------

def test_upload_png_detected_from_bytes(client, ctx):
    res = upload(client, ctx, "screenshot.png", PNG)
    assert res.status_code == 201
    assert res.json()["content_type"] == "image/png"
    assert res.json()["size_bytes"] == len(PNG)


def test_fake_extension_is_rejected(client, ctx):
    """An .exe renamed to .png is still rejected: we read the bytes, not the name."""
    res = upload(client, ctx, "innocent.png", b"MZ\x90\x00\x03\x00\x00\x00", "image/png")
    assert res.status_code == 422
    assert "not allowed" in res.json()["error"]["message"]


def test_too_large_file_is_rejected(client, ctx, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 50)
    assert upload(client, ctx, "big.txt", b"a" * 51).status_code == 422


def test_empty_file_is_rejected(client, ctx):
    assert upload(client, ctx, "empty.txt", b"").status_code == 422


def test_path_traversal_filename_is_cleaned(client, ctx):
    res = upload(client, ctx, "../../etc/passwd", b"hello")
    assert res.json()["original_name"] == "passwd"


# ---------- Attachments: signed URLs ----------

def test_signed_url_downloads_the_file(client, ctx):
    url = upload(client, ctx, "notes.txt", b"hello world").json()["download_url"]
    res = client.get(url)  # no Authorization header
    assert res.status_code == 200
    assert res.content == b"hello world"
    assert "attachment" in res.headers["content-disposition"]


def test_tampered_signature_is_rejected(client, ctx):
    url = upload(client, ctx, "notes.txt", b"hello").json()["download_url"]
    assert client.get(url[:-4] + "0000").status_code == 403


def test_changing_the_expiry_breaks_the_signature(client, ctx):
    url = upload(client, ctx, "notes.txt", b"hello").json()["download_url"]
    expires = parse_qs(urlparse(url).query)["expires"][0]
    assert client.get(url.replace(f"expires={expires}", f"expires={int(expires) + 99999}")).status_code == 403


def test_expired_link_is_rejected(client, ctx):
    attachment = upload(client, ctx, "notes.txt", b"hello").json()
    past = int(time.time()) - 10
    signature = storage._signature(uuid.UUID(attachment["id"]), past)
    res = client.get(f"/attachments/{attachment['id']}/download?expires={past}&signature={signature}")
    assert res.status_code == 403


def test_other_workspace_cannot_list_attachments(client, ctx):
    upload(client, ctx, "notes.txt", b"hello")
    outsider = signup(client, "outsider")
    assert client.get(f"/issues/{ctx['issue']['id']}/attachments", headers=auth(outsider["access_token"])).status_code == 404


def test_detect_type_unit():
    assert storage.detect_type(PNG) == "image/png"
    assert storage.detect_type(b"%PDF-1.7 ...") == "application/pdf"
    assert storage.detect_type("héllo".encode()) == "text/plain"
    assert storage.detect_type(b"\x00\x01binary") is None
