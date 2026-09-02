from datetime import date, datetime
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.models.accomplishment import AccomplishmentType


class AccomplishmentCreate(BaseModel):
    type: AccomplishmentType = AccomplishmentType.CERTIFICATE
    title: str = Field(..., min_length=2, max_length=200)
    issuer: Optional[str] = Field(None, max_length=150)
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    credential_url: Optional[str] = None
    document_url: Optional[str] = None
    details: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AccomplishmentUpdate(BaseModel):
    type: Optional[AccomplishmentType] = None
    title: Optional[str] = Field(None, min_length=2, max_length=200)
    issuer: Optional[str] = Field(None, max_length=150)
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    credential_url: Optional[str] = None
    document_url: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class AccomplishmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    type: AccomplishmentType
    title: str
    issuer: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    credential_url: Optional[str] = None
    document_url: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime
