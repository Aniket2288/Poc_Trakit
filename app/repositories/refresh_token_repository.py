import uuid
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import RefreshToken


def add(db: Session, jti: uuid.UUID, user_id: uuid.UUID, workspace_id: uuid.UUID, expires_at: datetime) -> None:
    db.add(RefreshToken(jti=jti, user_id=user_id, workspace_id=workspace_id, expires_at=expires_at))
    db.flush()


def get(db: Session, jti: uuid.UUID) -> RefreshToken | None:
    return db.get(RefreshToken, jti)


def get_for_update(db: Session, jti: uuid.UUID) -> RefreshToken | None:
    """Same as get, but locks the row until commit, so two refreshes with one token can't both succeed."""
    return db.get(RefreshToken, jti, with_for_update=True)


def revoke(db: Session, token: RefreshToken) -> None:
    token.revoked_at = datetime.now(timezone.utc)
    db.flush()


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    """Revoke every still-active refresh token the user has."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
