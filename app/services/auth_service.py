import re
import secrets
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError, PermissionDeniedError
from app.models import Role, User
from app.repositories import refresh_token_repository, user_repository, workspace_repository
from app.schemas.auth import LoginRequest, SignupRequest, TokenPair
from app.services import audit_service

# Checked when the email doesn't exist, so a wrong email takes as long as a wrong password.
# Otherwise an attacker could time the response to learn which emails have accounts.
_DUMMY_HASH = security.hash_password("not-a-real-password")


def signup(db: Session, data: SignupRequest) -> TokenPair:
    """Create a user and a new workspace with that user as its admin, then log them in."""
    email = data.email.lower()
    if user_repository.get_by_email(db, email):
        raise ConflictError("An account with this email already exists")

    try:
        user = user_repository.create(db, email, security.hash_password(data.password), data.full_name)
        workspace = workspace_repository.create_workspace(db, data.workspace_name, _unique_slug(db, data.workspace_name))
        workspace_repository.create_membership(db, user.id, workspace.id, Role.ADMIN)
        audit_service.record(
            db, workspace_id=workspace.id, actor_id=user.id, action="workspace.created", entity_type="workspace",
            entity_id=workspace.id, after={"name": workspace.name, "slug": workspace.slug, "owner": str(user.id)},
        )
        tokens = _issue_tokens(db, user.id, workspace.id, Role.ADMIN)
        db.commit()
    except IntegrityError:
        # Two signups with the same email at the same moment: the unique index stops the second one.
        db.rollback()
        raise ConflictError("An account with this email already exists")
    return tokens


def login(db: Session, data: LoginRequest) -> TokenPair:
    user = user_repository.get_by_email(db, data.email.lower())

    if user is None:
        security.verify_password(data.password, _DUMMY_HASH)
        raise AuthenticationError("Invalid email or password")
    if not security.verify_password(data.password, user.password_hash):
        raise AuthenticationError("Invalid email or password")
    if not user.is_active:
        raise AuthenticationError("This account is disabled")

    if data.workspace_id:
        membership = workspace_repository.get_membership(db, user.id, data.workspace_id)
    else:
        membership = workspace_repository.get_first_membership(db, user.id)
    if membership is None:
        raise PermissionDeniedError("You are not a member of this workspace")

    tokens = _issue_tokens(db, user.id, membership.workspace_id, membership.role)
    db.commit()
    return tokens


def refresh(db: Session, refresh_token: str) -> TokenPair:
    """Rotation: swap a valid refresh token for a brand-new pair, and retire the old one."""
    claims = security.decode_token(refresh_token, security.REFRESH)
    stored = refresh_token_repository.get_for_update(db, uuid.UUID(claims["jti"]))

    if stored is None:
        raise AuthenticationError("Invalid token")

    if stored.revoked_at is not None:
        # This token was already used or logged out. If someone is presenting it again, it may have
        # been stolen, so we log the user out everywhere. They will have to log in again.
        refresh_token_repository.revoke_all_for_user(db, stored.user_id)
        db.commit()
        raise AuthenticationError("Refresh token has already been used")

    user = user_repository.get_by_id(db, stored.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("This account is disabled")

    # Read the role from the database, not the old token: an admin may have changed it since.
    membership = workspace_repository.get_membership(db, user.id, stored.workspace_id)
    if membership is None:
        raise PermissionDeniedError("You are no longer a member of this workspace")

    refresh_token_repository.revoke(db, stored)
    tokens = _issue_tokens(db, user.id, stored.workspace_id, membership.role)
    db.commit()
    return tokens


def logout(db: Session, refresh_token: str) -> None:
    claims = security.decode_token(refresh_token, security.REFRESH)
    stored = refresh_token_repository.get(db, uuid.UUID(claims["jti"]))
    if stored is not None and stored.revoked_at is None:
        refresh_token_repository.revoke(db, stored)
        db.commit()


def get_active_user(db: Session, user_id: uuid.UUID) -> User:
    user = user_repository.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("This account is disabled")
    return user


# ---------- Helpers ----------

def _issue_tokens(db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID, role: Role) -> TokenPair:
    access_token = security.create_access_token(user_id, workspace_id, role.value)
    refresh_token, jti, expires_at = security.create_refresh_token(user_id, workspace_id)
    refresh_token_repository.add(db, jti, user_id, workspace_id, expires_at)
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_minutes * 60,
    )


def _unique_slug(db: Session, name: str) -> str:
    """'My Team!' -> 'my-team'. Adds a short random ending if that slug is already taken."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    slug = base
    while workspace_repository.slug_exists(db, slug):
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug
