import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class SentEmail(UUIDPrimaryKeyMixin, Base):
    """
    One row per email we have sent. The unique idempotency_key is what makes jobs safe to repeat:
    a retried or duplicated job finds its key already here and does not send a second time.
    """

    __tablename__ = "sent_emails"

    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)  # e.g. "assignment:<audit id>"
    to_email: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
