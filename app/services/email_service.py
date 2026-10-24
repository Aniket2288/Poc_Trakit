import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("trackit.email")


class EmailDeliveryError(Exception):
    """Sending failed for a reason that may go away (server down, timeout). The job retries on this."""


def deliver(to: str, subject: str, body: str) -> None:
    if settings.email_backend == "console":
        # Local development: the "email" is just a log line in the worker's output.
        logger.info("EMAIL to=%s subject=%r\n%s", to, subject, body)
        return

    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError(str(exc)) from exc
