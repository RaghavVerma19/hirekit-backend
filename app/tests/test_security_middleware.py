import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient):
    """Verify standard OWASP security and tracking headers on API responses."""
    res = await client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert "Strict-Transport-Security" in res.headers
    assert "X-Request-ID" in res.headers
    assert "X-Process-Time" in res.headers


@pytest.mark.asyncio
async def test_request_size_limit_rejection(client: AsyncClient):
    """Verify requests with Content-Length > 10MB are rejected with 413 Payload Too Large."""
    # Simulate header exceeding 10MB
    headers = {"Content-Length": str(15 * 1024 * 1024)}  # 15 MB
    res = await client.post("/api/v1/auth/login", headers=headers, json={"email": "a", "password": "b"})
    assert res.status_code == 413
    assert res.json()["error"] == "PAYLOAD_TOO_LARGE"
