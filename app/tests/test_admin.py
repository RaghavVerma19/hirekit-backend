from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.job import Job, JobType
from app.models.user import Role, User


async def _register_admin(client: AsyncClient, db_session: AsyncSession) -> str:
    res = await client.post("/api/v1/auth/register", json={
        "email": "tpo_admin@university.edu.in",
        "password": "Password123!",
        "name": "Prof. TPO Officer",
    })
    user_id = res.json()["id"]

    # Upgrade to TPO role
    await db_session.execute(
        update(User).where(User.id == user_id).values(role=Role.TPO)
    )
    await db_session.commit()

    login_res = await client.post("/api/v1/auth/login", json={
        "email": "tpo_admin@university.edu.in",
        "password": "Password123!",
    })
    return login_res.json()["access_token"]


@pytest.mark.asyncio
async def test_admin_access_control(client: AsyncClient):
    """Test non-admin student is blocked from TPO endpoints with 403 Forbidden."""
    await client.post("/api/v1/auth/register", json={
        "email": "plain_student@test.com",
        "password": "Password123!",
        "name": "Student",
    })
    login_res = await client.post("/api/v1/auth/login", json={
        "email": "plain_student@test.com",
        "password": "Password123!",
    })
    student_token = login_res.json()["access_token"]
    student_headers = {"Authorization": f"Bearer {student_token}"}

    res = await client.get("/api/v1/admin/users", headers=student_headers)
    assert res.status_code == 403
    assert res.json()["error"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_bulk_verify_and_analytics(client: AsyncClient, db_session: AsyncSession):
    """Test TPO bulk student verification and analytics overview."""
    admin_token = await _register_admin(client, db_session)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Register 2 unverified students
    res1 = await client.post("/api/v1/auth/register", json={
        "email": "student1@test.com", "password": "Password123!", "name": "Student 1"
    })
    res2 = await client.post("/api/v1/auth/register", json={
        "email": "student2@test.com", "password": "Password123!", "name": "Student 2"
    })
    u1_id = res1.json()["id"]
    u2_id = res2.json()["id"]

    # 1. Bulk verify
    res_verify = await client.post("/api/v1/admin/bulk-verify", json={
        "user_ids": [u1_id, u2_id]
    }, headers=admin_headers)
    assert res_verify.status_code == 200
    assert "Successfully verified 2" in res_verify.json()["message"]

    # 2. Get analytics
    res_analytics = await client.get("/api/v1/admin/analytics/overview", headers=admin_headers)
    assert res_analytics.status_code == 200
    data = res_analytics.json()
    assert "placement_rate_percent" in data
    assert "total_students" in data
    assert "avg_ctc_lpa" in data
