import enum
import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Column, Date, Enum, ForeignKey, Index, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class IssueStatus(str, enum.Enum):
    BACKLOG = "backlog"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class IssuePriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


def _values(enum_class):
    return [member.value for member in enum_class]


# Many-to-many link: one issue has many labels, one label is on many issues.
issue_labels = Table(
    "issue_labels",
    Base.metadata,
    Column("issue_id", ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
)


class Label(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(30))


class Issue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("project_id", "number"),
        Index("ix_issues_workspace_status", "workspace_id", "status"),
    )

    # workspace_id is copied from the project so every list query can filter by tenant without a join.
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    number: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, name="issue_status", values_callable=_values), default=IssueStatus.BACKLOG
    )
    priority: Mapped[IssuePriority] = mapped_column(
        Enum(IssuePriority, name="issue_priority", values_callable=_values), default=IssuePriority.MEDIUM
    )
    due_date: Mapped[date | None] = mapped_column(Date)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    project: Mapped["Project"] = relationship()
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assignee_id])
    labels: Mapped[list[Label]] = relationship(secondary=issue_labels)
