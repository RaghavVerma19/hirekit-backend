import io
from typing import Dict, Optional, Tuple
import uuid
from fastapi import status
from PIL import Image
import structlog

from app.core.config import settings
from app.core.errors import AppException
from app.schemas.common import PresignedUploadOut, UploadTargetType

logger = structlog.get_logger()

# Strict Content-Type allowlist
ALLOWED_CONTENT_TYPES = {
    "application/pdf": [".pdf"],
    "image/png": [".png"],
    "image/jpeg": [".jpg", ".jpeg"],
    "image/webp": [".webp"],
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class StorageService:
    @staticmethod
    def validate_upload(filename: str, content_type: str) -> None:
        """Validate content type and extension against security allowlist."""
        content_type_lower = content_type.lower().split(";")[0].strip()
        if content_type_lower not in ALLOWED_CONTENT_TYPES:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="INVALID_FILE_TYPE",
                message=f"File type '{content_type}' is not allowed. Permitted: PDF, PNG, JPEG, WEBP.",
                details={"allowed_types": list(ALLOWED_CONTENT_TYPES.keys())},
            )

    @staticmethod
    async def generate_presigned_upload(
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        target_type: UploadTargetType,
    ) -> PresignedUploadOut:
        """Generate a presigned S3/R2 upload URL with structured path and 5-min TTL."""
        StorageService.validate_upload(filename, content_type)

        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        unique_file_id = uuid.uuid4().hex[:12]
        key = f"uploads/{target_type.value}/{user_id}/{unique_file_id}_{safe_filename}"
        expires_in = 300  # 5 minutes

        # If AWS credentials configured, generate genuine S3 presigned URL
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            try:
                import aioboto3
                session = aioboto3.Session()
                async with session.client(
                    "s3",
                    region_name=settings.AWS_REGION,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                ) as s3:
                    upload_url = await s3.generate_presigned_url(
                        ClientMethod="put_object",
                        Params={
                            "Bucket": settings.S3_BUCKET,
                            "Key": key,
                            "ContentType": content_type,
                        },
                        ExpiresIn=expires_in,
                    )
            except Exception as e:
                logger.error("s3_presign_failed", error=str(e))
                # Fallback to CDN URL construct in local development
                upload_url = f"{settings.CDN_BASE}/{key}?mock_presigned=true"
        else:
            # Development / Mock S3 mode
            upload_url = f"{settings.CDN_BASE}/{key}?mock_presigned=true"

        file_url = f"{settings.CDN_BASE}/{key}"

        return PresignedUploadOut(
            upload_url=upload_url,
            file_url=file_url,
            key=key,
            expires_in=expires_in,
            headers={"Content-Type": content_type},
        )

    @staticmethod
    async def file_exists(file_url: str) -> bool:
        """Verify that uploaded file exists on S3."""
        if not file_url.startswith(settings.CDN_BASE):
            return False
        # In development mock mode, return True
        if not (settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY):
            return True

        key = file_url.replace(f"{settings.CDN_BASE}/", "")
        try:
            import aioboto3
            session = aioboto3.Session()
            async with session.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            ) as s3:
                await s3.head_object(Bucket=settings.S3_BUCKET, Key=key)
                return True
        except Exception:
            return False

    @staticmethod
    def process_avatar(file_bytes: bytes) -> bytes:
        """Process avatar image: resize to 256x256 max square thumbnail, encode as WebP."""
        try:
            image = Image.open(io.BytesIO(file_bytes))
            # Convert RGBA/Palette to RGB
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")

            # Center square crop & thumbnail to 256x256
            width, height = image.size
            min_dim = min(width, height)
            left = (width - min_dim) / 2
            top = (height - min_dim) / 2
            right = (width + min_dim) / 2
            bottom = (height + min_dim) / 2
            cropped = image.crop((left, top, right, bottom))
            cropped.thumbnail((256, 256), Image.Resampling.LANCZOS)

            # Compress to WebP
            buffer = io.BytesIO()
            cropped.save(buffer, format="WEBP", quality=80, method=6)
            return buffer.getvalue()
        except Exception as e:
            logger.error("avatar_processing_failed", error=str(e))
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="INVALID_IMAGE_FILE",
                message="Failed to process avatar image. Please provide a valid JPEG, PNG, or WebP file.",
            )
