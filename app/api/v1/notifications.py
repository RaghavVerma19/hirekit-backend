from typing import List
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageOut
from app.schemas.notification import NotificationOut, UnreadCountOut
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications & Alerts"])


@router.get(
    "",
    response_model=List[NotificationOut],
    status_code=status.HTTP_200_OK,
    summary="List My Notifications",
)
async def list_notifications(
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[NotificationOut]:
    """Retrieve all notifications for the authenticated user."""
    notifications = await NotificationService.list_notifications(
        db, current_user.id, limit
    )
    return [NotificationOut.model_validate(n) for n in notifications]


@router.get(
    "/unread-count",
    response_model=UnreadCountOut,
    status_code=status.HTTP_200_OK,
    summary="Get Unread Notification Count",
)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UnreadCountOut:
    """Get badge count of unread notifications."""
    count = await NotificationService.get_unread_count(db, current_user.id)
    return UnreadCountOut(unread_count=count)


@router.patch(
    "/{notification_id}/read",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Mark Notification as Read",
)
async def mark_as_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Mark a specific notification as read."""
    await NotificationService.mark_as_read(db, current_user.id, notification_id)
    return MessageOut(message="Notification marked as read.")


@router.post(
    "/mark-all-read",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Mark All Notifications as Read",
)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Mark all unread notifications as read."""
    await NotificationService.mark_all_read(db, current_user.id)
    return MessageOut(message="All notifications marked as read.")
