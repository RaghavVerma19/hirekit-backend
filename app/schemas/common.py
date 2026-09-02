import enum
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[Any] = None
    request_id: Optional[str] = None


class MessageOut(BaseModel):
    message: str
    success: bool = True


class HealthOut(BaseModel):
    status: str
    database: str
    redis: str
    version: str


class UploadTargetType(str, enum.Enum):
    EDUCATION = "education"
    EXPERIENCE = "experience"
    ACCOMPLISHMENT = "accomplishment"
    AVATAR = "avatar"
    RESUME_PDF = "resume_pdf"


class PresignedUploadIn(BaseModel):
    filename: str = Field(..., min_length=3, max_length=255)
    content_type: str = Field(..., min_length=3, max_length=100)
    target_type: UploadTargetType = UploadTargetType.EDUCATION


class PresignedUploadOut(BaseModel):
    upload_url: str
    file_url: str
    key: str
    expires_in: int = 300
    headers: Dict[str, str] = {}


class ConfirmUploadIn(BaseModel):
    target_type: UploadTargetType
    target_id: uuid.UUID
    file_url: str
