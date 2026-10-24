import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_role
from app.core.database import get_db
from app.models import Role
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])

# Who may do what
anyone = get_current_user                          # admin, member, viewer
editors = require_role(Role.ADMIN, Role.MEMBER)    # admin, member
admins = require_role(Role.ADMIN)                  # admin only


@router.get("", response_model=list[ProjectOut])
def list_projects(current: CurrentUser = Depends(anyone), db: Session = Depends(get_db)):
    return project_service.list_projects(db, current.workspace_id)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, current: CurrentUser = Depends(editors), db: Session = Depends(get_db)):
    return project_service.create_project(db, current.workspace_id, current.user_id, data)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, current: CurrentUser = Depends(anyone), db: Session = Depends(get_db)):
    return project_service.get_project(db, current.workspace_id, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: uuid.UUID, data: ProjectUpdate, current: CurrentUser = Depends(editors), db: Session = Depends(get_db)):
    return project_service.update_project(db, current.workspace_id, current.user_id, project_id, data)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: uuid.UUID, current: CurrentUser = Depends(admins), db: Session = Depends(get_db)):
    project_service.delete_project(db, current.workspace_id, current.user_id, project_id)
