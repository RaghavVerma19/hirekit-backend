from datetime import datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict
from app.models.application import ApplicationStatus
from app.schemas.job import JobOut


class ApplicationCreate(BaseModel):
    resume_id: Optional[uuid.UUID] = None


class ApplicationEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    status: ApplicationStatus
    note: Optional[str] = None
    actor: str
    occurred_at: datetime


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    user_id: uuid.UUID
    resume_id: Optional[uuid.UUID] = None
    status: ApplicationStatus
    applied_at: datetime
    updated_at: datetime
    job: Optional[JobOut] = None


class ApplicationDetailOut(ApplicationOut):
    events: List[ApplicationEventOut] = []
