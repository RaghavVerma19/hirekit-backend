from datetime import datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.models.job import JobStatus, JobType


class JobCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    company_name: str = Field(..., min_length=2, max_length=150)
    company_logo: Optional[str] = None
    location: str = Field("Hybrid / On-site", max_length=150)
    type: JobType = JobType.FULL_TIME
    tier: str = Field("REGULAR", description="REGULAR, DREAM, or SUPER_DREAM")
    ctc: str = Field("Best in Industry", max_length=100)
    min_cgpa: float = Field(0.0, ge=0.0, le=10.0)
    max_active_backlogs: int = Field(0, ge=0)
    min_10th_marks: float = Field(0.0, ge=0.0, le=100.0)
    min_12th_marks: float = Field(0.0, ge=0.0, le=100.0)
    eligible_departments: List[str] = []
    eligible_batches: List[str] = []
    skills: List[str] = []
    description: str = ""
    requirements: str = ""
    rounds: List[dict] = []
    deadline: datetime


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company_name: str
    company_logo: Optional[str] = None
    location: str
    type: JobType
    tier: str = "REGULAR"
    ctc: str
    min_cgpa: float
    max_active_backlogs: int = 0
    min_10th_marks: float = 0.0
    min_12th_marks: float = 0.0
    eligible_departments: List[str]
    eligible_batches: List[str]
    skills: List[str]
    description: str
    requirements: str
    rounds: List[dict] = []
    is_drive_active: bool = True
    status: JobStatus
    deadline: datetime
    posted_at: datetime


class JobListItem(JobOut):
    is_eligible: bool = True
    ineligibility_reasons: List[str] = []
    match_score: int = 80
    has_applied: bool = False
