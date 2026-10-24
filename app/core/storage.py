import hashlib
import hmac
import re
import time
import uuid
from pathlib import Path

from app.core.config import settings

# ---------- File type detection ----------
# We never trust the file name or the browser's Content-Type. We look at the first bytes ("magic numbers").
SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"%PDF-": "application/pdf",
}
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/gif", "application/pdf", "text/plain"}


def detect_type(data: bytes) -> str | None:
    for magic, content_type in SIGNATURES.items():
        if data.startswith(magic):
            return content_type
    # Plain text: must decode as UTF-8 and contain no NUL bytes (binary files almost always do).
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return "text/plain" if b"\x00" not in data else None


def clean_filename(name: str | None) -> str:
    """'../../etc/passwd' -> 'passwd'. Keeps only safe characters. Used for display, never as a path."""
    base = Path(name or "file").name
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._") or "file"
    return base[:100]


# ---------- Local disk storage ----------

def save(data: bytes) -> str:
    """Store bytes under a random name and return that name (the storage key)."""
    key = uuid.uuid4().hex
    folder = Path(settings.upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / key).write_bytes(data)
    return key


def path_for(key: str) -> Path:
    return Path(settings.upload_dir) / key


# ---------- Signed download URLs ----------
# The link carries an expiry time and an HMAC signature of (attachment id + expiry).
# Changing either part breaks the signature, and the server refuses expired links.

def _signature(attachment_id: uuid.UUID, expires: int) -> str:
    message = f"attachment-download:{attachment_id}:{expires}".encode()
    return hmac.new(settings.jwt_secret_key.encode(), message, hashlib.sha256).hexdigest()


def signed_download_url(attachment_id: uuid.UUID) -> str:
    expires = int(time.time()) + settings.download_url_seconds
    return f"/attachments/{attachment_id}/download?expires={expires}&signature={_signature(attachment_id, expires)}"


def is_valid_signature(attachment_id: uuid.UUID, expires: int, signature: str) -> bool:
    if expires < time.time():
        return False
    # compare_digest takes the same time whatever the input, so the signature can't be guessed byte by byte.
    return hmac.compare_digest(_signature(attachment_id, expires), signature)
