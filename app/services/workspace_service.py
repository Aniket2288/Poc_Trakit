import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Membership
from app.repositories import user_repository, workspace_repository
from app.schemas.workspace import AddMemberRequest
from app.services import audit_service


def add_member(db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, data: AddMemberRequest) -> Membership:
    user = user_repository.get_by_email(db, data.email.lower())
    if user is None:
        raise NotFoundError("No user with that email. They need to sign up first")

    if workspace_repository.get_membership(db, user.id, workspace_id):
        raise ConflictError("This user is already in the workspace")

    membership = workspace_repository.create_membership(db, user.id, workspace_id, data.role)
    audit_service.record(
        db, workspace_id=workspace_id, actor_id=actor_id, action="member.added", entity_type="membership",
        entity_id=membership.id, after=audit_service.snapshot(membership, ["user_id", "role"]),
    )
    db.commit()
    return membership


def list_members(db: Session, workspace_id: uuid.UUID):
    return workspace_repository.list_members(db, workspace_id)
