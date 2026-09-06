from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict
from app.schemas.user import UserOut


class LeaderboardEntryOut(BaseModel):
    rank: int
    user_id: uuid.UUID
    name: str
    avatar: Optional[str] = None
    score: int
    department: str
    batch: str
    role: Optional[str] = None


class LinkedInScoreOut(BaseModel):
    profile_score: int
    headline_score: int
    experience_score: int
    network_score: int
    views: int
    impressions: int
    appearances: int
    updated_at: str


class MyRankOut(BaseModel):
    rank: int
    percentile: float
    total_students: int
    my_score: int
    top_score: int
    improvement_this_week: int
    recommendation_tip: str


class DashboardOverviewOut(BaseModel):
    user: UserOut
    active_jobs_count: int = 0
    applications_count: int = 0
    upcoming_interviews_count: int = 0
    leaderboard: List[LeaderboardEntryOut] = []
    linkedin: Optional[LinkedInScoreOut] = None
    announcements: List[Dict[str, Any]] = []
