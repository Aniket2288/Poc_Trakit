import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings
from app.core.exceptions import AuthenticationError

ACCESS = "access"
REFRESH = "refresh"

password_hasher = PasswordHasher()



def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# ---------- Tokens ----------

def create_access_token(user_id: uuid.UUID, workspace_id: uuid.UUID, role: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "jti": str(uuid.uuid4()),
        "type": ACCESS,
        "workspace_id": str(workspace_id),
        "role": role,
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: uuid.UUID, workspace_id: uuid.UUID) -> tuple[str, uuid.UUID, datetime]:
    now = datetime.now(timezone.utc)
    jti = uuid.uuid4()
    expires_at = now + timedelta(days=settings.refresh_token_days)
    claims = {
        "sub": str(user_id),
        "iat": now,
        "exp": expires_at,
        "jti": str(jti),
        "type": REFRESH,
        "workspace_id": str(workspace_id),
    }
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at


def decode_token(token: str, expected_type: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "iat", "exp", "jti", "type", "workspace_id"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token")          

    if claims["type"] != expected_type:
        raise AuthenticationError("Wrong token type")
    return claims
