from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.membership import Membership
    from app.models.project import Project


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="workspace", passive_deletes=True)
    projects: Mapped[list["Project"]] = relationship(back_populates="workspace", passive_deletes=True)
