"""Putting work on the queue. Services call these AFTER db.commit(), so the worker always finds the data."""

import logging
import uuid

logger = logging.getLogger("trackit.jobs")


def enqueue_assignment_email(audit_id: uuid.UUID) -> None:
    from app.worker.tasks import send_assignment_email  # imported here so the web app starts even if Celery isn't configured

    try:
        send_assignment_email.delay(str(audit_id))
    except Exception:
        # The assignment is already saved. A queue outage must not turn that into a 500 for the user,
        # so we log it. (The fully reliable fix is an "outbox" table that a poller re-sends from.)
        logger.exception("could not enqueue assignment email audit_id=%s", audit_id)
