import json
from typing import List, Optional
import uuid
import redis.asyncio as aioredis
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.notification import Notification, NotificationType
from app.schemas.notification import NotificationOut

logger = structlog.get_logger()


class NotificationService:
    @staticmethod
    async def create_and_publish(
        db: AsyncSession,
        redis: aioredis.Redis,
        user_id: uuid.UUID,
        title: str,
        body: str,
        notif_type: NotificationType = NotificationType.PLACEMENT,
        link: Optional[str] = None,
    ) -> Notification:
        """Insert notification to DB and publish event to user's Redis pub/sub channel."""
        notification = Notification(
            user_id=user_id,
            title=title,
            body=body,
            type=notif_type,
            link=link,
            is_read=False,
        )
        db.add(notification)
        await db.commit()
        await db.refresh(notification)

        # Publish to Redis channel for live WebSocket delivery
        channel_name = f"hirekit:user:{user_id}"
        payload = {
            "event": "NEW_NOTIFICATION",
            "data": {
                "id": str(notification.id),
                "title": notification.title,
                "body": notification.body,
                "type": notification.type.value,
                "link": notification.link,
                "created_at": notification.created_at.isoformat(),
            },
        }
        try:
            await redis.publish(channel_name, json.dumps(payload))
            logger.info("notification_published", user_id=str(user_id), title=title)
        except Exception as e:
            logger.warning("redis_publish_failed", error=str(e))

        return notification

    @staticmethod
    async def list_notifications(
        db: AsyncSession, user_id: uuid.UUID, limit: int = 30
    ) -> List[Notification]:
        """Fetch student's notifications ordered by latest first."""
        result = await db.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(desc(Notification.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def mark_as_read(
        db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID
    ) -> None:
        """Mark single notification as read."""
        await db.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(is_read=True)
        )
        await db.commit()

    @staticmethod
    async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> None:
        """Mark all notifications as read for a user."""
        await db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )
        await db.commit()

    @staticmethod
    async def get_unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
        """Get total unread notifications count."""
        count = await db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id, Notification.is_read.is_(False)
            )
        )
        return count or 0
