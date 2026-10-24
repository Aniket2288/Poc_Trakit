from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.database import get_db
from app.schemas.user import MeResponse
from app.services import auth_service

router = APIRouter(tags=["users"])


@router.get("/me", response_model=MeResponse)
def me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    # The token check above needed no database. Loading the profile does, because /me returns it.
    user = auth_service.get_active_user(db, current.user_id)
    return MeResponse(user=user, workspace_id=current.workspace_id, role=current.role)
