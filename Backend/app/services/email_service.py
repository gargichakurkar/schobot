from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailNotConfiguredError(RuntimeError):
    pass


class EmailService:
    @property
    def is_configured(self) -> bool:
        return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)

    def send_otp_email(self, to_email: str, otp_code: str) -> bool:
        if not self.is_configured:
            raise EmailNotConfiguredError(
                "Email delivery service is not configured on this server. "
                "Account recovery requires SMTP environment variables "
                "(SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL)."
            )

        try:
            msg = EmailMessage()
            msg["Subject"] = f"Your Schobot Account Verification Code: {otp_code}"
            msg["From"] = settings.smtp_from_email or "noreply@schobot.com"
            msg["To"] = to_email
            msg.set_content(
                f"Hello,\n\n"
                f"Your one-time verification code (OTP) for Schobot (ScholarMate AI) is:\n\n"
                f"  {otp_code}\n\n"
                f"This code will expire in 10 minutes. If you did not request this code, please ignore this email.\n\n"
                f"— The Schobot Team"
            )

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
            return True
        except Exception as exc:
            logger.error("Failed to send OTP email to %s: %s", to_email, exc)
            raise RuntimeError(f"Failed to deliver verification email: {exc}") from exc


_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
