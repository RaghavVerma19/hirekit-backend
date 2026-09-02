import pytest
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str = "dash@test.com") -> str:
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "name": "Dashboard Tester",
    })
    res = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password123!",
    })
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_dashboard_overview(client: AsyncClient):
    """Test dashboard aggregation endpoint."""
    token = await _register_and_login(client, "overview@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.get("/api/v1/dashboard/overview", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == "overview@test.com"
    assert "active_jobs_count" in data
    assert "applications_count" in data
    assert "linkedin" in data
    assert data["linkedin"]["profile_score"] == 85
    assert len(data["announcements"]) > 0


@pytest.mark.asyncio
async def test_my_batch_rank(client: AsyncClient):
    """Test personal batch rank and percentile endpoint."""
    token = await _register_and_login(client, "rank@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.get("/api/v1/dashboard/my-rank", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "rank" in data
    assert "percentile" in data
    assert "recommendation_tip" in data
