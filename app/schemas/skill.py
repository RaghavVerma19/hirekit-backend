from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    level: str = Field("INTERMEDIATE", max_length=50)

    @field_validator("name")
    @classmethod
    def normalize_skill_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Skill name cannot be empty")
        # Canonical casing normalization (e.g., "react.js" -> "React.js", "PYTHON" -> "Python")
        return cleaned.title()


class SkillUpdate(BaseModel):
    level: str = Field(..., max_length=50)


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    level: str
    is_verified: bool
    created_at: datetime
