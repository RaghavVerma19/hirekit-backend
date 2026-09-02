import base64
from datetime import datetime
import json
from typing import Optional, Tuple
import uuid
from fastapi import status
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppException
from app.models.post import Post, PostComment
from app.models.user import User
from app.schemas.post import CommentCreate, CommentOut, CursorPage, PostOut


def encode_cursor(created_at: datetime, item_id: uuid.UUID) -> str:
    """Encode created_at and id into opaque base64 string."""
    payload = {"t": created_at.isoformat(), "id": str(item_id)}
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def decode_cursor(cursor: str) -> Tuple[datetime, uuid.UUID]:
    """Decode base64 cursor string."""
    try:
        raw = base64.b64decode(cursor.encode("utf-8")).decode("utf-8")
        payload = json.loads(raw)
        return datetime.fromisoformat(payload["t"]), uuid.UUID(payload["id"])
    except Exception:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_CURSOR",
            message="Invalid pagination cursor.",
        )


class FeedService:
    @staticmethod
    async def list_posts(
        db: AsyncSession, cursor: Optional[str] = None, limit: int = 10
    ) -> CursorPage[PostOut]:
        """Fetch posts with cursor pagination and top 2 recent comments."""
        query = (
            select(Post)
            .options(selectinload(Post.comments))
            .order_by(Post.is_pinned.desc(), Post.created_at.desc(), Post.id.desc())
            .limit(limit + 1)
        )

        if cursor:
            t, item_id = decode_cursor(cursor)
            query = query.where(
                (Post.created_at < t) | ((Post.created_at == t) & (Post.id < item_id))
            )

        result = await db.execute(query)
        posts = list(result.scalars().all())

        has_more = len(posts) > limit
        items_to_return = posts[:limit]

        next_cursor = None
        if has_more and items_to_return:
            last_item = items_to_return[-1]
            next_cursor = encode_cursor(last_item.created_at, last_item.id)

        formatted_items = []
        for p in items_to_return:
            comments_out = [
                CommentOut.model_validate(c) for c in (p.comments[-2:] if p.comments else [])
            ]
            post_out = PostOut(
                id=p.id,
                author_id=p.author_id,
                author_name=p.author_name,
                author_avatar=p.author_avatar,
                title=p.title,
                body=p.body,
                likes_count=p.likes_count,
                comments_count=p.comments_count,
                is_pinned=p.is_pinned,
                created_at=p.created_at,
                updated_at=p.updated_at,
                recent_comments=comments_out,
            )
            formatted_items.append(post_out)

        return CursorPage(
            items=formatted_items,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    @staticmethod
    async def add_comment(
        db: AsyncSession, user: User, post_id: uuid.UUID, comment_in: CommentCreate
    ) -> CommentOut:
        """Add a comment to a post and increment comments counter."""
        post = await db.get(Post, post_id)
        if not post:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="POST_NOT_FOUND",
                message="Post not found.",
            )

        comment = PostComment(
            post_id=post.id,
            author_id=user.id,
            author_name=user.name,
            author_avatar=user.avatar_url,
            content=comment_in.content,
        )
        db.add(comment)

        # Increment count
        post.comments_count += 1
        await db.commit()
        await db.refresh(comment)

        return CommentOut.model_validate(comment)
