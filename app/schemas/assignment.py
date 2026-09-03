from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.models.assignment import SubmissionStatus


class AssignmentCreateIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    description: str = Field('', max_length=5000)
    course_code: str = Field('CS301', max_length=50)
    due_at: datetime
    max_score: float = Field(100.0, ge=1.0, le=1000.0)
    target_department: str = Field('Computer Science', max_length=100)
    target_batch: str = Field('2026', max_length=50)
    attachment_url: Optional[str] = Field(None, max_length=512)


class AssignmentSubmitIn(BaseModel):
    file_url: str = Field(..., max_length=512)


class AssignmentGradeIn(BaseModel):
    score: float = Field(..., ge=0.0)
    feedback: Optional[str] = Field(None, max_length=2000)


class AssignmentSubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assignment_id: uuid.UUID
    student_id: uuid.UUID
    file_url: str
    submitted_at: datetime
    status: SubmissionStatus
    score: Optional[float] = None
    feedback: Optional[str] = None


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    course_code: str
    due_at: datetime
    max_score: float
    target_department: str
    target_batch: str
    attachment_url: Optional[str] = None
    my_submission: Optional[AssignmentSubmissionOut] = None
    created_at: datetime
