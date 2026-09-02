import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def _register_and_get_token(client: AsyncClient, email: str = "user@test.com", name: str = "Test User") -> str:
    """Helper to register and login a user, returning their access token."""
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "name": name,
    })
    res = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password123!",
    })
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_get_empty_profile(client: AsyncClient):
    """Test fetching empty profile graph for a newly registered user."""
    token = await _register_and_get_token(client, "empty@test.com", "Empty User")
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.get("/api/v1/profile", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == "empty@test.com"
    assert data["educations"] == []
    assert data["skills"] == []
    assert data["projects"] == []
    assert data["completion"]["percentage"] < 30
    assert data["completion"]["is_job_ready"] is False


@pytest.mark.asyncio
async def test_update_basic_profile(client: AsyncClient):
    """Test updating basic profile details."""
    token = await _register_and_get_token(client, "basic@test.com", "Basic User")
    headers = {"Authorization": f"Bearer {token}"}

    update_payload = {
        "headline": "Full Stack Developer",
        "phone": "+919876543210",
        "location": "Jaipur, Rajasthan",
        "summary": "Passionate software engineer building modern web applications.",
    }
    res = await client.put("/api/v1/profile/basic", json=update_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["headline"] == "Full Stack Developer"
    assert data["phone"] == "+919876543210"
    assert data["location"] == "Jaipur, Rajasthan"


@pytest.mark.asyncio
async def test_mass_assignment_protection(client: AsyncClient, db_session: AsyncSession):
    """Test that attempting to inject role=ADMIN in basic profile update is ignored."""
    token = await _register_and_get_token(client, "hacker@test.com", "Hacker")
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.put("/api/v1/profile/basic", json={
        "name": "Legit Name",
        "role": "ADMIN",
        "is_verified": True,
    }, headers=headers)
    assert res.status_code == 200

    # Verify user in database is still STUDENT and unverified
    user = await db_session.scalar(select(User).where(User.email == "hacker@test.com"))
    assert user.role == "STUDENT"
    assert user.is_verified is False


@pytest.mark.asyncio
async def test_education_crud(client: AsyncClient):
    """Test education creation, update, and deletion."""
    token = await _register_and_get_token(client, "edu@test.com", "Edu User")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create Education
    create_payload = {
        "degree": "B.Tech",
        "department": "Computer Science & Engineering",
        "institution": "Poornima University",
        "start_year": 2022,
        "end_year": 2026,
        "cgpa": 8.75,
        "is_current": True,
        "semester_scores": [
            {"semester": 1, "sgpa": 8.5, "credits": 24},
            {"semester": 2, "sgpa": 9.0, "credits": 24},
        ],
    }
    res_create = await client.post("/api/v1/profile/educations", json=create_payload, headers=headers)
    assert res_create.status_code == 201
    edu = res_create.json()
    assert edu["degree"] == "B.Tech"
    assert edu["cgpa"] == 8.75
    edu_id = edu["id"]

    # 2. List Educations
    res_list = await client.get("/api/v1/profile/educations", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # 3. Update Education
    res_update = await client.put(f"/api/v1/profile/educations/{edu_id}", json={"cgpa": 9.1}, headers=headers)
    assert res_update.status_code == 200
    assert res_update.json()["cgpa"] == 9.1

    # 4. Delete Education
    res_del = await client.delete(f"/api/v1/profile/educations/{edu_id}", headers=headers)
    assert res_del.status_code == 200

    res_list_after = await client.get("/api/v1/profile/educations", headers=headers)
    assert len(res_list_after.json()) == 0


@pytest.mark.asyncio
async def test_skill_normalization_and_duplicate(client: AsyncClient):
    """Test skill name auto-normalization and duplicate rejection."""
    token = await _register_and_get_token(client, "skills@test.com", "Skills User")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create Skill "react.js"
    res1 = await client.post("/api/v1/profile/skills", json={"name": "react.js", "level": "ADVANCED"}, headers=headers)
    assert res1.status_code == 201
    assert res1.json()["name"] == "React.Js"

    # 2. Duplicate Skill "React.js"
    res2 = await client.post("/api/v1/profile/skills", json={"name": "React.Js", "level": "BEGINNER"}, headers=headers)
    assert res2.status_code == 409
    assert res2.json()["error"] == "SKILL_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_experience_with_responsibilities(client: AsyncClient):
    """Test creating experience with nested responsibility bullet points."""
    token = await _register_and_get_token(client, "exp@test.com", "Exp User")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "role": "Frontend Intern",
        "company": "Tech Corp",
        "location": "Remote",
        "type": "INTERNSHIP",
        "start_date": "2024-01-10",
        "end_date": "2024-06-30",
        "is_current": False,
        "responsibilities": [
            "Built responsive UI components using React and Tailwind CSS",
            "Improved page load performance by 35%",
        ],
    }
    res = await client.post("/api/v1/profile/experiences", json=payload, headers=headers)
    assert res.status_code == 201
    exp = res.json()
    assert exp["role"] == "Frontend Intern"
    assert len(exp["responsibilities"]) == 2
    assert exp["responsibilities"][0]["description"] == "Built responsive UI components using React and Tailwind CSS"


@pytest.mark.asyncio
async def test_idor_protection_other_user_resource(client: AsyncClient):
    """Test that User A cannot modify or delete User B's resources (returns 404)."""
    token_a = await _register_and_get_token(client, "usera@test.com", "User A")
    token_b = await _register_and_get_token(client, "userb@test.com", "User B")

    # User A creates education
    res_a = await client.post(
        "/api/v1/profile/educations",
        json={"degree": "B.Tech", "institution": "College A", "start_year": 2021},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    edu_id = res_a.json()["id"]

    # User B tries to update User A's education
    res_b_update = await client.put(
        f"/api/v1/profile/educations/{edu_id}",
        json={"institution": "Hacked College"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b_update.status_code == 404
    assert res_b_update.json()["error"] == "RESOURCE_NOT_FOUND"

    # User B tries to delete User A's education
    res_b_del = await client.delete(
        f"/api/v1/profile/educations/{edu_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b_del.status_code == 404


@pytest.mark.asyncio
async def test_additional_info_patch_merge(client: AsyncClient):
    """Test partial answers to 21 questions merge without wiping unmentioned keys."""
    token = await _register_and_get_token(client, "info@test.com", "Info User")
    headers = {"Authorization": f"Bearer {token}"}

    # Step 1: answer 2 questions
    res1 = await client.patch("/api/v1/profile/additional-info", json={
        "willing_to_relocate": True,
        "blood_group": "O+",
    }, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["willing_to_relocate"] is True
    assert res1.json()["blood_group"] == "O+"

    # Step 2: answer 1 new question (the previous 2 must remain intact)
    res2 = await client.patch("/api/v1/profile/additional-info", json={
        "expected_ctc": "12 LPA",
    }, headers=headers)
    assert res2.status_code == 200
    data = res2.json()
    assert data["willing_to_relocate"] is True
    assert data["blood_group"] == "O+"
    assert data["expected_ctc"] == "12 LPA"


@pytest.mark.asyncio
async def test_presigned_upload_validation(client: AsyncClient):
    """Test generating presigned S3 upload URL with validation."""
    token = await _register_and_get_token(client, "upload@test.com", "Upload User")
    headers = {"Authorization": f"Bearer {token}"}

    # Valid PDF upload request
    res = await client.post("/api/v1/profile/upload-document", json={
        "filename": "marksheet_sem4.pdf",
        "content_type": "application/pdf",
        "target_type": "education",
    }, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "upload_url" in data
    assert "file_url" in data
    assert data["key"].startswith("uploads/education/")

    # Invalid executable/script upload request
    res_bad = await client.post("/api/v1/profile/upload-document", json={
        "filename": "malware.exe",
        "content_type": "application/x-msdownload",
        "target_type": "education",
    }, headers=headers)
    assert res_bad.status_code == 400
    assert res_bad.json()["error"] == "INVALID_FILE_TYPE"
