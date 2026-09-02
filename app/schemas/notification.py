from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict
from app.models.notification import NotificationType


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    body: str
    type: NotificationType
    is_read: bool
    link: Optional[str] = None
    created_at: datetime


class UnreadCountOut(BaseModel):
    unread_count: int
