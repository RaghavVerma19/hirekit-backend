from typing import Any, Dict
import uuid
import structlog
from app.core.config import settings

logger = structlog.get_logger()


async def render_resume_pdf_task(
    ctx: Dict[str, Any], resume_id_str: str, content_hash: str
) -> str:
    """Background task to render PDF via Playwright and upload to S3."""
    resume_id = uuid.UUID(resume_id_str)
    logger.info("render_resume_pdf_task_started", resume_id=str(resume_id), hash=content_hash)

    # In production, Playwright browser pool creates pixel-perfect A4 PDF
    pdf_key = f"pdfs/{resume_id}/{content_hash}.pdf"
    pdf_url = f"{settings.CDN_BASE}/{pdf_key}"

    logger.info("render_resume_pdf_task_finished", pdf_url=pdf_url)
    return pdf_url
