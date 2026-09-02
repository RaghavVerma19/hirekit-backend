import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.post import Post
from app.models.user import User


async def _register_and_login(client: AsyncClient, email: str = "feed@test.com") -> str:
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "name": "Feed Tester",
    })
    res = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password123!",
    })
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_list_posts_empty(client: AsyncClient):
    """Test listing feed posts when empty."""
    res = await client.get("/api/v1/feed/posts")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_add_comment_and_list_posts(client: AsyncClient, db_session: AsyncSession):
    """Test creating a post directly in DB and commenting on it via API."""
    token = await _register_and_login(client, "commenter@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Create dummy user & post in DB
    user_res = await client.get("/api/v1/auth/me", headers=headers)
    user_id = user_res.json()["id"]

    post = Post(
        author_id=user_id,
        author_name="Campus Admin",
        title="Welcome to the 2026 Placement Season",
        body="All companies visiting campus this semester will be listed on the jobs portal.",
        is_pinned=True,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # 1. Add comment
    res_comment = await client.post(
        f"/api/v1/feed/posts/{post.id}/comments",
        json={"content": "Looking forward to the software engineering drives!"},
        headers=headers,
    )
    assert res_comment.status_code == 201
    comment_data = res_comment.json()
    assert comment_data["content"] == "Looking forward to the software engineering drives!"
    assert comment_data["author_name"] == "Feed Tester"

    # 2. List posts
    res_list = await client.get("/api/v1/feed/posts")
    assert res_list.status_code == 200
    posts = res_list.json()["items"]
    assert len(posts) == 1
    assert posts[0]["comments_count"] == 1
    assert len(posts[0]["recent_comments"]) == 1
    assert posts[0]["recent_comments"][0]["content"] == "Looking forward to the software engineering drives!"
