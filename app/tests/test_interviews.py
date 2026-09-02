from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview import Interview, InterviewStatus
from app.models.user import Role, User


async def _register_and_login(
    client: AsyncClient, email: str = "interview_student@test.com"
) -> str:
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "name": "Interview Student",
    })
    res = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password123!",
    })
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_upcoming_interviews(client: AsyncClient, db_session: AsyncSession):
    """Test listing student's upcoming interviews."""
    token = await _register_and_login(client, "upcoming_student@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/api/v1/auth/me", headers=headers)
    user_id = me.json()["id"]

    # Seed 1 upcoming and 1 past interview
    future_time = datetime.now(timezone.utc) + timedelta(days=2)
    past_time = datetime.now(timezone.utc) - timedelta(days=2)

    i1 = Interview(
        user_id=user_id,
        company_name="Microsoft India",
        role_title="Software Engineer",
        round_name="Technical Round 2 (System Design)",
        scheduled_at=future_time,
        meeting_url="https://teams.microsoft.com/meet/123",
        status=InterviewStatus.SCHEDULED,
    )
    i2 = Interview(
        user_id=user_id,
        company_name="OldCorp",
        role_title="Intern",
        round_name="Round 1",
        scheduled_at=past_time,
        status=InterviewStatus.COMPLETED,
    )
    db_session.add_all([i1, i2])
    await db_session.commit()

    # List upcoming
    res = await client.get("/api/v1/interviews/upcoming", headers=headers)
    assert res.status_code == 200
    interviews = res.json()
    assert len(interviews) == 1
    assert interviews[0]["company_name"] == "Microsoft India"
    assert interviews[0]["round_name"] == "Technical Round 2 (System Design)"
