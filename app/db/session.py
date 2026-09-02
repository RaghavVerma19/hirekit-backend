from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings

# Async Engine with production-optimized connection pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG and settings.ENVIRONMENT == "development",
    pool_size=5,
    max_overflow=2,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for yielding async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
