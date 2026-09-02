from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _register_and_login(client: AsyncClient, email: str = "resume_test@test.com") -> str:
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "name": "Resume Tester",
    })
    res = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password123!",
    })
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_create_and_list_resumes(client: AsyncClient):
    """Test creating a resume and listing user's resumes."""
    token = await _register_and_login(client, "create_res@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    res_create = await client.post("/api/v1/resumes", json={
        "title": "Frontend Engineer Resume",
        "template_id": "modern-tech",
        "auto_populate": True,
    }, headers=headers)
    assert res_create.status_code == 201
    data = res_create.json()
    assert data["title"] == "Frontend Engineer Resume"
    assert data["is_primary"] is True  # First resume is auto-set to primary
    resume_id = data["id"]

    res_list = await client.get("/api/v1/resumes", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1


@pytest.mark.asyncio
async def test_update_and_optimistic_locking(client: AsyncClient):
    """Test resume auto-save and concurrent conflict protection."""
    token = await _register_and_login(client, "lock_test@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_res = await client.post("/api/v1/resumes", json={"title": "Draft 1"}, headers=headers)
    resume = create_res.json()
    resume_id = resume["id"]

    # 1. Successful update
    res_update = await client.put(f"/api/v1/resumes/{resume_id}", json={
        "title": "Draft 2",
        "content_json": {"summary": "Experienced engineer with Python expertise."},
    }, headers=headers)
    assert res_update.status_code == 200
    assert res_update.json()["title"] == "Draft 2"

    # 2. Concurrent conflict with outdated timestamp
    past_timestamp = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    res_conflict = await client.put(f"/api/v1/resumes/{resume_id}", json={
        "title": "Stale Edit",
        "last_known_updated_at": past_timestamp,
    }, headers=headers)
    assert res_conflict.status_code == 409
    assert res_conflict.json()["error"] == "CONCURRENT_EDIT_CONFLICT"


@pytest.mark.asyncio
async def test_set_primary_resume(client: AsyncClient):
    """Test toggling the primary application resume."""
    token = await _register_and_login(client, "primary_test@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    res1 = await client.post("/api/v1/resumes", json={"title": "Resume 1"}, headers=headers)
    res2 = await client.post("/api/v1/resumes", json={"title": "Resume 2"}, headers=headers)
    id1 = res1.json()["id"]
    id2 = res2.json()["id"]

    assert res1.json()["is_primary"] is True
    assert res2.json()["is_primary"] is False

    # Switch primary to Resume 2
    res_patch = await client.patch(f"/api/v1/resumes/{id2}/primary", headers=headers)
    assert res_patch.status_code == 200
    assert res_patch.json()["is_primary"] is True

    # Verify Resume 1 is no longer primary
    get1 = await client.get(f"/api/v1/resumes/{id1}", headers=headers)
    assert get1.json()["is_primary"] is False


@pytest.mark.asyncio
async def test_score_resume_and_caching(client: AsyncClient):
    """Test ATS scoring and verifying cached score on identical content."""
    token = await _register_and_login(client, "ats_test@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_res = await client.post("/api/v1/resumes", json={
        "title": "ATS Candidate Resume",
        "auto_populate": True,
    }, headers=headers)
    resume_id = create_res.json()["id"]

    # 1. First scoring call
    res_score1 = await client.post(f"/api/v1/resumes/{resume_id}/score", headers=headers)
    assert res_score1.status_code == 200
    score1_data = res_score1.json()
    assert "overall_score" in score1_data
    assert score1_data["overall_score"] >= 40
    assert len(score1_data["strengths"]) > 0

    # 2. Second scoring call on unchanged content (hits Redis cache)
    res_score2 = await client.post(f"/api/v1/resumes/{resume_id}/score", headers=headers)
    assert res_score2.status_code == 200
    assert res_score2.json()["overall_score"] == score1_data["overall_score"]
