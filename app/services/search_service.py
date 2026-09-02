from typing import List, Optional
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.job import Job, JobStatus
from app.models.post import Post
from app.schemas.search import SearchResponse, SearchResultItem

logger = structlog.get_logger()


class SearchService:
    @staticmethod
    async def search(
        db: AsyncSession, query_str: str, search_type: str = "all", limit: int = 20
    ) -> SearchResponse:
        """Global search across active Job opportunities and Campus Discussions."""
        results: List[SearchResultItem] = []
        q = f"%{query_str}%"

        # 1. Search Jobs
        if search_type in ["all", "jobs"]:
            job_query = (
                select(Job)
                .where(
                    or_(
                        Job.title.ilike(q),
                        Job.company_name.ilike(q),
                        Job.description.ilike(q),
                        Job.location.ilike(q),
                    )
                )
                .limit(limit)
            )
            job_res = await db.execute(job_query)
            for j in job_res.scalars().all():
                results.append(
                    SearchResultItem(
                        id=j.id,
                        type="job",
                        title=j.title,
                        subtitle=f"{j.company_name} • {j.ctc}",
                        snippet=(j.description[:140] + "...") if len(j.description) > 140 else j.description,
                        match_score=92 if query_str.lower() in j.title.lower() else 78,
                        url=f"/jobs/{j.id}",
                    )
                )

        # 2. Search Posts
        if search_type in ["all", "posts"]:
            post_query = (
                select(Post)
                .where(or_(Post.title.ilike(q), Post.body.ilike(q)))
                .limit(limit)
            )
            post_res = await db.execute(post_query)
            for p in post_res.scalars().all():
                results.append(
                    SearchResultItem(
                        id=p.id,
                        type="post",
                        title=p.title,
                        subtitle=f"By {p.author_name} • {p.comments_count} comments",
                        snippet=(p.body[:140] + "...") if len(p.body) > 140 else p.body,
                        match_score=85 if query_str.lower() in p.title.lower() else 70,
                        url=f"/feed/posts/{p.id}",
                    )
                )

        # Sort results by match score descending
        results.sort(key=lambda r: r.match_score, reverse=True)

        return SearchResponse(
            query=query_str,
            total_count=len(results),
            results=results[:limit],
        )
