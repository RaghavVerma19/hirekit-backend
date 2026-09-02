from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class ATSImprovement(BaseModel):
    section: str
    current: str
    suggested: str
    impact: str  # e.g. "HIGH", "MEDIUM", "LOW"


class ATSScoreResult(BaseModel):
    overall_score: int = Field(..., ge=0, le=100)
    pass_rate_message: str
    strengths: List[str] = []
    improvements: List[ATSImprovement] = []
    missing_sections: List[str] = []
    is_job_matched: bool = False


class ResumeCreate(BaseModel):
    title: str = Field("My Resume", min_length=1, max_length=150)
    template_id: str = Field("modern-tech", max_length=50)
    auto_populate: bool = True


class ResumeUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=150)
    template_id: Optional[str] = Field(None, max_length=50)
    content_json: Optional[Dict[str, Any]] = None
    last_known_updated_at: Optional[datetime] = None  # For optimistic concurrency locking


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    pdf_url: Optional[str] = None
    template_id: str
    content_hash: str
    ats_score: Optional[int] = None
    ats_feedback: Optional[Dict[str, Any]] = None
    is_primary: bool
    leaderboard_eligible: bool
    created_at: datetime
    updated_at: datetime


class ResumeDetailOut(ResumeOut):
    content_json: Dict[str, Any]
