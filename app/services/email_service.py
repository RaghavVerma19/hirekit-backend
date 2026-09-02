from typing import Any, Dict, Optional
import httpx
import structlog
from app.core.config import settings

logger = structlog.get_logger()


class EmailService:
    @staticmethod
    async def _send(
        to_email: str, subject: str, html_content: str, text_content: Optional[str] = None
    ) -> bool:
        """Deliver email via SendGrid REST API or log in local test environments."""
        if settings.SENDGRID_API_KEY:
            payload = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": settings.EMAIL_FROM, "name": settings.EMAIL_FROM_NAME},
                "subject": subject,
                "content": [
                    {"type": "text/html", "value": html_content},
                ],
            }
            if text_content:
                payload["content"].insert(0, {"type": "text/plain", "value": text_content})

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(
                        "https://api.sendgrid.com/v3/mail/send",
                        headers={
                            "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    if res.status_code in [200, 202]:
                        logger.info("email_sent_sendgrid", to=to_email, subject=subject)
                        return True
                    else:
                        logger.warning(
                            "sendgrid_failed",
                            status=res.status_code,
                            body=res.text,
                        )
                        return False
            except Exception as e:
                logger.error("email_delivery_exception", error=str(e), to=to_email)
                return False
        else:
            # Local development / Test mode
            logger.info(
                "email_mock_delivered",
                to=to_email,
                subject=subject,
                preview=(text_content or html_content)[:120],
            )
            return True

    @staticmethod
    async def send_verification_email(to_email: str, verification_url: str) -> bool:
        """Send account email verification link."""
        subject = "Verify your HireKit Campus Account"
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #eaeaea; border-radius: 12px;">
          <h2 style="color: #4F46E5; margin-top: 0;">Welcome to HireKit</h2>
          <p>Please click the button below to verify your college email address and activate your placement profile.</p>
          <div style="margin: 24px 0;">
            <a href="{verification_url}" style="background-color: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">Verify Email Address</a>
          </div>
          <p style="color: #666; font-size: 13px;">This link will expire in 24 hours. If you did not create an account, you can ignore this email.</p>
        </div>
        """
        return await EmailService._send(to_email, subject, html)

    @staticmethod
    async def send_password_reset_email(to_email: str, reset_url: str) -> bool:
        """Send password reset instructions."""
        subject = "Reset your HireKit Password"
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #eaeaea; border-radius: 12px;">
          <h2 style="color: #111827; margin-top: 0;">Password Reset Request</h2>
          <p>We received a request to reset your password. Click the button below to choose a new password:</p>
          <div style="margin: 24px 0;">
            <a href="{reset_url}" style="background-color: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">Reset Password</a>
          </div>
          <p style="color: #666; font-size: 13px;">This link will expire in 15 minutes. If you did not request a password reset, please contact support immediately.</p>
        </div>
        """
        return await EmailService._send(to_email, subject, html)

    @staticmethod
    async def send_application_confirmation(
        to_email: str, student_name: str, job_title: str, company_name: str
    ) -> bool:
        """Send placement drive application confirmation."""
        subject = f"Application Submitted: {job_title} at {company_name}"
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #eaeaea; border-radius: 12px;">
          <h2 style="color: #10B981; margin-top: 0;">Application Submitted ✓</h2>
          <p>Hi {student_name},</p>
          <p>Your application for <strong>{job_title}</strong> at <strong>{company_name}</strong> has been successfully submitted to the Training & Placement Cell.</p>
          <p>You can track the live status of your application and upcoming interview rounds on your HireKit dashboard.</p>
        </div>
        """
        return await EmailService._send(to_email, subject, html)

    @staticmethod
    async def send_weekly_digest(
        to_email: str, student_name: str, active_jobs_count: int, batch_rank: int
    ) -> bool:
        """Send weekly digest of campus placement activity."""
        subject = "Your Weekly HireKit Placement Digest"
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #eaeaea; border-radius: 12px;">
          <h2 style="color: #4F46E5; margin-top: 0;">Weekly Campus Digest</h2>
          <p>Hi {student_name},</p>
          <p>Here is your weekly summary:</p>
          <ul>
            <li><strong>{active_jobs_count} New Campus Drives</strong> currently accepting applications.</li>
            <li>Your current batch rank is <strong>#{batch_rank}</strong>.</li>
          </ul>
          <p>Log in to HireKit to review opportunities before their deadlines close.</p>
        </div>
        """
        return await EmailService._send(to_email, subject, html)
