import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core import storage
from app.core.config import settings
from app.core.exceptions import NotFoundError, PermissionDeniedError, UnprocessableError
from app.models import Attachment, Comment, CommentRevision
from app.repositories import comment_repository
from app.services import audit_service, issue_service

# ---------- Comments ----------


def add_comment(db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, issue_id: uuid.UUID, body: str) -> Comment:
    issue = issue_service.get_issue(db, workspace_id, issue_id)  # 404 if not in this workspace
    comment = comment_repository.add(db, Comment(workspace_id=workspace_id, issue_id=issue.id, author_id=actor_id, body=body))
    audit_service.record(
        db, workspace_id=workspace_id, actor_id=actor_id, action="comment.created", entity_type="comment",
        entity_id=comment.id, after={"issue_id": str(issue.id), "body": body},
    )
    db.commit()
    return comment


def list_comments(db: Session, workspace_id: uuid.UUID, issue_id: uuid.UUID) -> list[Comment]:
    issue_service.get_issue(db, workspace_id, issue_id)
    return comment_repository.list_comments(db, issue_id)


def edit_comment(db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, comment_id: uuid.UUID, body: str) -> Comment:
    comment = _get_comment(db, workspace_id, comment_id)
    if comment.author_id != actor_id:
        raise PermissionDeniedError("You can only edit your own comments")
    if body == comment.body:
        return comment  # nothing changed, so no new revision

    # Keep the OLD text before overwriting it. That row is the edit history.
    # created_at comes from Python, not Postgres now(), which is frozen for the whole transaction.
    now = datetime.now(timezone.utc)
    comment_repository.add(db, CommentRevision(comment_id=comment.id, body=comment.body, edited_by=actor_id, created_at=now))
    audit_service.record(
        db, workspace_id=workspace_id, actor_id=actor_id, action="comment.edited", entity_type="comment",
        entity_id=comment.id, before={"body": comment.body}, after={"body": body},
    )
    comment.body = body
    comment.edited_at = now
    db.commit()
    return comment


def comment_history(db: Session, workspace_id: uuid.UUID, comment_id: uuid.UUID) -> list[CommentRevision]:
    comment = _get_comment(db, workspace_id, comment_id)
    return comment_repository.list_revisions(db, comment.id)


def _get_comment(db: Session, workspace_id: uuid.UUID, comment_id: uuid.UUID) -> Comment:
    comment = comment_repository.get_comment(db, comment_id, workspace_id)
    if comment is None:
        raise NotFoundError("Comment not found")
    return comment


# ---------- Attachments ----------


def upload_attachment(db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, issue_id: uuid.UUID, filename: str | None, data: bytes) -> Attachment:
    issue = issue_service.get_issue(db, workspace_id, issue_id)

    if len(data) == 0:
        raise UnprocessableError("The file is empty")
    if len(data) > settings.max_upload_bytes:
        raise UnprocessableError(f"The file is too large. The limit is {settings.max_upload_bytes // (1024 * 1024)} MB")

    content_type = storage.detect_type(data[:2048])
    if content_type not in storage.ALLOWED_TYPES:
        raise UnprocessableError("This file type is not allowed. Upload PNG, JPEG, GIF, PDF or plain text")

    key = storage.save(data)  # the file is written first; if the DB step fails, an orphan file is the only cost
    attachment = comment_repository.add(
        db,
        Attachment(
            workspace_id=workspace_id, issue_id=issue.id, uploaded_by=actor_id, original_name=storage.clean_filename(filename),
            content_type=content_type, size_bytes=len(data), storage_key=key,
        ),
    )
    audit_service.record(
        db, workspace_id=workspace_id, actor_id=actor_id, action="attachment.uploaded", entity_type="attachment",
        entity_id=attachment.id, after={"issue_id": str(issue.id), "name": attachment.original_name, "type": content_type, "size": len(data)},
    )
    db.commit()
    return attachment


def list_attachments(db: Session, workspace_id: uuid.UUID, issue_id: uuid.UUID) -> list[Attachment]:
    issue_service.get_issue(db, workspace_id, issue_id)
    return comment_repository.list_attachments(db, issue_id)


def attachment_for_download(db: Session, attachment_id: uuid.UUID, expires: int, signature: str) -> Attachment:
    # The signature IS the permission: only someone who could list the issue's attachments got this link.
    if not storage.is_valid_signature(attachment_id, expires, signature):
        raise PermissionDeniedError("This download link is invalid or has expired")
    attachment = comment_repository.get_attachment(db, attachment_id)
    if attachment is None:
        raise NotFoundError("Attachment not found")
    return attachment
