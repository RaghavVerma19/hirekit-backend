import pytest
from app.services.email_service import EmailService


@pytest.mark.asyncio
async def test_email_service_deliveries():
    """Test email generation and dispatch in test mode."""
    # 1. Verification email
    v_res = await EmailService.send_verification_email(
        to_email="student@university.edu.in",
        verification_url="http://localhost:3000/verify?token=xyz",
    )
    assert v_res is True

    # 2. Password reset email
    r_res = await EmailService.send_password_reset_email(
        to_email="student@university.edu.in",
        reset_url="http://localhost:3000/reset?token=xyz",
    )
    assert r_res is True

    # 3. Application confirmation email
    a_res = await EmailService.send_application_confirmation(
        to_email="student@university.edu.in",
        student_name="Shruti Bansal",
        job_title="Frontend Engineer",
        company_name="Google",
    )
    assert a_res is True

    # 4. Weekly digest
    d_res = await EmailService.send_weekly_digest(
        to_email="student@university.edu.in",
        student_name="Shruti Bansal",
        active_jobs_count=14,
        batch_rank=8,
    )
    assert d_res is True
