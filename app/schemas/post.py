from datetime import datetime
from typing import Generic, List, Optional, TypeVar
import uuid
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    post_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    author_avatar: Optional[str] = None
    content: str
    created_at: datetime


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    author_avatar: Optional[str] = None
    title: str
    body: str
    likes_count: int
    comments_count: int
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    recent_comments: List[CommentOut] = []


class CursorPage(BaseModel, Generic[T]):
    items: List[T]
    next_cursor: Optional[str] = None
    has_more: bool = False
