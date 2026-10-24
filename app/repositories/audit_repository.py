import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def add(db: Session, entry: AuditLog) -> AuditLog:
    db.add(entry)
    db.flush()
    return entry


def list_for_workspace(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[AuditLog], int]:
    query = select(AuditLog).where(AuditLog.workspace_id == workspace_id)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(AuditLog.created_at.desc(), AuditLog.id).limit(limit).offset(offset))
    return list(rows), total
