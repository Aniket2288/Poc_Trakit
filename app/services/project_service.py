import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Project
from app.repositories import project_repository
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services import audit_service

AUDITED_FIELDS = ["key", "name", "description"]


def list_projects(db: Session, workspace_id: uuid.UUID) -> list[Project]:
    return project_repository.list_for_workspace(db, workspace_id)


def get_project(db: Session, workspace_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = project_repository.get_in_workspace(db, project_id, workspace_id)
    if project is None:
        # 404, not 403: we don't even admit that a project in another workspace exists.
        raise NotFoundError("Project not found")
    return project


def create_project(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID, data: ProjectCreate) -> Project:
    key = data.key.upper()
    if project_repository.key_exists(db, workspace_id, key):
        raise ConflictError(f"A project with key {key} already exists")

    project = project_repository.create(db, workspace_id, key, data.name, data.description, user_id)
    audit_service.record(
        db, workspace_id=workspace_id, actor_id=user_id, action="project.created", entity_type="project",
        entity_id=project.id, after=audit_service.snapshot(project, AUDITED_FIELDS),
    )
    db.commit()
    return project


def update_project(db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
    project = get_project(db, workspace_id, project_id)
    before = audit_service.snapshot(project, AUDITED_FIELDS)

    # exclude_unset: only change the fields the client actually sent.
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    audit_service.record(
        db, workspace_id=workspace_id, actor_id=actor_id, action="project.updated", entity_type="project",
        entity_id=project.id, before=before, after=audit_service.snapshot(project, AUDITED_FIELDS),
    )
    db.commit()
    return project


def delete_project(db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, project_id: uuid.UUID) -> None:
    project = get_project(db, workspace_id, project_id)
    # The row is about to be hard-deleted, so the audit log keeps the last copy of it.
    audit_service.record(
        db, workspace_id=workspace_id, actor_id=actor_id, action="project.deleted", entity_type="project",
        entity_id=project.id, before=audit_service.snapshot(project, AUDITED_FIELDS),
    )
    project_repository.delete(db, project)
    db.commit()
