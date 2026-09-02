from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application Settings
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Hirekit Backend"

    # Security
    JWT_SECRET_KEY: str = "dev-secret-key-hirekit-please-change-in-production-min-32-chars-long"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 30

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://hirekit:hirekit@localhost:5433/hirekit"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # S3 / Cloudflare R2
    S3_BUCKET: str = "hirekit-uploads"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-south-1"
    CDN_BASE: str = "https://cdn.hirekit.com"

    # AI (Gemini)
    GEMINI_API_KEY: str = ""

    # Email
    SENDGRID_API_KEY: str = ""
    FROM_EMAIL: str = "noreply@hirekit.com"

    # Sentry
    SENTRY_DSN: str = ""

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return ["http://localhost:3000", "http://127.0.0.1:3000"]


settings = Settings()
