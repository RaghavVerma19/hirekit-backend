from typing import Optional
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.post import CommentCreate, CommentOut, CursorPage, PostOut
from app.services.feed_service import FeedService

router = APIRouter(prefix="/feed", tags=["Campus Feed & Discussions"])


@router.get(
    "/posts",
    response_model=CursorPage[PostOut],
    status_code=status.HTTP_200_OK,
    summary="List Feed Posts (Cursor Paginated)",
)
async def list_posts(
    cursor: Optional[str] = Query(None, description="Base64 encoded pagination cursor"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> CursorPage[PostOut]:
    """Retrieve campus discussions with cursor pagination for infinite scrolling."""
    return await FeedService.list_posts(db, cursor, limit)


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add Comment to Post",
)
async def add_comment(
    post_id: uuid.UUID,
    comment_in: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentOut:
    """Add a verified student/alumni comment to a post."""
    return await FeedService.add_comment(db, current_user, post_id, comment_in)
