import enum
import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories import audit_repository


def snapshot(obj, fields: list[str]) -> dict:
    """Copy some fields of a model into a plain dict that can be stored as JSON."""
    return {field: _to_json(getattr(obj, field)) for field in fields}


def record(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditLog:
    """
    Add an audit row to the CURRENT transaction. It does not commit.

    The calling service commits once, so the change and its audit row are saved together
    or not at all. A change can never happen without its log entry.
    """
    return audit_repository.add(
        db,
        AuditLog(
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
        ),
    )


def _to_json(value):
    if isinstance(value, (uuid.UUID, datetime, date)):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, list):
        return [_to_json(v) for v in value]
    return value


def list_logs(db: Session, workspace_id: uuid.UUID, *, entity_type, entity_id, limit: int, offset: int):
    return audit_repository.list_for_workspace(
        db, workspace_id, entity_type=entity_type, entity_id=entity_id, limit=limit, offset=offset
    )
