from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SemesterScore(BaseModel):
    semester: int = Field(..., ge=1, le=12)
    sgpa: Optional[float] = Field(None, ge=0.0, le=10.0)
    percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    credits: Optional[int] = Field(None, ge=0)


class EducationCreate(BaseModel):
    degree: str = Field(..., min_length=2, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    institution: str = Field(..., min_length=2, max_length=255)
    start_year: int = Field(..., ge=1970, le=2050)
    end_year: Optional[int] = Field(None, ge=1970, le=2050)
    cgpa: Optional[float] = Field(None, ge=0.0, le=10.0)
    percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    is_current: bool = False
    marksheet_url: Optional[str] = None
    semester_scores: Optional[List[SemesterScore]] = []
    education_gap: Optional[int] = Field(0, ge=0, le=10)

    @field_validator("end_year")
    @classmethod
    def validate_year_range(cls, v: Optional[int], info) -> Optional[int]:
        start_year = info.data.get("start_year")
        if v is not None and start_year is not None and v < start_year:
            raise ValueError("end_year must be greater than or equal to start_year")
        return v


class EducationUpdate(BaseModel):
    degree: Optional[str] = Field(None, min_length=2, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    institution: Optional[str] = Field(None, min_length=2, max_length=255)
    start_year: Optional[int] = Field(None, ge=1970, le=2050)
    end_year: Optional[int] = Field(None, ge=1970, le=2050)
    cgpa: Optional[float] = Field(None, ge=0.0, le=10.0)
    percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    is_current: Optional[bool] = None
    marksheet_url: Optional[str] = None
    semester_scores: Optional[List[SemesterScore]] = None
    education_gap: Optional[int] = Field(None, ge=0, le=10)


class EducationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    degree: str
    department: Optional[str] = None
    institution: str
    start_year: int
    end_year: Optional[int] = None
    cgpa: Optional[float] = None
    percentage: Optional[float] = None
    is_current: bool
    is_verified: bool
    marksheet_url: Optional[str] = None
    semester_scores: Optional[List[Dict[str, Any]]] = None
    education_gap: Optional[int] = 0
    created_at: datetime
    updated_at: datetime
