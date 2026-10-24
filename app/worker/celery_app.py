from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging as celery_setup_logging

from app.core.config import settings
from app.core.logging import setup_logging

celery_app = Celery("trackit", broker=settings.redis_url, include=["app.worker.tasks"])

celery_app.conf.update(
    # Remove a job from the queue only AFTER it finishes. If the worker crashes mid-job, Redis hands it out again.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Take one job at a time, so a crash can only ever affect the job in hand.
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    # If Redis is unreachable, give up publishing quickly instead of hanging the web request.
    task_publish_retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.5},
    timezone="Asia/Kolkata",
    beat_schedule={
        "daily-overdue-digest": {
            "task": "trackit.send_overdue_digest",
            "schedule": crontab(hour=9, minute=0),  # every day at 09:00 IST
        },
    },
)


@celery_setup_logging.connect
def use_json_logs(**kwargs):
    """The worker writes the same JSON log lines as the API."""
    setup_logging(settings.log_level)
