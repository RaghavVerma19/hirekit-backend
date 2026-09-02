from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict
from app.models.interview import InterviewStatus


class InterviewCreate(BaseModel):
    user_id: uuid.UUID
    application_id: Optional[uuid.UUID] = None
    company_name: str
    role_title: str
    round_name: str = "Technical Round 1"
    scheduled_at: datetime
    meeting_url: Optional[str] = None


class InterviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    application_id: Optional[uuid.UUID] = None
    company_name: str
    role_title: str
    round_name: str
    scheduled_at: datetime
    meeting_url: Optional[str] = None
    status: InterviewStatus
    prep_score: Optional[int] = None
    feedback: Optional[str] = None
    created_at: datetime
