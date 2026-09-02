from typing import Any, Dict, List, Optional
import uuid
from fastapi import status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.core.errors import AppException
from app.models.accomplishment import Accomplishment
from app.models.education import Education
from app.models.experience import Experience, Responsibility
from app.models.guardian import Guardian
from app.models.project import Project
from app.models.skill import UserSkill
from app.models.social_link import SocialLink
from app.models.user import User
from app.schemas.accomplishment import AccomplishmentCreate, AccomplishmentUpdate
from app.schemas.common import ConfirmUploadIn, UploadTargetType
from app.schemas.education import EducationCreate, EducationUpdate
from app.schemas.experience import ExperienceCreate, ExperienceUpdate
from app.schemas.guardian import GuardianCreate, GuardianUpdate
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.schemas.skill import SkillCreate, SkillUpdate
from app.schemas.social_link import SocialLinkCreate
from app.schemas.user import FullProfileOut, ProfileBasicUpdate, ProfileCompletionOut
from app.services.storage_service import StorageService

logger = structlog.get_logger()

# Resource Caps to prevent unbounded table growth / DB bloat
MAX_EDUCATIONS = 10
MAX_EXPERIENCES = 20
MAX_SKILLS = 50
MAX_PROJECTS = 15
MAX_ACCOMPLISHMENTS = 30
MAX_GUARDIANS = 5
MAX_SOCIAL_LINKS = 10


class ProfileService:
    @staticmethod
    def calculate_completion(
        user: User,
        educations: List[Education],
        experiences: List[Experience],
        skills: List[UserSkill],
        projects: List[Project],
        accomplishments: List[Accomplishment],
    ) -> ProfileCompletionOut:
        """Calculate dynamic profile completion score and actionable guidance."""
        score = 0
        completed: List[str] = []
        missing: List[str] = []

        # 1. Basic Info (Name, Phone, Location) -> 15%
        if user.name and user.phone and user.location:
            score += 15
            completed.append("Basic Information")
        else:
            missing.append("Complete Basic Information (+15%)")

        # 2. Education details -> 20%
        if len(educations) > 0:
            score += 20
            completed.append("Education Details")
        else:
            missing.append("Add University/College Education (+20%)")

        # 3. Marksheet upload -> 15%
        has_marksheet = any(e.marksheet_url for e in educations)
        if has_marksheet:
            score += 15
            completed.append("Verified Marksheet")
        else:
            missing.append("Upload Latest Marksheet (+15%)")

        # 4. Skills (at least 3) -> 15%
        if len(skills) >= 3:
            score += 15
            completed.append("Key Skills")
        else:
            missing.append(f"Add {max(1, 3 - len(skills))} more skill(s) (+15%)")

        # 5. Projects (at least 1) -> 15%
        if len(projects) >= 1:
            score += 15
            completed.append("Projects")
        else:
            missing.append("Add at least 1 Project (+15%)")

        # 6. Work Experience / Internship -> 10%
        if len(experiences) >= 1:
            score += 10
            completed.append("Work Experience")
        else:
            missing.append("Add Internship / Work Experience (+10%)")

        # 7. Accomplishments / Certifications -> 10%
        if len(accomplishments) >= 1:
            score += 10
            completed.append("Certifications / Accomplishments")
        else:
            missing.append("Add Certifications or Awards (+10%)")

        score = min(100, score)

        # Determine next actionable recommendation
        if not educations:
            next_action = "Add your university degree details to get started."
        elif not has_marksheet:
            next_action = "Upload your semester marksheet to qualify for verified job drives."
        elif len(skills) < 3:
            next_action = "Add 3 core skills so AI can match you to top recruiter criteria."
        elif not projects:
            next_action = "Showcase a project to boost your profile visibility."
        elif score < 80:
            next_action = "Add work experience or certifications to achieve 80%+ job readiness."
        else:
            next_action = "Your profile is in top shape! You are eligible for all placement drives."

        return ProfileCompletionOut(
            percentage=score,
            completed_sections=completed,
            missing_sections=missing,
            next_action=next_action,
            is_job_ready=score >= 70,
        )

    @staticmethod
    async def get_full_profile(db: AsyncSession, user_id: uuid.UUID) -> FullProfileOut:
        """Fetch entire profile graph in an optimized single query with joined relationships."""
        result = await db.execute(
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.educations),
                selectinload(User.experiences).selectinload(Experience.responsibilities),
                selectinload(User.skills),
                selectinload(User.projects),
                selectinload(User.accomplishments),
                selectinload(User.guardians),
                selectinload(User.social_links),
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="USER_NOT_FOUND",
                message="User profile not found.",
            )

        completion = ProfileService.calculate_completion(
            user=user,
            educations=user.educations,
            experiences=user.experiences,
            skills=user.skills,
            projects=user.projects,
            accomplishments=user.accomplishments,
        )

        return FullProfileOut(
            user=user,
            educations=user.educations,
            experiences=user.experiences,
            skills=user.skills,
            projects=user.projects,
            accomplishments=user.accomplishments,
            guardians=user.guardians,
            social_links=user.social_links,
            additional_info=user.additional_info,
            completion=completion,
        )

    @staticmethod
    async def update_basic(
        db: AsyncSession, user: User, basic_in: ProfileBasicUpdate
    ) -> User:
        """Update whitelisted basic profile fields (protecting system/role flags)."""
        update_data = basic_in.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(user, key, value)

        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def update_additional_info(
        db: AsyncSession, user: User, partial_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """PATCH merge for the 21 contextual questions (no data loss on partial save)."""
        current_info = dict(user.additional_info or {})
        current_info.update(partial_data)
        user.additional_info = current_info
        await db.commit()
        return user.additional_info

    # ------------------ Educations CRUD ------------------
    @staticmethod
    async def create_education(
        db: AsyncSession, user_id: uuid.UUID, edu_in: EducationCreate
    ) -> Education:
        count = await db.scalar(
            select(func.count(Education.id)).where(Education.user_id == user_id)
        )
        if count >= MAX_EDUCATIONS:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="CAP_EXCEEDED",
                message=f"Maximum of {MAX_EDUCATIONS} education entries allowed.",
            )

        edu_dict = edu_in.model_dump()
        semester_scores = [s.model_dump() if hasattr(s, "model_dump") else s for s in (edu_in.semester_scores or [])]
        edu_dict["semester_scores"] = semester_scores

        education = Education(user_id=user_id, **edu_dict)
        db.add(education)
        await db.commit()
        await db.refresh(education)
        return education

    @staticmethod
    async def update_education(
        db: AsyncSession, user_id: uuid.UUID, edu_id: uuid.UUID, update_in: EducationUpdate
    ) -> Education:
        edu = await db.get(Education, edu_id)
        if not edu or edu.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Education entry not found.",
            )

        update_dict = update_in.model_dump(exclude_unset=True)
        if "semester_scores" in update_dict and update_dict["semester_scores"] is not None:
            update_dict["semester_scores"] = [
                s.model_dump() if hasattr(s, "model_dump") else s for s in update_dict["semester_scores"]
            ]

        for key, value in update_dict.items():
            setattr(edu, key, value)

        await db.commit()
        await db.refresh(edu)
        return edu

    @staticmethod
    async def delete_education(
        db: AsyncSession, user_id: uuid.UUID, edu_id: uuid.UUID
    ) -> None:
        edu = await db.get(Education, edu_id)
        if not edu or edu.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Education entry not found.",
            )
        await db.delete(edu)
        await db.commit()

    # ------------------ Experiences CRUD ------------------
    @staticmethod
    async def create_experience(
        db: AsyncSession, user_id: uuid.UUID, exp_in: ExperienceCreate
    ) -> Experience:
        count = await db.scalar(
            select(func.count(Experience.id)).where(Experience.user_id == user_id)
        )
        if count >= MAX_EXPERIENCES:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="CAP_EXCEEDED",
                message=f"Maximum of {MAX_EXPERIENCES} experience entries allowed.",
            )

        exp_dict = exp_in.model_dump(exclude={"responsibilities"})
        experience = Experience(user_id=user_id, **exp_dict)
        db.add(experience)
        await db.flush()

        # Add responsibilities
        if exp_in.responsibilities:
            for idx, desc in enumerate(exp_in.responsibilities):
                resp = Responsibility(
                    experience_id=experience.id,
                    description=desc,
                    order_index=idx,
                )
                db.add(resp)

        await db.commit()
        await db.refresh(experience)
        # Eager load responsibilities
        res = await db.execute(
            select(Experience)
            .where(Experience.id == experience.id)
            .options(selectinload(Experience.responsibilities))
        )
        return res.scalar_one()

    @staticmethod
    async def update_experience(
        db: AsyncSession, user_id: uuid.UUID, exp_id: uuid.UUID, update_in: ExperienceUpdate
    ) -> Experience:
        exp = await db.get(Experience, exp_id)
        if not exp or exp.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Experience entry not found.",
            )

        update_dict = update_in.model_dump(exclude_unset=True, exclude={"responsibilities"})
        for key, value in update_dict.items():
            setattr(exp, key, value)

        # Replace responsibilities if specified
        if update_in.responsibilities is not None:
            await db.execute(
                delete(Responsibility).where(Responsibility.experience_id == exp_id)
            )
            for idx, desc in enumerate(update_in.responsibilities):
                resp = Responsibility(
                    experience_id=exp.id,
                    description=desc,
                    order_index=idx,
                )
                db.add(resp)

        await db.commit()
        res = await db.execute(
            select(Experience)
            .where(Experience.id == exp_id)
            .options(selectinload(Experience.responsibilities))
        )
        return res.scalar_one()

    @staticmethod
    async def delete_experience(
        db: AsyncSession, user_id: uuid.UUID, exp_id: uuid.UUID
    ) -> None:
        exp = await db.get(Experience, exp_id)
        if not exp or exp.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Experience entry not found.",
            )
        await db.delete(exp)
        await db.commit()

    # ------------------ Skills CRUD ------------------
    @staticmethod
    async def create_skill(
        db: AsyncSession, user_id: uuid.UUID, skill_in: SkillCreate
    ) -> UserSkill:
        count = await db.scalar(
            select(func.count(UserSkill.id)).where(UserSkill.user_id == user_id)
        )
        if count >= MAX_SKILLS:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="CAP_EXCEEDED",
                message=f"Maximum of {MAX_SKILLS} skills allowed.",
            )

        # Check for duplicate
        existing = await db.scalar(
            select(UserSkill).where(
                UserSkill.user_id == user_id,
                UserSkill.name == skill_in.name,
            )
        )
        if existing:
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                error_code="SKILL_ALREADY_EXISTS",
                message=f"Skill '{skill_in.name}' is already on your profile.",
            )

        skill = UserSkill(
            user_id=user_id,
            name=skill_in.name,
            level=skill_in.level,
            is_verified=False,
        )
        db.add(skill)
        await db.commit()
        await db.refresh(skill)
        return skill

    @staticmethod
    async def update_skill(
        db: AsyncSession, user_id: uuid.UUID, skill_id: uuid.UUID, update_in: SkillUpdate
    ) -> UserSkill:
        skill = await db.get(UserSkill, skill_id)
        if not skill or skill.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Skill not found.",
            )
        skill.level = update_in.level
        await db.commit()
        await db.refresh(skill)
        return skill

    @staticmethod
    async def delete_skill(
        db: AsyncSession, user_id: uuid.UUID, skill_id: uuid.UUID
    ) -> None:
        skill = await db.get(UserSkill, skill_id)
        if not skill or skill.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Skill not found.",
            )
        await db.delete(skill)
        await db.commit()

    # ------------------ Projects CRUD ------------------
    @staticmethod
    async def create_project(
        db: AsyncSession, user_id: uuid.UUID, proj_in: ProjectCreate
    ) -> Project:
        count = await db.scalar(
            select(func.count(Project.id)).where(Project.user_id == user_id)
        )
        if count >= MAX_PROJECTS:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="CAP_EXCEEDED",
                message=f"Maximum of {MAX_PROJECTS} projects allowed.",
            )

        project = Project(user_id=user_id, **proj_in.model_dump())
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return project

    @staticmethod
    async def update_project(
        db: AsyncSession, user_id: uuid.UUID, proj_id: uuid.UUID, update_in: ProjectUpdate
    ) -> Project:
        proj = await db.get(Project, proj_id)
        if not proj or proj.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Project not found.",
            )
        for key, value in update_in.model_dump(exclude_unset=True).items():
            setattr(proj, key, value)

        await db.commit()
        await db.refresh(proj)
        return proj

    @staticmethod
    async def delete_project(
        db: AsyncSession, user_id: uuid.UUID, proj_id: uuid.UUID
    ) -> None:
        proj = await db.get(Project, proj_id)
        if not proj or proj.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Project not found.",
            )
        await db.delete(proj)
        await db.commit()

    # ------------------ Accomplishments CRUD ------------------
    @staticmethod
    async def create_accomplishment(
        db: AsyncSession, user_id: uuid.UUID, acc_in: AccomplishmentCreate
    ) -> Accomplishment:
        count = await db.scalar(
            select(func.count(Accomplishment.id)).where(Accomplishment.user_id == user_id)
        )
        if count >= MAX_ACCOMPLISHMENTS:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="CAP_EXCEEDED",
                message=f"Maximum of {MAX_ACCOMPLISHMENTS} accomplishments allowed.",
            )

        acc = Accomplishment(user_id=user_id, **acc_in.model_dump())
        db.add(acc)
        await db.commit()
        await db.refresh(acc)
        return acc

    @staticmethod
    async def update_accomplishment(
        db: AsyncSession, user_id: uuid.UUID, acc_id: uuid.UUID, update_in: AccomplishmentUpdate
    ) -> Accomplishment:
        acc = await db.get(Accomplishment, acc_id)
        if not acc or acc.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Accomplishment not found.",
            )
        for key, value in update_in.model_dump(exclude_unset=True).items():
            setattr(acc, key, value)

        await db.commit()
        await db.refresh(acc)
        return acc

    @staticmethod
    async def delete_accomplishment(
        db: AsyncSession, user_id: uuid.UUID, acc_id: uuid.UUID
    ) -> None:
        acc = await db.get(Accomplishment, acc_id)
        if not acc or acc.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Accomplishment not found.",
            )
        await db.delete(acc)
        await db.commit()

    # ------------------ Guardians CRUD ------------------
    @staticmethod
    async def create_guardian(
        db: AsyncSession, user_id: uuid.UUID, guard_in: GuardianCreate
    ) -> Guardian:
        count = await db.scalar(
            select(func.count(Guardian.id)).where(Guardian.user_id == user_id)
        )
        if count >= MAX_GUARDIANS:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="CAP_EXCEEDED",
                message=f"Maximum of {MAX_GUARDIANS} guardians allowed.",
            )

        guardian = Guardian(user_id=user_id, **guard_in.model_dump())
        db.add(guardian)
        await db.commit()
        await db.refresh(guardian)
        return guardian

    @staticmethod
    async def update_guardian(
        db: AsyncSession, user_id: uuid.UUID, guard_id: uuid.UUID, update_in: GuardianUpdate
    ) -> Guardian:
        guard = await db.get(Guardian, guard_id)
        if not guard or guard.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Guardian entry not found.",
            )
        for key, value in update_in.model_dump(exclude_unset=True).items():
            setattr(guard, key, value)

        await db.commit()
        await db.refresh(guard)
        return guard

    @staticmethod
    async def delete_guardian(
        db: AsyncSession, user_id: uuid.UUID, guard_id: uuid.UUID
    ) -> None:
        guard = await db.get(Guardian, guard_id)
        if not guard or guard.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Guardian entry not found.",
            )
        await db.delete(guard)
        await db.commit()

    # ------------------ Social Links CRUD ------------------
    @staticmethod
    async def create_social_link(
        db: AsyncSession, user_id: uuid.UUID, link_in: SocialLinkCreate
    ) -> SocialLink:
        count = await db.scalar(
            select(func.count(SocialLink.id)).where(SocialLink.user_id == user_id)
        )
        if count >= MAX_SOCIAL_LINKS:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="CAP_EXCEEDED",
                message=f"Maximum of {MAX_SOCIAL_LINKS} social links allowed.",
            )

        link = SocialLink(user_id=user_id, **link_in.model_dump())
        db.add(link)
        await db.commit()
        await db.refresh(link)
        return link

    @staticmethod
    async def delete_social_link(
        db: AsyncSession, user_id: uuid.UUID, link_id: uuid.UUID
    ) -> None:
        link = await db.get(SocialLink, link_id)
        if not link or link.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESOURCE_NOT_FOUND",
                message="Social link not found.",
            )
        await db.delete(link)
        await db.commit()

    # ------------------ Confirm Upload ------------------
    @staticmethod
    async def confirm_upload(
        db: AsyncSession, user_id: uuid.UUID, confirm_in: ConfirmUploadIn
    ) -> None:
        """Verify uploaded file exists on S3 and attach to target record."""
        # Check S3 file existence
        exists = await StorageService.file_exists(confirm_in.file_url)
        if not exists:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="FILE_NOT_FOUND_ON_STORAGE",
                message="The uploaded file could not be verified on storage.",
            )

        if confirm_in.target_type == UploadTargetType.EDUCATION:
            edu = await db.get(Education, confirm_in.target_id)
            if not edu or edu.user_id != user_id:
                raise AppException(status_code=404, error_code="RESOURCE_NOT_FOUND", message="Education not found")
            edu.marksheet_url = confirm_in.file_url

        elif confirm_in.target_type == UploadTargetType.EXPERIENCE:
            exp = await db.get(Experience, confirm_in.target_id)
            if not exp or exp.user_id != user_id:
                raise AppException(status_code=404, error_code="RESOURCE_NOT_FOUND", message="Experience not found")
            exp.certificate_url = confirm_in.file_url

        elif confirm_in.target_type == UploadTargetType.ACCOMPLISHMENT:
            acc = await db.get(Accomplishment, confirm_in.target_id)
            if not acc or acc.user_id != user_id:
                raise AppException(status_code=404, error_code="RESOURCE_NOT_FOUND", message="Accomplishment not found")
            acc.document_url = confirm_in.file_url

        elif confirm_in.target_type == UploadTargetType.AVATAR:
            user = await db.get(User, user_id)
            if user:
                user.avatar_url = confirm_in.file_url

        await db.commit()
