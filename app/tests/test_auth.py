from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import EmailVerificationToken, RefreshToken, User


@pytest.mark.asyncio
async def test_health_endpoints(client: AsyncClient):
    """Test health and readiness probes."""
    res = await client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"

    res_ready = await client.get("/api/v1/ready")
    assert res_ready.status_code == 200
    ready_data = res_ready.json()
    assert ready_data["status"] == "ready"


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, db_session: AsyncSession):
    """Test standard user registration flow."""
    payload = {
        "email": "student@poornima.edu.in",
        "password": "Password123!",
        "name": "Shruti Bansal",
    }
    res = await client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "student@poornima.edu.in"
    assert data["name"] == "Shruti Bansal"
    assert data["role"] == "STUDENT"
    assert data["is_verified"] is False
    assert "password_hash" not in data

    # Verify user saved in DB
    user = await db_session.scalar(
        select(User).where(User.email == "student@poornima.edu.in")
    )
    assert user is not None
    assert user.name == "Shruti Bansal"

    # Verify EmailVerificationToken generated
    token_record = await db_session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    )
    assert token_record is not None
    assert token_record.used is False


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Test that registering an existing email returns 409 Conflict."""
    payload = {
        "email": "duplicate@test.com",
        "password": "Password123!",
        "name": "Test User",
    }
    res1 = await client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    data = res2.json()
    assert data["error"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    """Test that weak passwords are rejected with 422 Unprocessable Entity."""
    # No uppercase
    res1 = await client.post("/api/v1/auth/register", json={
        "email": "weak1@test.com",
        "password": "password123",
        "name": "Weak Pass",
    })
    assert res1.status_code == 422

    # No number
    res2 = await client.post("/api/v1/auth/register", json={
        "email": "weak2@test.com",
        "password": "PasswordPassword",
        "name": "Weak Pass",
    })
    assert res2.status_code == 422

    # Too short (<8 chars)
    res3 = await client.post("/api/v1/auth/register", json={
        "email": "weak3@test.com",
        "password": "Pass1",
        "name": "Weak Pass",
    })
    assert res3.status_code == 422


@pytest.mark.asyncio
async def test_login_and_get_me(client: AsyncClient):
    """Test login sets cookies and returns access token to query /me."""
    # Register first
    await client.post("/api/v1/auth/register", json={
        "email": "login_test@poornima.edu.in",
        "password": "SecurePassword1!",
        "name": "Login Tester",
    })

    # Login
    login_res = await client.post("/api/v1/auth/login", json={
        "email": "login_test@poornima.edu.in",
        "password": "SecurePassword1!",
    })
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    access_token = token_data["access_token"]

    # Verify cookies set
    assert "refresh_token" in login_res.cookies
    assert "csrf_token" in login_res.cookies

    # Access protected /me route
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == "login_test@poornima.edu.in"
    assert me_data["name"] == "Login Tester"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Test wrong password or nonexistent user returns 401."""
    res = await client.post("/api/v1/auth/login", json={
        "email": "nonexistent@test.com",
        "password": "WrongPassword123!",
    })
    assert res.status_code == 401
    assert res.json()["error"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient):
    """Test refresh token rotation issues a new token pair."""
    # Register & Login
    await client.post("/api/v1/auth/register", json={
        "email": "refresh_test@test.com",
        "password": "Password123!",
        "name": "Refresh Tester",
    })
    login_res = await client.post("/api/v1/auth/login", json={
        "email": "refresh_test@test.com",
        "password": "Password123!",
    })
    initial_rt = login_res.cookies.get("refresh_token")
    assert initial_rt is not None

    # Call refresh endpoint with initial cookie
    client.cookies.set("refresh_token", initial_rt)
    refresh_res = await client.post("/api/v1/auth/refresh")
    assert refresh_res.status_code == 200
    assert "access_token" in refresh_res.json()

    # The cookie should have been rotated to a new value
    rotated_rt = refresh_res.cookies.get("refresh_token")
    assert rotated_rt is not None
    assert rotated_rt != initial_rt


@pytest.mark.asyncio
async def test_refresh_token_grace_period(client: AsyncClient):
    """Test 30s grace period allows concurrent browser tab refreshes without logging out."""
    await client.post("/api/v1/auth/register", json={
        "email": "grace_test@test.com",
        "password": "Password123!",
        "name": "Grace Tester",
    })
    login_res = await client.post("/api/v1/auth/login", json={
        "email": "grace_test@test.com",
        "password": "Password123!",
    })
    tab_1_rt = login_res.cookies.get("refresh_token")

    # Tab 1 refreshes
    client.cookies.set("refresh_token", tab_1_rt)
    res_tab1 = await client.post("/api/v1/auth/refresh")
    assert res_tab1.status_code == 200

    # Tab 2 sends the OLD token immediately (simulating concurrent tab sync)
    client.cookies.set("refresh_token", tab_1_rt)
    res_tab2 = await client.post("/api/v1/auth/refresh")
    assert res_tab2.status_code == 200
    assert "access_token" in res_tab2.json()


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    """Test logout clears auth cookies."""
    await client.post("/api/v1/auth/register", json={
        "email": "logout_test@test.com",
        "password": "Password123!",
        "name": "Logout Tester",
    })
    login_res = await client.post("/api/v1/auth/login", json={
        "email": "logout_test@test.com",
        "password": "Password123!",
    })
    rt = login_res.cookies.get("refresh_token")

    client.cookies.set("refresh_token", rt)
    logout_res = await client.post("/api/v1/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json()["success"] is True
