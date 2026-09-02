from datetime import date, datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=150)
    description: str = Field(..., min_length=10)
    live_url: Optional[str] = None
    github_url: Optional[str] = None
    skills_used: List[str] = Field(default_factory=list)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_ongoing: bool = False

    @field_validator("skills_used")
    @classmethod
    def normalize_skills(cls, v: List[str]) -> List[str]:
        return [s.strip().title() for s in v if s.strip()]


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = Field(None, min_length=10)
    live_url: Optional[str] = None
    github_url: Optional[str] = None
    skills_used: Optional[List[str]] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_ongoing: Optional[bool] = None

    @field_validator("skills_used")
    @classmethod
    def normalize_skills(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            return [s.strip().title() for s in v if s.strip()]
        return v


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: str
    live_url: Optional[str] = None
    github_url: Optional[str] = None
    skills_used: List[str] = []
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_ongoing: bool
    created_at: datetime
    updated_at: datetime
