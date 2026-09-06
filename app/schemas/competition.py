from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.models.competition import CompetitionStatus


class CompetitionCreateIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    description: str = Field('', max_length=5000)
    category: str = Field('Coding and Algorithms', max_length=100)
    start_date: datetime
    end_date: datetime
    prize_pool: str = Field('Cash Prizes + Certificates', max_length=100)
    max_participants: Optional[int] = Field(None, ge=1)
    rules_url: Optional[str] = Field(None, max_length=512)


class CompetitionRegisterIn(BaseModel):
    team_name: Optional[str] = Field(None, max_length=100)


class CompetitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    category: str
    start_date: datetime
    end_date: datetime
    prize_pool: str
    status: CompetitionStatus
    max_participants: Optional[int]
    participant_count: int
    rules_url: Optional[str]
    is_registered: Optional[bool] = False
    created_at: datetime


class CompetitionRegistrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    competition_id: uuid.UUID
    user_id: uuid.UUID
    team_name: Optional[str] = None
    registered_at: datetime
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    user_department: Optional[str] = None
    user_batch: Optional[str] = None
