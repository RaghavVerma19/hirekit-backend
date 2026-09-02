from arq.connections import RedisSettings
from arq.cron import cron
import redis.asyncio as aioredis
import structlog

from app.core.config import settings
from app.workers.tasks.digest_email import send_weekly_digest_task
from app.workers.tasks.job_deadlines import check_job_deadlines_task
from app.workers.tasks.leaderboard import recalculate_leaderboard_task
from app.workers.tasks.render_pdf import render_resume_pdf_task

logger = structlog.get_logger()


async def startup(ctx: dict) -> None:
    logger.info("arq_worker_startup")
    ctx["redis"] = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )


async def shutdown(ctx: dict) -> None:
    logger.info("arq_worker_shutdown")
    if "redis" in ctx:
        await ctx["redis"].close()


class WorkerSettings:
    functions = [
        recalculate_leaderboard_task,
        render_resume_pdf_task,
        check_job_deadlines_task,
        send_weekly_digest_task,
    ]
    cron_jobs = [
        # Hourly reconciliation of highest ATS scores into Redis ZSET
        cron(recalculate_leaderboard_task, minute=0),
        # Daily deadline check at midnight (00:00 UTC)
        cron(check_job_deadlines_task, hour=0, minute=0),
        # Weekly digest every Monday at 09:00 UTC
        cron(send_weekly_digest_task, weekday=0, hour=9, minute=0),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
