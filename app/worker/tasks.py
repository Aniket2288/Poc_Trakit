import logging
import uuid
from contextlib import contextmanager
from datetime import date

from app.core.database import SessionLocal
from app.services import notification_service
from app.services.email_service import EmailDeliveryError
from app.worker.celery_app import celery_app

logger = logging.getLogger("trackit.jobs")

# Shared retry policy: retry only on errors that can go away, wait 2s, 4s, 8s ... (max 10 min), give up after 5.
RETRY_POLICY = dict(
    autoretry_for=(EmailDeliveryError, ConnectionError),
    retry_backoff=2,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)


@contextmanager
def session_scope():
    """Each job gets its own database session, separate from any web request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@celery_app.task(name="trackit.send_assignment_email", **RETRY_POLICY)
def send_assignment_email(audit_id: str) -> str:
    with session_scope() as db:
        result = notification_service.send_assignment_email(db, uuid.UUID(audit_id))
    logger.info("assignment email job audit_id=%s result=%s", audit_id, result)
    return result


@celery_app.task(name="trackit.send_overdue_digest", **RETRY_POLICY)
def send_overdue_digest(today: str | None = None) -> int:
    day = date.fromisoformat(today) if today else date.today()
    with session_scope() as db:
        sent = notification_service.send_overdue_digest(db, day)
    logger.info("overdue digest job day=%s emails_sent=%s", day, sent)
    return sent
