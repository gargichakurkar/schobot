from __future__ import annotations

import logging
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class EmailNotConfiguredError(RuntimeError):
    pass


class EmailService:
    @property
    def is_configured(self) -> bool:
        return bool(settings.resend_api_key and settings.resend_api_key.strip())

    def send_otp_email(self, to_email: str, otp_code: str) -> bool:
        if not self.is_configured:
            raise EmailNotConfiguredError(
                "Email delivery service is not configured on this server. "
                "Account recovery requires Resend API configuration "
                "(RESEND_API_KEY, RESEND_FROM_EMAIL)."
            )

        try:
            subject = f"Your Schobot Account Verification Code: {otp_code}"
            text_content = (
                f"Hello,\n\n"
                f"Your one-time verification code (OTP) for Schobot (ScholarMate AI) is:\n\n"
                f"  {otp_code}\n\n"
                f"This code will expire in 10 minutes. If you did not request this code, please ignore this email.\n\n"
                f"— The Schobot Team"
            )
            html_content = (
                f"<div style='font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; border: 1px solid #E5E7EB; border-radius: 12px; background: #FFFFFF;'>"
                f"<h2 style='color: #4F46E5; margin-top: 0;'>ScholarMate AI Verification</h2>"
                f"<p style='color: #374151; font-size: 15px;'>Hello,</p>"
                f"<p style='color: #374151; font-size: 15px;'>Your one-time verification code (OTP) for Schobot is:</p>"
                f"<div style='background: #F3F4F6; padding: 16px; border-radius: 8px; font-size: 28px; font-weight: bold; letter-spacing: 6px; text-align: center; color: #111827; margin: 24px 0;'>"
                f"{otp_code}"
                f"</div>"
                f"<p style='color: #6B7280; font-size: 13px;'>This code will expire in 10 minutes. If you did not request this verification code, you can safely ignore this email.</p>"
                f"<hr style='border: none; border-top: 1px solid #E5E7EB; margin: 24px 0;' />"
                f"<p style='color: #9CA3AF; font-size: 12px; margin-bottom: 0;'>— The Schobot Team</p>"
                f"</div>"
            )

            headers = {
                "Authorization": f"Bearer {settings.resend_api_key.strip()}",
                "Content-Type": "application/json",
            }
            payload = {
                "from": settings.resend_from_email or "Schobot <onboarding@resend.dev>",
                "to": [to_email],
                "subject": subject,
                "text": text_content,
                "html": html_content,
            }

            with httpx.Client(timeout=15.0) as client:
                response = client.post(RESEND_API_URL, json=payload, headers=headers)
                if response.status_code not in (200, 201):
                    logger.error(
                        "Resend API error sending email to %s: HTTP %s",
                        to_email,
                        response.status_code,
                    )
                    raise RuntimeError(f"Resend API returned HTTP {response.status_code}")

            return True
        except EmailNotConfiguredError:
            raise
        except Exception as exc:
            logger.error("Failed to send OTP email to %s: %s", to_email, exc)
            raise RuntimeError(f"Failed to deliver verification email: {exc}") from exc


_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
