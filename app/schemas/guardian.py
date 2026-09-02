from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class GuardianCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    relationship: str = Field("FATHER", max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    occupation: Optional[str] = Field(None, max_length=100)
    annual_income: Optional[str] = Field(None, max_length=50)


class GuardianUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    relationship: Optional[str] = Field(None, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    occupation: Optional[str] = Field(None, max_length=100)
    annual_income: Optional[str] = Field(None, max_length=50)


class GuardianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    relationship: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    occupation: Optional[str] = None
    annual_income: Optional[str] = None
    created_at: datetime
    updated_at: datetime
