import uuid
from contextlib import contextmanager
from datetime import date

import pytest
from celery.schedules import crontab

from app.models import AuditLog, SentEmail
from app.services import email_service, notification_service
from app.services.email_service import EmailDeliveryError
from app.worker import tasks
from app.worker.celery_app import celery_app
from tests.conftest import add_member_and_login, auth, signup


@pytest.fixture
def outbox(monkeypatch):
    """Capture emails instead of sending them."""
    sent = []
    monkeypatch.setattr(email_service, "deliver", lambda to, subject, body: sent.append({"to": to, "subject": subject, "body": body}))
    return sent


@pytest.fixture
def ctx(client):
    admin = signup(client, "admin")
    member = add_member_and_login(client, admin, "member")
    h = auth(admin["access_token"])
    project = client.post("/projects", json={"key": "TRK", "name": "TrackIt"}, headers=h).json()
    return {"admin": admin, "member": member, "h": h, "project": project}


def create_issue(client, ctx, **fields):
    res = client.post(f"/projects/{ctx['project']['id']}/issues", json={"title": "Fix login", **fields}, headers=ctx["h"])
    assert res.status_code == 201, res.text
    return res.json()


def assign(client, ctx, issue, user_id):
    return client.post(f"/issues/{issue['id']}/assign", json={"assignee_id": user_id}, headers=ctx["h"])


# ---------- Enqueueing ----------

def test_assigning_enqueues_one_job_after_commit(client, ctx, enqueued, db):
    issue = create_issue(client, ctx)
    assign(client, ctx, issue, ctx["member"]["user_id"])
    assert len(enqueued) == 1
    # The job carries the id of the committed audit event.
    assert db.get(AuditLog, enqueued[0]).action == "issue.assigned"


def test_creating_with_an_assignee_also_enqueues(client, ctx, enqueued):
    create_issue(client, ctx, assignee_id=ctx["member"]["user_id"])
    assert len(enqueued) == 1


def test_reassigning_to_the_same_person_or_unassigning_enqueues_nothing(client, ctx, enqueued):
    issue = create_issue(client, ctx, assignee_id=ctx["member"]["user_id"])
    assign(client, ctx, issue, ctx["member"]["user_id"])
    assign(client, ctx, issue, None)
    assert len(enqueued) == 1


# ---------- The assignment email job ----------

def test_assignment_email_goes_to_the_assignee(client, ctx, enqueued, outbox, db):
    issue = create_issue(client, ctx, assignee_id=ctx["member"]["user_id"])
    assert notification_service.send_assignment_email(db, enqueued[0]) == "sent"
    assert outbox[0]["to"] == ctx["member"]["email"]
    assert issue["key"] in outbox[0]["subject"]


def test_running_the_same_job_twice_sends_only_once(client, ctx, enqueued, outbox, db):
    """Idempotency: a retry or a duplicate delivery from the queue must not email twice."""
    create_issue(client, ctx, assignee_id=ctx["member"]["user_id"])
    first = notification_service.send_assignment_email(db, enqueued[0])
    second = notification_service.send_assignment_email(db, enqueued[0])
    assert (first, second) == ("sent", "skipped: already sent")
    assert len(outbox) == 1
    assert db.query(SentEmail).count() == 1


def test_stale_job_is_skipped_after_reassignment(client, ctx, enqueued, outbox, db):
    issue = create_issue(client, ctx, assignee_id=ctx["member"]["user_id"])
    other = add_member_and_login(client, ctx["admin"], "member", name="other")
    assign(client, ctx, issue, other["user_id"])
    old_job, new_job = enqueued
    assert notification_service.send_assignment_email(db, old_job) == "skipped: stale, the issue was reassigned since"
    assert notification_service.send_assignment_email(db, new_job) == "sent"
    assert [m["to"] for m in outbox] == [other["email"]]


def test_failed_send_releases_the_claim_so_the_retry_can_send(client, ctx, enqueued, monkeypatch, db):
    create_issue(client, ctx, assignee_id=ctx["member"]["user_id"])

    def broken(to, subject, body):
        raise EmailDeliveryError("mail server down")

    monkeypatch.setattr(email_service, "deliver", broken)
    with pytest.raises(EmailDeliveryError):
        notification_service.send_assignment_email(db, enqueued[0])
    assert db.query(SentEmail).count() == 0  # nothing recorded, so it isn't "already sent"

    delivered = []
    monkeypatch.setattr(email_service, "deliver", lambda to, subject, body: delivered.append(to))
    assert notification_service.send_assignment_email(db, enqueued[0]) == "sent"
    assert delivered == [ctx["member"]["email"]]


def test_unknown_event_is_skipped(db, outbox):
    assert notification_service.send_assignment_email(db, uuid.uuid4()).startswith("skipped")
    assert outbox == []


# ---------- The daily overdue digest ----------

def test_digest_sends_one_email_per_person_with_only_open_overdue_issues(client, ctx, outbox, db):
    member_id = ctx["member"]["user_id"]
    create_issue(client, ctx, title="Late A", assignee_id=member_id, due_date="2026-01-10")
    create_issue(client, ctx, title="Late B", assignee_id=member_id, due_date="2026-01-12")
    create_issue(client, ctx, title="Not due yet", assignee_id=member_id, due_date="2027-01-01")
    create_issue(client, ctx, title="Late but nobody assigned", due_date="2026-01-01")
    done = create_issue(client, ctx, title="Late but done", assignee_id=member_id, due_date="2026-01-01")
    for status in ["in_progress", "review", "done"]:
        client.post(f"/issues/{done['id']}/transition", json={"status": status}, headers=ctx["h"])

    assert notification_service.send_overdue_digest(db, date(2026, 6, 1)) == 1
    body = outbox[0]["body"]
    assert outbox[0]["to"] == ctx["member"]["email"]
    assert "Late A" in body and "Late B" in body
    assert "Not due yet" not in body and "nobody assigned" not in body and "Late but done" not in body


def test_digest_twice_on_the_same_day_sends_once_but_next_day_sends_again(client, ctx, outbox, db):
    create_issue(client, ctx, assignee_id=ctx["member"]["user_id"], due_date="2026-01-10")
    assert notification_service.send_overdue_digest(db, date(2026, 6, 1)) == 1
    assert notification_service.send_overdue_digest(db, date(2026, 6, 1)) == 0
    assert notification_service.send_overdue_digest(db, date(2026, 6, 2)) == 1
    assert len(outbox) == 2


# ---------- The Celery wiring ----------

def test_celery_task_runs_the_job_with_its_own_session(client, ctx, enqueued, outbox, db, monkeypatch):
    create_issue(client, ctx, assignee_id=ctx["member"]["user_id"])

    @contextmanager
    def test_session():
        yield db

    monkeypatch.setattr(tasks, "session_scope", test_session)
    result = tasks.send_assignment_email.apply(args=[str(enqueued[0])])  # runs the task in-process, no broker
    assert result.get() == "sent"
    assert len(outbox) == 1


def test_tasks_retry_with_backoff_only_on_temporary_errors():
    task = celery_app.tasks["trackit.send_assignment_email"]
    assert task.max_retries == 5
    assert task.retry_backoff == 2
    assert EmailDeliveryError in task.autoretry_for


def test_worker_settings_make_crashes_safe():
    conf = celery_app.conf
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1


def test_digest_is_scheduled_daily_at_9():
    schedule = celery_app.conf.beat_schedule["daily-overdue-digest"]
    assert schedule["task"] == "trackit.send_overdue_digest"
    assert schedule["schedule"] == crontab(hour=9, minute=0)
