import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project


def list_for_workspace(db: Session, workspace_id: uuid.UUID) -> list[Project]:
    return list(db.scalars(select(Project).where(Project.workspace_id == workspace_id).order_by(Project.created_at)))


def get_in_workspace(db: Session, project_id: uuid.UUID, workspace_id: uuid.UUID) -> Project | None:
    # Always filter by workspace too, so nobody can open another workspace's project by guessing its id.
    return db.scalar(select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id))


def key_exists(db: Session, workspace_id: uuid.UUID, key: str) -> bool:
    return db.scalar(select(Project.id).where(Project.workspace_id == workspace_id, Project.key == key)) is not None


def create(db: Session, workspace_id: uuid.UUID, key: str, name: str, description: str | None, created_by: uuid.UUID) -> Project:
    project = Project(workspace_id=workspace_id, key=key, name=name, description=description, created_by=created_by)
    db.add(project)
    db.flush()
    return project


def delete(db: Session, project: Project) -> None:
    db.delete(project)
    db.flush()
