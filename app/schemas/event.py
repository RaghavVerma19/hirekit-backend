from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.models.event import EventType


class EventCreateIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    description: str = Field('', max_length=5000)
    event_type: EventType = EventType.WORKSHOP
    date: datetime
    end_date: Optional[datetime] = None
    location: str = Field('Campus Auditorium', max_length=255)
    is_virtual: bool = False
    meeting_url: Optional[str] = Field(None, max_length=512)
    banner_url: Optional[str] = Field(None, max_length=512)
    max_attendees: Optional[int] = Field(None, ge=1)


class EventUpdateIn(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    event_type: Optional[EventType] = None
    date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=255)
    is_virtual: Optional[bool] = None
    meeting_url: Optional[str] = Field(None, max_length=512)
    banner_url: Optional[str] = Field(None, max_length=512)
    max_attendees: Optional[int] = Field(None, ge=1)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    event_type: EventType
    date: datetime
    end_date: Optional[datetime]
    location: str
    is_virtual: bool
    meeting_url: Optional[str]
    organizer_id: Optional[uuid.UUID]
    organizer_name: str
    banner_url: Optional[str]
    max_attendees: Optional[int]
    registered_count: int
    is_registered: Optional[bool] = False
    created_at: datetime
