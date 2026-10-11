from typing import Any, Dict
import uuid
import structlog
from app.core.config import settings

logger = structlog.get_logger()


async def render_resume_pdf_task(
    ctx: Dict[str, Any], resume_id_str: str, content_hash: str
) -> str:
    """Compile stored latex_source via external LaTeX API and upload to S3.

    Replaces previous stub that returned a fake CDN URL without compiling.
    Returns real pdf_url on success; raises on failure so ARQ retries/logs.
    """
    from app.db.session import AsyncSessionLocal
    from app.models.resume import Resume
    from app.services.latex_compile_service import compile_latex_source, source_hash

    resume_id = uuid.UUID(resume_id_str)
    logger.info("render_resume_pdf_task_started", resume_id=str(resume_id), hash=content_hash)

    async with AsyncSessionLocal() as session:
        resume = await session.get(Resume, resume_id)
        if not resume:
            raise ValueError(f"Resume {resume_id} not found")
        source = str((resume.content_json or {}).get("latex_source") or "")
        if "\\begin{document}" not in source:
            raise ValueError("No complete latex_source to compile")

        result = await compile_latex_source(source)
        if not result.get("success") or not result.get("pdf_bytes"):
            raise RuntimeError(f"LaTeX compile failed: {result.get('log', '')[:500]}")

        pdf_bytes: bytes = result["pdf_bytes"]
        key_hash = source_hash(source)
        pdf_key = f"pdfs/{resume_id}/{key_hash}.pdf"

        from app.services.storage_service import StorageService
        if not StorageService._is_mock_storage():
            import aioboto3
            aiosession = aioboto3.Session()
            async with aiosession.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            ) as s3:
                await s3.put_object(Bucket=settings.S3_BUCKET, Key=pdf_key, Body=pdf_bytes, ContentType="application/pdf")

        pdf_url = f"{settings.CDN_BASE}/{pdf_key}"
        content = dict(resume.content_json or {})
        content["compiled_pdf_url"] = pdf_url
        resume.content_json = content
        resume.pdf_url = pdf_url
        await session.commit()

    logger.info("render_resume_pdf_task_finished", pdf_url=pdf_url)
    return pdf_url
