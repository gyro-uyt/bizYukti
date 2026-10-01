"""In-app notifications and OTP delivery (SMTP for email, webhook adapter for SMS)."""

import logging
import smtplib
import uuid
from email.message import EmailMessage

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Notification

log = logging.getLogger("bizyukti.notify")


def notify(db: Session, user_id: uuid.UUID | None, kind: str, title: str, body: str | None = None,
           link: str | None = None) -> None:
    if user_id:
        db.add(Notification(user_id=user_id, kind=kind, title=title[:160], body=(body or "")[:400] or None, link=link))


def deliver_otp(channel: str, destination: str, code: str) -> None:
    message = f"{code} is your BizYukti sign-in code. It expires in {settings.otp_ttl_minutes} minutes. Don't share it."
    if channel == "email" and settings.smtp_host:
        msg = EmailMessage()
        msg["Subject"] = f"{code} is your BizYukti code"
        msg["From"] = settings.smtp_from
        msg["To"] = destination
        msg.set_content(message)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return
    if channel == "phone" and settings.sms_webhook_url:
        r = httpx.post(settings.sms_webhook_url, json={"to": destination, "message": message},
                       headers={"Authorization": f"Bearer {settings.sms_webhook_token}"}, timeout=10)
        r.raise_for_status()
        return
    if settings.is_production:
        raise HTTPException(status_code=503, detail=f"Sign-in by {channel} isn't available right now. Try the other option.")
    log.info("DEV OTP for %s %s: %s", channel, destination, code)
