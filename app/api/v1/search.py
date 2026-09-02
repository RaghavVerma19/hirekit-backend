from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.search import SearchResponse
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["Global Search"])


@router.get(
    "",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Global Unified Search",
)
async def search_all(
    q: str = Query(..., min_length=2, description="Search term"),
    type: str = Query("all", pattern="^(all|jobs|posts)$", description="Filter target type"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Search campus placement opportunities and community discussion posts."""
    return await SearchService.search(db, q, type, limit)
