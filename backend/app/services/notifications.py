"""Outbound notifications (currently: email via SMTP).

Deliberately tiny and dependency-free (uses stdlib ``smtplib``). If SMTP isn't
configured, ``send_email`` logs and returns ``False`` instead of raising — the
alert system still records that a drop happened, the operator just won't get a
push.

Adding WhatsApp / webhook delivery later: implement a ``send_webhook`` here and
branch on ``alert.channel`` in ``alert_service``.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config import get_settings

logger = logging.getLogger("flight_scheduler.notifications")


def send_email(to_address: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True on success, False if not sent."""
    settings = get_settings()
    if not settings.smtp_host:
        logger.info("SMTP not configured — skipping email to %s (%s)", to_address, subject)
        return False

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            if settings.smtp_port in (587, 25):
                smtp.starttls()
                smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        logger.info("Sent alert email to %s", to_address)
        return True
    except Exception as exc:  # noqa: BLE001 - notification failure is non-fatal
        logger.warning("Failed to send email to %s: %s", to_address, exc)
        return False


def send_webhook(url: str, payload: dict) -> bool:
    """POST a JSON payload to a webhook URL (for future WhatsApp/Zapier hooks)."""
    try:
        resp = httpx.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook POST to %s failed: %s", url, exc)
        return False
