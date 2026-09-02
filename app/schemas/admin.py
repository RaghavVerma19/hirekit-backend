from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict
from app.models.application import ApplicationStatus


class BulkVerifyIn(BaseModel):
    user_ids: List[uuid.UUID]


class BulkStatusUpdateIn(BaseModel):
    application_ids: List[uuid.UUID]
    status: ApplicationStatus
    note: Optional[str] = None


class AdminAnalyticsOverviewOut(BaseModel):
    placement_rate_percent: float
    total_students: int
    placed_students: int
    avg_ctc_lpa: str
    highest_ctc_lpa: str
    active_job_drives: int
    offers_count: int


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID
    action: str
    target_type: str
    target_id: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
