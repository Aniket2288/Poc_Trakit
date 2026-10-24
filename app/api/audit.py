import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_role
from app.core.database import get_db
from app.models import Role
from app.services import audit_service
from app.schemas.audit import AuditLogPage

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    entity_type: str | None = Query(None, examples=["issue"]),
    entity_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: CurrentUser = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Admin only. Newest first. Filter by entity_type and/or entity_id to see one thing's history."""
    items, total = audit_service.list_logs(
        db, current.workspace_id, entity_type=entity_type, entity_id=entity_id, limit=limit, offset=offset
    )
    return AuditLogPage(items=items, total=total, limit=limit, offset=offset)
