from datetime import date, datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResponsibilityIn(BaseModel):
    description: str = Field(..., min_length=2, max_length=500)
    order_index: int = Field(0, ge=0)


class ResponsibilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    order_index: int


class ExperienceCreate(BaseModel):
    role: str = Field(..., min_length=2, max_length=100)
    company: str = Field(..., min_length=2, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    type: str = Field("INTERNSHIP", max_length=50)
    start_date: date
    end_date: Optional[date] = None
    is_current: bool = False
    certificate_url: Optional[str] = None
    responsibilities: Optional[List[str]] = []

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: Optional[date], info) -> Optional[date]:
        start_date = info.data.get("start_date")
        if v is not None and start_date is not None and v < start_date:
            raise ValueError("end_date must be on or after start_date")
        return v


class ExperienceUpdate(BaseModel):
    role: Optional[str] = Field(None, min_length=2, max_length=100)
    company: Optional[str] = Field(None, min_length=2, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    type: Optional[str] = Field(None, max_length=50)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: Optional[bool] = None
    certificate_url: Optional[str] = None
    responsibilities: Optional[List[str]] = None


class ExperienceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    company: str
    location: Optional[str] = None
    type: str
    start_date: date
    end_date: Optional[date] = None
    is_current: bool
    certificate_url: Optional[str] = None
    responsibilities: List[ResponsibilityOut] = []
    created_at: datetime
    updated_at: datetime
