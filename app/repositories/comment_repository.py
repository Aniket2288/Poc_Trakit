import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Attachment, Comment, CommentRevision


def add(db: Session, obj):
    db.add(obj)
    db.flush()
    return obj


def get_comment(db: Session, comment_id: uuid.UUID, workspace_id: uuid.UUID) -> Comment | None:
    return db.scalar(select(Comment).where(Comment.id == comment_id, Comment.workspace_id == workspace_id))


def list_comments(db: Session, issue_id: uuid.UUID) -> list[Comment]:
    # selectinload: load every author in ONE extra query instead of one per comment.
    return list(
        db.scalars(select(Comment).where(Comment.issue_id == issue_id).options(selectinload(Comment.author)).order_by(Comment.created_at, Comment.id))
    )


def list_revisions(db: Session, comment_id: uuid.UUID) -> list[CommentRevision]:
    return list(db.scalars(select(CommentRevision).where(CommentRevision.comment_id == comment_id).order_by(CommentRevision.created_at.desc(), CommentRevision.id)))


def get_attachment(db: Session, attachment_id: uuid.UUID) -> Attachment | None:
    return db.get(Attachment, attachment_id)


def list_attachments(db: Session, issue_id: uuid.UUID) -> list[Attachment]:
    return list(db.scalars(select(Attachment).where(Attachment.issue_id == issue_id).order_by(Attachment.created_at, Attachment.id)))
