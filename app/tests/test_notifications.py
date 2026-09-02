import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.models.notification import NotificationType
from app.services.notification_service import NotificationService


async def _register_and_login(client: AsyncClient, email: str = "notif_user@test.com") -> str:
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "name": "Notification User",
    })
    res = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password123!",
    })
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_notifications_lifecycle(
    client: AsyncClient, db_session: AsyncSession, mock_redis: aioredis.Redis
):
    """Test creating, listing, unread badge counting, and marking notifications as read."""
    token = await _register_and_login(client, "notif_flow@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/api/v1/auth/me", headers=headers)
    user_id = me.json()["id"]

    # 1. Initially 0 unread
    res_count0 = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert res_count0.status_code == 200
    assert res_count0.json()["unread_count"] == 0

    # 2. Add 2 notifications via service
    n1 = await NotificationService.create_and_publish(
        db=db_session,
        redis=mock_redis,
        user_id=user_id,
        title="Application Shortlisted",
        body="Google has shortlisted your profile for Technical Round 1.",
        notif_type=NotificationType.PLACEMENT,
    )
    n2 = await NotificationService.create_and_publish(
        db=db_session,
        redis=mock_redis,
        user_id=user_id,
        title="Interview Scheduled",
        body="Your interview is scheduled for tomorrow at 3 PM.",
        notif_type=NotificationType.INTERVIEW,
    )

    # 3. Check unread count = 2
    res_count2 = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert res_count2.json()["unread_count"] == 2

    # 4. List notifications
    res_list = await client.get("/api/v1/notifications", headers=headers)
    assert res_list.status_code == 200
    items = res_list.json()
    assert len(items) == 2

    # 5. Mark single notification as read
    res_read = await client.patch(f"/api/v1/notifications/{n1.id}/read", headers=headers)
    assert res_read.status_code == 200

    # Check unread count = 1
    res_count1 = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert res_count1.json()["unread_count"] == 1

    # 6. Mark all as read
    res_mark_all = await client.post("/api/v1/notifications/mark-all-read", headers=headers)
    assert res_mark_all.status_code == 200

    # Check unread count = 0
    res_count_final = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert res_count_final.json()["unread_count"] == 0
