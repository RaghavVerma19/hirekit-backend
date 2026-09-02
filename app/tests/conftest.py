from typing import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.redis import get_redis
from app.db.session import get_db
from app.main import app as fastapi_app
import app.models  # Register all models with Base.metadata

# Use an async in-memory SQLite database for fast isolated unit/integration tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class MockRedis:
    """In-memory mock for Redis client in tests."""
    def __init__(self):
        self._store = {}
        self._zsets = {}

    async def ping(self):
        return True

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int = None, nx: bool = False):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def delete(self, *keys: str):
        for k in keys:
            self._store.pop(k, None)
            self._zsets.pop(k, None)
        return True

    async def publish(self, channel: str, message: str):
        return 1

    async def zadd(self, name: str, mapping: dict):
        if name not in self._zsets:
            self._zsets[name] = {}
        for member, score in mapping.items():
            self._zsets[name][str(member)] = float(score)
        return len(mapping)

    async def zscore(self, name: str, member: str):
        if name not in self._zsets or str(member) not in self._zsets[name]:
            return None
        return self._zsets[name][str(member)]

    async def zrevrank(self, name: str, member: str):
        if name not in self._zsets or str(member) not in self._zsets[name]:
            return None
        sorted_members = sorted(self._zsets[name].items(), key=lambda x: x[1], reverse=True)
        for rank, (m, _) in enumerate(sorted_members):
            if m == str(member):
                return rank
        return None

    async def zcard(self, name: str):
        if name not in self._zsets:
            return 0
        return len(self._zsets[name])

    async def zcount(self, name: str, min_val, max_val):
        if name not in self._zsets:
            return 0
        return len([s for s in self._zsets[name].values() if float(min_val) <= s <= float(max_val)])

    async def zrevrange(self, name: str, start: int, end: int, withscores: bool = False):
        if name not in self._zsets:
            return []
        sorted_members = sorted(self._zsets[name].items(), key=lambda x: x[1], reverse=True)
        slice_members = sorted_members[start : (end + 1) if end != -1 else None]
        if withscores:
            return slice_members
        return [m for m, _ in slice_members]

    async def close(self):
        pass


@pytest.fixture(scope="function", autouse=True)
async def setup_test_db():
    """Create all database tables before each test and drop them after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields a test database session."""
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture
def mock_redis() -> MockRedis:
    """Yields an in-memory mock Redis instance."""
    return MockRedis()


@pytest.fixture
async def client(db_session: AsyncSession, mock_redis: MockRedis) -> AsyncGenerator[AsyncClient, None]:
    """Yields an async HTTP test client with overridden dependencies."""
    async def override_get_db():
        yield db_session

    async def override_get_redis():
        yield mock_redis

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()
