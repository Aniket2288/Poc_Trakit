import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Membership, Role, Workspace


def slug_exists(db: Session, slug: str) -> bool:
    return db.scalar(select(Workspace.id).where(Workspace.slug == slug)) is not None


def create_workspace(db: Session, name: str, slug: str) -> Workspace:
    workspace = Workspace(name=name, slug=slug)
    db.add(workspace)
    db.flush()
    return workspace


def create_membership(db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID, role: Role) -> Membership:
    membership = Membership(user_id=user_id, workspace_id=workspace_id, role=role)
    db.add(membership)
    db.flush()
    return membership


def get_membership(db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID) -> Membership | None:
    return db.scalar(
        select(Membership).where(Membership.user_id == user_id, Membership.workspace_id == workspace_id)
    )


def get_first_membership(db: Session, user_id: uuid.UUID) -> Membership | None:
    """The workspace a user joined first. Used when login doesn't say which workspace."""
    return db.scalar(
        select(Membership).where(Membership.user_id == user_id).order_by(Membership.created_at).limit(1)
    )


def list_members(db: Session, workspace_id: uuid.UUID) -> list[Membership]:
    return list(
        db.scalars(
            select(Membership)
            .where(Membership.workspace_id == workspace_id)
            .options(selectinload(Membership.user))
            .order_by(Membership.created_at)
        )
    )
