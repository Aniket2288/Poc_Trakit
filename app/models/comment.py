import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Comment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "comments"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # empty = never edited

    author: Mapped["User"] = relationship()


class CommentRevision(UUIDPrimaryKeyMixin, Base):
    """The text a comment had BEFORE an edit. One row per edit, so the full history is kept."""

    __tablename__ = "comment_revisions"

    comment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    edited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Attachment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "attachments"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    original_name: Mapped[str] = mapped_column(String(255))  # cleaned, only used for display and download
    content_type: Mapped[str] = mapped_column(String(100))   # what WE detected from the bytes
    size_bytes: Mapped[int]
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)  # random name on disk
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
