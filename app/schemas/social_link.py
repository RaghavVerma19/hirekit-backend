from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SocialLinkCreate(BaseModel):
    platform: str = Field(..., min_length=2, max_length=50)
    url: str = Field(..., min_length=5, max_length=512)

    @field_validator("platform")
    @classmethod
    def normalize_platform(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class SocialLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    platform: str
    url: str
    created_at: datetime
