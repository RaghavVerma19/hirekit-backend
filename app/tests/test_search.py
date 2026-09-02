from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.post import Post
from app.models.user import User


@pytest.mark.asyncio
async def test_global_search(client: AsyncClient, db_session: AsyncSession):
    """Test global unified search across jobs and feed posts."""
    # Seed job & post
    job = Job(
        title="Senior Python Backend Architect",
        company_name="FastScale AI",
        location="Bengaluru",
        ctc="₹35 LPA",
        deadline=datetime.now(timezone.utc) + timedelta(days=10),
    )
    # Create user for post author
    res_reg = await client.post("/api/v1/auth/register", json={
        "email": "search_author@test.com",
        "password": "Password123!",
        "name": "Author",
    })
    user_id = res_reg.json()["id"]

    post = Post(
        author_id=user_id,
        author_name="Placement Lead",
        title="Guide to Python and FastAPI Interviews",
        body="Here are the top 20 questions asked in backend Python placement rounds.",
    )
    db_session.add_all([job, post])
    await db_session.commit()

    # 1. Search for "Python"
    res = await client.get("/api/v1/search?q=Python")
    assert res.status_code == 200
    data = res.json()
    assert data["total_count"] >= 2
    types = [r["type"] for r in data["results"]]
    assert "job" in types
    assert "post" in types

    # 2. Filter search by type=jobs
    res_jobs = await client.get("/api/v1/search?q=Python&type=jobs")
    assert res_jobs.status_code == 200
    assert all(r["type"] == "job" for r in res_jobs.json()["results"])
