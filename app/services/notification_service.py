"""
The work the background jobs do. Plain functions that take a database session, so tests can call
them directly. app/worker/tasks.py wraps them as Celery tasks.
"""

import logging
import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AuditLog, Issue, SentEmail, User
from app.repositories import issue_repository
from app.services import email_service

logger = logging.getLogger("trackit.jobs")


def send_assignment_email(db: Session, audit_id: uuid.UUID) -> str:
    """Email the person an issue was assigned to. Returns what happened, which tests and logs use."""
    event = db.get(AuditLog, audit_id)
    if event is None or event.action != "issue.assigned":
        return "skipped: no such assignment event"

    assignee_id = (event.after or {}).get("assignee_id")
    issue = db.get(Issue, event.entity_id)
    if issue is None or assignee_id is None:
        return "skipped: issue gone or it was an unassign"
    if str(issue.assignee_id) != assignee_id:
        # The job sat in the queue and the issue was reassigned meanwhile. That newer assignment has its own job.
        return "skipped: stale, the issue was reassigned since"

    assignee = db.get(User, issue.assignee_id)
    key = issue.project.key
    subject = f"[TrackIt] You were assigned {key}-{issue.number}: {issue.title}"
    body = (
        f"Hi {assignee.full_name},\n\n"
        f"You were assigned {key}-{issue.number}: {issue.title}\n"
        f"Priority: {issue.priority.value}\n"
        f"Due: {issue.due_date or 'no due date'}\n\n"
        f"Open TrackIt: {settings.frontend_url}\n"
    )
    sent = send_once(db, f"assignment:{audit_id}", assignee.email, subject, body)
    return "sent" if sent else "skipped: already sent"


def send_overdue_digest(db: Session, today: date) -> int:
    """One email per person listing their open issues past their due date. Returns how many emails were sent."""
    by_assignee: dict[uuid.UUID, list[Issue]] = defaultdict(list)
    for issue in issue_repository.list_overdue(db, today):
        by_assignee[issue.assignee_id].append(issue)

    sent = 0
    for assignee_id, issues in by_assignee.items():
        user = db.get(User, assignee_id)
        lines = [f"- {i.project.key}-{i.number}: {i.title} (due {i.due_date}, {i.status.value})" for i in issues]
        body = f"Hi {user.full_name},\n\nThese issues assigned to you are overdue:\n" + "\n".join(lines) + f"\n\n{settings.frontend_url}\n"
        # One key per person per day: running the digest twice on the same day sends nothing new.
        if send_once(db, f"overdue-digest:{assignee_id}:{today.isoformat()}", user.email, f"[TrackIt] {len(issues)} overdue issue(s)", body):
            sent += 1
    return sent


def send_once(db: Session, idempotency_key: str, to: str, subject: str, body: str) -> bool:
    """
    Send an email at most once per idempotency key. Returns False if it was already sent.

    1. Insert the SentEmail row (the "claim"). If the key exists, the unique index rejects it: already sent.
    2. Send the email.
    3. Commit. If sending raised, the claim is rolled back, so the retry can try again.

    If two workers race on the same key, the second INSERT waits on the first one's row and then fails.
    The one gap: a crash AFTER sending but BEFORE commit means the retry sends again. That is
    "at least once"; true exactly-once delivery isn't possible with an external mail server.
    """
    try:
        db.add(SentEmail(idempotency_key=idempotency_key, to_email=to, subject=subject))
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("email already sent, skipping key=%s", idempotency_key)
        return False

    try:
        email_service.deliver(to, subject, body)
    except Exception:
        db.rollback()  # drop the claim so the retry can send
        raise
    db.commit()
    return True
