from typing import Any, Dict, List
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.accomplishment import Accomplishment
from app.models.education import Education
from app.models.experience import Experience
from app.models.guardian import Guardian
from app.models.project import Project
from app.models.skill import UserSkill
from app.models.social_link import SocialLink
from app.models.user import User
from app.schemas.accomplishment import (
    AccomplishmentCreate,
    AccomplishmentOut,
    AccomplishmentUpdate,
)
from app.schemas.common import (
    ConfirmUploadIn,
    MessageOut,
    PresignedUploadIn,
    PresignedUploadOut,
    UploadTargetType,
)
from app.schemas.education import EducationCreate, EducationOut, EducationUpdate
from app.schemas.experience import ExperienceCreate, ExperienceOut, ExperienceUpdate
from app.schemas.guardian import GuardianCreate, GuardianOut, GuardianUpdate
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.schemas.skill import SkillCreate, SkillOut, SkillUpdate
from app.schemas.social_link import SocialLinkCreate, SocialLinkOut
from app.schemas.user import (
    FullProfileOut,
    ProfileBasicUpdate,
    ProfileCompletionOut,
    UserOut,
)
from app.services.profile_service import ProfileService
from app.services.storage_service import StorageService

router = APIRouter(prefix="/profile", tags=["Profile Management"])


# ==================== Core Profile Endpoints ====================

@router.get(
    "",
    response_model=FullProfileOut,
    status_code=status.HTTP_200_OK,
    summary="Get Full Student Profile",
)
@router.get(
    "/me",
    response_model=FullProfileOut,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FullProfileOut:
    """Retrieve full profile graph with all sub-resources and completion score."""
    return await ProfileService.get_full_profile(db, current_user.id)


@router.get(
    "/completion",
    response_model=ProfileCompletionOut,
    status_code=status.HTTP_200_OK,
    summary="Get Profile Completion Score",
)
async def get_profile_completion(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileCompletionOut:
    """Calculate profile completion percentage and next recommended action."""
    profile = await ProfileService.get_full_profile(db, current_user.id)
    return profile.completion


@router.put(
    "/basic",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    summary="Update Basic Profile Info",
)
@router.patch(
    "/basic",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def update_basic_info(
    basic_in: ProfileBasicUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Update whitelisted basic profile details."""
    return await ProfileService.update_basic(db, current_user, basic_in)


@router.patch(
    "/additional-info",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Partial Update Additional Info (21 Questions)",
)
async def patch_additional_info(
    partial_info: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """PATCH merge answers to contextual questions without overwriting existing data."""
    return await ProfileService.update_additional_info(db, current_user, partial_info)


@router.patch(
    "/avatar",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    summary="Upload & Compress Avatar Image",
)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Process uploaded avatar into 256x256 WebP thumbnail and update profile."""
    file_bytes = await file.read()
    webp_bytes = StorageService.process_avatar(file_bytes)

    # In production, upload webp_bytes to S3
    avatar_key = f"uploads/avatar/{current_user.id}/avatar.webp"
    avatar_url = f"{settings.CDN_BASE}/{avatar_key}"

    current_user.avatar_url = avatar_url
    await db.commit()
    await db.refresh(current_user)
    return current_user


# ==================== Document Uploads ====================

@router.post(
    "/upload-document",
    response_model=PresignedUploadOut,
    status_code=status.HTTP_200_OK,
    summary="Generate Presigned S3 Upload URL",
)
@router.post(
    "/upload-url",
    response_model=PresignedUploadOut,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_presigned_upload_url(
    upload_in: PresignedUploadIn,
    current_user: User = Depends(get_current_user),
) -> PresignedUploadOut:
    """Generate temporary presigned upload URL for direct browser-to-S3 upload."""
    return await StorageService.generate_presigned_upload(
        user_id=current_user.id,
        filename=upload_in.filename,
        content_type=upload_in.content_type,
        target_type=upload_in.target_type,
    )


@router.post(
    "/confirm-upload",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Confirm Upload & Link File URL to DB",
)
async def confirm_document_upload(
    confirm_in: ConfirmUploadIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Verify uploaded file on S3 and link URL to target entity."""
    await ProfileService.confirm_upload(db, current_user.id, confirm_in)
    return MessageOut(message="Document uploaded and linked successfully.")


# ==================== Educations ====================

@router.get("/educations", response_model=List[EducationOut], tags=["Education"])
async def list_educations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[EducationOut]:
    result = await db.execute(
        select(Education)
        .where(Education.user_id == current_user.id)
        .order_by(Education.start_year.desc())
    )
    return list(result.scalars().all())


@router.post("/educations", response_model=EducationOut, status_code=status.HTTP_201_CREATED, tags=["Education"])
async def add_education(
    edu_in: EducationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EducationOut:
    return await ProfileService.create_education(db, current_user.id, edu_in)


@router.put("/educations/{edu_id}", response_model=EducationOut, tags=["Education"])
async def update_education(
    edu_id: uuid.UUID,
    edu_in: EducationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EducationOut:
    return await ProfileService.update_education(db, current_user.id, edu_id, edu_in)


@router.delete("/educations/{edu_id}", response_model=MessageOut, tags=["Education"])
async def delete_education(
    edu_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    await ProfileService.delete_education(db, current_user.id, edu_id)
    return MessageOut(message="Education deleted successfully.")


# ==================== Experiences ====================

@router.get("/experiences", response_model=List[ExperienceOut], tags=["Experience"])
async def list_experiences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ExperienceOut]:
    result = await db.execute(
        select(Experience)
        .where(Experience.user_id == current_user.id)
        .options(selectinload(Experience.responsibilities))
        .order_by(Experience.start_date.desc())
    )
    return list(result.scalars().all())


@router.post("/experiences", response_model=ExperienceOut, status_code=status.HTTP_201_CREATED, tags=["Experience"])
async def add_experience(
    exp_in: ExperienceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperienceOut:
    return await ProfileService.create_experience(db, current_user.id, exp_in)


@router.put("/experiences/{exp_id}", response_model=ExperienceOut, tags=["Experience"])
async def update_experience(
    exp_id: uuid.UUID,
    exp_in: ExperienceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperienceOut:
    return await ProfileService.update_experience(db, current_user.id, exp_id, exp_in)


@router.delete("/experiences/{exp_id}", response_model=MessageOut, tags=["Experience"])
async def delete_experience(
    exp_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    await ProfileService.delete_experience(db, current_user.id, exp_id)
    return MessageOut(message="Experience deleted successfully.")


# ==================== Skills ====================

@router.get("/skills", response_model=List[SkillOut], tags=["Skills"])
async def list_skills(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[SkillOut]:
    result = await db.execute(
        select(UserSkill)
        .where(UserSkill.user_id == current_user.id)
        .order_by(UserSkill.name.asc())
    )
    return list(result.scalars().all())


@router.post("/skills", response_model=SkillOut, status_code=status.HTTP_201_CREATED, tags=["Skills"])
async def add_skill(
    skill_in: SkillCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillOut:
    return await ProfileService.create_skill(db, current_user.id, skill_in)


@router.put("/skills/{skill_id}", response_model=SkillOut, tags=["Skills"])
async def update_skill(
    skill_id: uuid.UUID,
    skill_in: SkillUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillOut:
    return await ProfileService.update_skill(db, current_user.id, skill_id, skill_in)


@router.delete("/skills/{skill_id}", response_model=MessageOut, tags=["Skills"])
async def delete_skill(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    await ProfileService.delete_skill(db, current_user.id, skill_id)
    return MessageOut(message="Skill removed successfully.")


# ==================== Projects ====================

@router.get("/projects", response_model=List[ProjectOut], tags=["Projects"])
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ProjectOut]:
    result = await db.execute(
        select(Project)
        .where(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED, tags=["Projects"])
async def add_project(
    proj_in: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    return await ProfileService.create_project(db, current_user.id, proj_in)


@router.put("/projects/{proj_id}", response_model=ProjectOut, tags=["Projects"])
async def update_project(
    proj_id: uuid.UUID,
    proj_in: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    return await ProfileService.update_project(db, current_user.id, proj_id, proj_in)


@router.delete("/projects/{proj_id}", response_model=MessageOut, tags=["Projects"])
async def delete_project(
    proj_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    await ProfileService.delete_project(db, current_user.id, proj_id)
    return MessageOut(message="Project deleted successfully.")


# ==================== Accomplishments ====================

@router.get("/accomplishments", response_model=List[AccomplishmentOut], tags=["Accomplishments"])
async def list_accomplishments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AccomplishmentOut]:
    result = await db.execute(
        select(Accomplishment)
        .where(Accomplishment.user_id == current_user.id)
        .order_by(Accomplishment.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/accomplishments", response_model=AccomplishmentOut, status_code=status.HTTP_201_CREATED, tags=["Accomplishments"])
async def add_accomplishment(
    acc_in: AccomplishmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccomplishmentOut:
    return await ProfileService.create_accomplishment(db, current_user.id, acc_in)


@router.put("/accomplishments/{acc_id}", response_model=AccomplishmentOut, tags=["Accomplishments"])
async def update_accomplishment(
    acc_id: uuid.UUID,
    acc_in: AccomplishmentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccomplishmentOut:
    return await ProfileService.update_accomplishment(db, current_user.id, acc_id, acc_in)


@router.delete("/accomplishments/{acc_id}", response_model=MessageOut, tags=["Accomplishments"])
async def delete_accomplishment(
    acc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    await ProfileService.delete_accomplishment(db, current_user.id, acc_id)
    return MessageOut(message="Accomplishment deleted successfully.")


# ==================== Guardians ====================

@router.get("/guardians", response_model=List[GuardianOut], tags=["Guardians"])
async def list_guardians(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[GuardianOut]:
    result = await db.execute(
        select(Guardian).where(Guardian.user_id == current_user.id)
    )
    return list(result.scalars().all())


@router.post("/guardians", response_model=GuardianOut, status_code=status.HTTP_201_CREATED, tags=["Guardians"])
async def add_guardian(
    guard_in: GuardianCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GuardianOut:
    return await ProfileService.create_guardian(db, current_user.id, guard_in)


@router.put("/guardians/{guard_id}", response_model=GuardianOut, tags=["Guardians"])
async def update_guardian(
    guard_id: uuid.UUID,
    guard_in: GuardianUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GuardianOut:
    return await ProfileService.update_guardian(db, current_user.id, guard_id, guard_in)


@router.delete("/guardians/{guard_id}", response_model=MessageOut, tags=["Guardians"])
async def delete_guardian(
    guard_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    await ProfileService.delete_guardian(db, current_user.id, guard_id)
    return MessageOut(message="Guardian entry removed successfully.")


# ==================== Social Links ====================

@router.get("/social-links", response_model=List[SocialLinkOut], tags=["Social Links"])
async def list_social_links(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[SocialLinkOut]:
    result = await db.execute(
        select(SocialLink).where(SocialLink.user_id == current_user.id)
    )
    return list(result.scalars().all())


@router.post("/social-links", response_model=SocialLinkOut, status_code=status.HTTP_201_CREATED, tags=["Social Links"])
async def add_social_link(
    link_in: SocialLinkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SocialLinkOut:
    return await ProfileService.create_social_link(db, current_user.id, link_in)


@router.delete("/social-links/{link_id}", response_model=MessageOut, tags=["Social Links"])
async def delete_social_link(
    link_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    await ProfileService.delete_social_link(db, current_user.id, link_id)
    return MessageOut(message="Social link removed successfully.")
