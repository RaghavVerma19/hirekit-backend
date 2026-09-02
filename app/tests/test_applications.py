import uuid
from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.education import Education
from app.models.job import Job, JobType
from app.models.resume import Resume


async def _register_and_login(client: AsyncClient, email: str = "app_test@test.com") -> str:
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "name": "Applicant",
    })
    res = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password123!",
    })
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_apply_and_timeline_tracking(client: AsyncClient, db_session: AsyncSession):
    """Test 1-click apply and timeline tracking."""
    token = await _register_and_login(client, "apply_flow@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Get user id
    me = await client.get("/api/v1/auth/me", headers=headers)
    user_id = uuid.UUID(me.json()["id"])

    # Seed Education & Primary Resume
    edu = Education(
        user_id=user_id,
        degree="B.Tech",
        department="Computer Science & Engineering",
        institution="Poornima University",
        start_year=2022,
        end_year=2026,
        cgpa=8.8,
    )
    res = Resume(
        user_id=user_id,
        title="Primary Placement Resume",
        is_primary=True,
        content_json={"summary": "Full stack engineer"},
    )
    job = Job(
        title="Software Development Engineer 1",
        company_name="Amazon India",
        location="Hyderabad, Telangana",
        type=JobType.FULL_TIME,
        ctc="₹28 LPA",
        min_cgpa=8.0,
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add_all([edu, res, job])
    await db_session.commit()
    await db_session.refresh(job)

    # 1. Apply to Job
    res_apply = await client.post(f"/api/v1/jobs/{job.id}/apply", json={}, headers=headers)
    assert res_apply.status_code == 201
    app_data = res_apply.json()
    assert app_data["status"] == "APPLIED"
    assert len(app_data["events"]) == 1
    assert app_data["events"][0]["status"] == "APPLIED"
    app_id = app_data["id"]

    # 2. Idempotent check (applying again returns 201 with existing application, not duplicate)
    res_apply2 = await client.post(f"/api/v1/jobs/{job.id}/apply", json={}, headers=headers)
    assert res_apply2.status_code == 201
    assert res_apply2.json()["id"] == app_id

    # 3. List my applications
    res_list = await client.get("/api/v1/applications", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # 4. Withdraw application
    res_withdraw = await client.delete(f"/api/v1/applications/{app_id}", headers=headers)
    assert res_withdraw.status_code == 200
    assert res_withdraw.json()["status"] == "WITHDRAWN"
    assert len(res_withdraw.json()["events"]) == 2


@pytest.mark.asyncio
async def test_apply_ineligible_cgpa(client: AsyncClient, db_session: AsyncSession):
    """Test rejection when student's CGPA is below requirement."""
    token = await _register_and_login(client, "low_cgpa@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/api/v1/auth/me", headers=headers)
    user_id = uuid.UUID(me.json()["id"])

    edu = Education(
        user_id=user_id,
        degree="B.Tech",
        department="Computer Science",
        institution="Poornima University",
        start_year=2022,
        end_year=2026,
        cgpa=6.5,
    )
    res = Resume(
        user_id=user_id,
        title="Resume",
        is_primary=True,
    )
    job = Job(
        title="High CGPA Role",
        company_name="TopTech",
        min_cgpa=8.5,
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add_all([edu, res, job])
    await db_session.commit()
    await db_session.refresh(job)

    res_apply = await client.post(f"/api/v1/jobs/{job.id}/apply", json={}, headers=headers)
    assert res_apply.status_code == 400
    assert res_apply.json()["error"] == "INELIGIBLE_CGPA"
