from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus, JobType


async def _register_and_login(client: AsyncClient, email: str = "job_test@test.com") -> str:
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "name": "Job Seeker",
    })
    res = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password123!",
    })
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_list_and_filter_jobs(client: AsyncClient, db_session: AsyncSession):
    """Test listing and filtering job postings."""
    token = await _register_and_login(client, "filter_jobs@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Seed 2 test jobs
    j1 = Job(
        title="Frontend React Developer",
        company_name="TechCorp India",
        location="Bengaluru, Karnataka",
        type=JobType.FULL_TIME,
        ctc="₹14 - 18 LPA",
        min_cgpa=7.5,
        eligible_departments=["Computer Science", "Information Technology"],
        eligible_batches=["2026"],
        skills=["React", "TypeScript", "Tailwind CSS"],
        deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    j2 = Job(
        title="Data Science Intern",
        company_name="AnalyticsHub",
        location="Remote",
        type=JobType.INTERNSHIP,
        ctc="₹40,000 / month",
        min_cgpa=8.0,
        eligible_departments=["Computer Science"],
        eligible_batches=["2026"],
        skills=["Python", "PyTorch", "SQL"],
        deadline=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db_session.add_all([j1, j2])
    await db_session.commit()

    # 1. List all open jobs
    res = await client.get("/api/v1/jobs", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 2

    # 2. Filter by search query
    res_search = await client.get("/api/v1/jobs?search=React", headers=headers)
    assert res_search.status_code == 200
    search_items = res_search.json()
    assert len(search_items) == 1
    assert search_items[0]["title"] == "Frontend React Developer"

    # 3. Filter by type
    res_type = await client.get("/api/v1/jobs?type=Internship", headers=headers)
    assert res_type.status_code == 200
    type_items = res_type.json()
    assert any(item["title"] == "Data Science Intern" for item in type_items)
