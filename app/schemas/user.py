from datetime import date, datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import Role
from app.schemas.accomplishment import AccomplishmentOut
from app.schemas.education import EducationOut
from app.schemas.experience import ExperienceOut
from app.schemas.guardian import GuardianOut
from app.schemas.project import ProjectOut
from app.schemas.skill import SkillOut
from app.schemas.social_link import SocialLinkOut


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: Role
    name: str
    headline: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[date] = None
    location: Optional[str] = None
    permanent_address: Optional[str] = None
    summary: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None
    college_id: Optional[uuid.UUID] = None
    is_verified: bool
    is_onboarded: bool
    timezone: str
    created_at: datetime
    updated_at: datetime


class ProfileBasicUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    headline: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    gender: Optional[str] = Field(None, max_length=20)
    dob: Optional[date] = None
    location: Optional[str] = Field(None, max_length=255)
    permanent_address: Optional[str] = None
    summary: Optional[str] = None
    timezone: Optional[str] = Field(None, max_length=64)

    @field_validator("dob", mode="before")
    @classmethod
    def parse_dob(cls, v: Any) -> Optional[date]:
        if not v or v == "":
            return None
        return v

    @field_validator("phone", "gender", "headline", "location", "permanent_address", "summary", mode="before")
    @classmethod
    def sanitize_strings(cls, v: Any) -> Optional[str]:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # Note: role, is_verified, email, password_hash are strictly omitted to prevent mass-assignment


class ProfileCompletionOut(BaseModel):
    percentage: int = Field(..., ge=0, le=100)
    completed_sections: List[str]
    missing_sections: List[str]
    next_action: str
    is_job_ready: bool


class FullProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserOut
    educations: List[EducationOut] = []
    experiences: List[ExperienceOut] = []
    skills: List[SkillOut] = []
    projects: List[ProjectOut] = []
    accomplishments: List[AccomplishmentOut] = []
    guardians: List[GuardianOut] = []
    social_links: List[SocialLinkOut] = []
    additional_info: Optional[Dict[str, Any]] = None
    completion: ProfileCompletionOut
