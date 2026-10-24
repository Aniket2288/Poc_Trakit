from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_role
from app.core.database import get_db
from app.models import Role
from app.schemas.workspace import AddMemberRequest, MemberDetail, MemberOut
from app.services import workspace_service

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.post("/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(data: AddMemberRequest, current: CurrentUser = Depends(require_role(Role.ADMIN)), db: Session = Depends(get_db)):
    return workspace_service.add_member(db, current.workspace_id, current.user_id, data)


@router.get("/members", response_model=list[MemberDetail])
def list_members(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    members = workspace_service.list_members(db, current.workspace_id)
    return [MemberDetail(user_id=m.user_id, email=m.user.email, full_name=m.user.full_name, role=m.role) for m in members]
