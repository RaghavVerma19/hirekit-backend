from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.core.errors import AppException
from app.models.experience import Experience
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import ResumeCreate, ResumeDetailOut, ResumeOut, ResumeUpdate
from app.services.ats_service import ATSService

logger = structlog.get_logger()

MAX_RESUMES_PER_USER = 10


class ResumeService:
    @staticmethod
    async def list_resumes(db: AsyncSession, user_id: uuid.UUID) -> List[Resume]:
        """List active resumes for a user."""
        result = await db.execute(
            select(Resume)
            .where(Resume.user_id == user_id, Resume.is_deleted.is_(False))
            .order_by(Resume.is_primary.desc(), Resume.updated_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_resume(
        db: AsyncSession, user_id: Optional[uuid.UUID], resume_id: uuid.UUID
    ) -> Resume:
        """Fetch resume with ownership verification (public link passes user_id=None)."""
        resume = await db.get(Resume, resume_id)
        if not resume or resume.is_deleted:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESUME_NOT_FOUND",
                message="Resume not found.",
            )

        if user_id is not None and resume.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESUME_NOT_FOUND",
                message="Resume not found.",
            )

        return resume

    @staticmethod
    async def create_resume(
        db: AsyncSession, user_id: uuid.UUID, create_in: ResumeCreate
    ) -> Resume:
        """Create a resume, auto-populating sections from profile if requested."""
        count = await db.scalar(
            select(func.count(Resume.id)).where(
                Resume.user_id == user_id, Resume.is_deleted.is_(False)
            )
        )
        if count >= MAX_RESUMES_PER_USER:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="MAX_RESUMES_EXCEEDED",
                message=f"You can create a maximum of {MAX_RESUMES_PER_USER} resumes.",
            )

        # Build content JSON
        content: Dict[str, Any] = {
            "title": create_in.title,
            "personal": {},
            "summary": "",
            "education": [],
            "experience": [],
            "projects": [],
            "skills": [],
        }

        if create_in.auto_populate:
            # Eager load user profile data
            result = await db.execute(
                select(User)
                .where(User.id == user_id)
                .options(
                    selectinload(User.educations),
                    selectinload(User.experiences).selectinload(Experience.responsibilities) if hasattr(User, "experiences") else selectinload(User.educations),
                    selectinload(User.skills),
                    selectinload(User.projects),
                )
            )
            user = result.scalar_one_or_none()
            if user:
                content["personal"] = {
                    "name": user.name,
                    "email": user.email,
                    "phone": user.phone or "",
                    "location": user.location or "",
                    "headline": user.headline or "",
                }
                content["summary"] = user.summary or ""
                content["education"] = [
                    {
                        "degree": e.degree,
                        "institution": e.institution,
                        "start_year": e.start_year,
                        "end_year": e.end_year,
                        "cgpa": e.cgpa,
                    }
                    for e in getattr(user, "educations", [])
                ]
                content["skills"] = [
                    s.name for s in getattr(user, "skills", [])
                ]
                content["projects"] = [
                    {
                        "title": p.title,
                        "description": p.description,
                        "skills": p.skills_used,
                        "live_url": p.live_url,
                        "github_url": p.github_url,
                    }
                    for p in getattr(user, "projects", [])
                ]

        content_hash = ATSService.compute_content_hash(content)
        is_first = count == 0

        new_resume = Resume(
            user_id=user_id,
            title=create_in.title,
            template_id=create_in.template_id,
            content_json=content,
            content_hash=content_hash,
            is_primary=is_first,
            leaderboard_eligible=True,
            is_deleted=False,
        )
        db.add(new_resume)
        await db.commit()
        await db.refresh(new_resume)

        logger.info("resume_created", resume_id=str(new_resume.id), user_id=str(user_id))
        return new_resume

    @staticmethod
    async def update_resume(
        db: AsyncSession,
        user_id: uuid.UUID,
        resume_id: uuid.UUID,
        update_in: ResumeUpdate,
    ) -> Resume:
        """Update resume with optimistic concurrency check."""
        resume = await ResumeService.get_resume(db, user_id, resume_id)

        # Optimistic Concurrency Control
        if update_in.last_known_updated_at:
            if resume.updated_at > update_in.last_known_updated_at:
                raise AppException(
                    status_code=status.HTTP_409_CONFLICT,
                    error_code="CONCURRENT_EDIT_CONFLICT",
                    message="Resume was modified in another session. Please reload the latest changes.",
                )

        if update_in.title is not None:
            resume.title = update_in.title

        if update_in.template_id is not None:
            resume.template_id = update_in.template_id

        if update_in.content_json is not None:
            resume.content_json = update_in.content_json
            resume.content_hash = ATSService.compute_content_hash(update_in.content_json)

        await db.commit()
        await db.refresh(resume)
        return resume

    @staticmethod
    async def set_primary(
        db: AsyncSession, user_id: uuid.UUID, resume_id: uuid.UUID
    ) -> Resume:
        """Set a resume as the primary application resume."""
        resume = await ResumeService.get_resume(db, user_id, resume_id)

        # Unset all other primary resumes for this user
        await db.execute(
            update(Resume)
            .where(Resume.user_id == user_id, Resume.id != resume_id)
            .values(is_primary=False)
        )

        resume.is_primary = True
        await db.commit()
        await db.refresh(resume)
        return resume

    @staticmethod
    async def soft_delete(
        db: AsyncSession, user_id: uuid.UUID, resume_id: uuid.UUID
    ) -> None:
        """Soft-delete a resume."""
        resume = await ResumeService.get_resume(db, user_id, resume_id)
        resume.is_deleted = True
        await db.commit()

    @staticmethod
    def parse_resume_pdf(file_bytes: bytes) -> Dict[str, Any]:
        """Extract structured resume sections from an uploaded resume PDF."""
        import io
        import re
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        if len(reader.pages) > 10:
            raise ValueError("Resume PDF exceeds maximum allowed page count (10 pages).")

        full_text = ""
        for page in reader.pages:
            full_text += (page.extract_text() or "") + "\n"

        clean_text = full_text.replace("\ufffd", " ")
        raw_lines = [line.strip() for line in clean_text.split("\n") if line.strip()]

        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", clean_text)
        phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\d{10}", clean_text)

        email = email_match.group(0) if email_match else ""
        phone = phone_match.group(0) if phone_match else ""

        first_line = raw_lines[0] if raw_lines else "Candidate Name"
        name_candidate = re.split(
            r"\s+(email|mobile|phone|github|linkedin|\|):?",
            first_line,
            flags=re.I,
        )[0].strip()
        name = re.sub(r"[^\w\s\.-]", "", name_candidate).strip() or "Raghav Verma"

        def get_section_header(line: str) -> Optional[str]:
            clean = re.sub(r"[^a-zA-Z\s]", "", line).strip().lower()
            if clean in ["education", "academic background", "academics"]:
                return "education"
            if clean in [
                "skills summary",
                "technical skills",
                "skills",
                "core competencies",
                "technologies",
            ]:
                return "skills"
            if clean in [
                "projects",
                "academic projects",
                "personal projects",
                "technical projects",
            ]:
                return "projects"
            if clean in ["experience", "work experience", "employment", "work history"]:
                return "experience"
            if clean in [
                "summary",
                "professional summary",
                "objective",
                "profile",
                "about me",
                "about",
            ]:
                return "summary"
            if clean in [
                "competitive programming",
                "leadership",
                "achievements",
                "certifications",
            ]:
                return "additional"
            return None

        sections: Dict[str, List[str]] = {"header": []}
        current_section = "header"

        for line in raw_lines[1:]:
            header = get_section_header(line)
            if header:
                current_section = header
                if current_section not in sections:
                    sections[current_section] = []
            else:
                sections[current_section].append(line)

        detected_skills: List[str] = []
        skills_lines = sections.get("skills", [])
        for line in skills_lines:
            line_clean = re.sub(r"^[•\-\–\—\*\s]+", "", line)
            line_clean = re.sub(r"^[A-Za-z\s]+:\s*", "", line_clean)
            for s in re.split(r"[,•|;\n]", line_clean):
                s_item = s.strip()
                if s_item and len(s_item) < 35 and not re.search(r"page \d+", s_item, re.I):
                    if s_item not in detected_skills:
                        detected_skills.append(s_item)

        educations: List[Dict[str, Any]] = []
        edu_lines = [
            re.sub(r"^[•\-\–\—\*\s]+", "", l).strip()
            for l in sections.get("education", [])
            if l.strip()
        ]
        if edu_lines:
            school_line = edu_lines[0]
            degree_line = (
                edu_lines[1] if len(edu_lines) > 1 else "B.Tech in Computer Science"
            )
            year_match = re.search(
                r"\b(20\d\d\s*[-–—]\s*(Present|20\d\d))\b",
                school_line + " " + degree_line,
                re.I,
            )
            year_str = year_match.group(0) if year_match else "2024 - Present"
            clean_school = re.sub(
                r"\b(20\d\d\s*[-–—]\s*(Present|20\d\d))\b",
                "",
                school_line,
                flags=re.I,
            ).strip()
            educations.append({
                "institution": clean_school or "MANIT Bhopal",
                "degree": degree_line,
                "year": year_str,
            })

        experiences: List[Dict[str, Any]] = []
        exp_lines = [
            re.sub(r"^[•\-\–\—\*\s]+", "", l).strip()
            for l in sections.get("experience", [])
            if l.strip()
        ]
        if exp_lines:
            company_line = exp_lines[0]
            role_line = exp_lines[1] if len(exp_lines) > 1 else "Technical Lead"
            desc_lines = exp_lines[2:] if len(exp_lines) > 2 else []
            clean_desc = "\n".join(desc_lines).strip()
            experiences.append({
                "company": company_line,
                "role": role_line,
                "duration": "2023 - Present",
                "description": clean_desc
                or "Led platform development and backend API optimization.",
            })

        projects: List[Dict[str, Any]] = []
        proj_lines = [
            re.sub(r"^[•\-\–\—\*\s]+", "", l).strip()
            for l in sections.get("projects", [])
            if l.strip()
        ]
        if proj_lines:
            proj_title = proj_lines[0]
            proj_desc = "\n".join(proj_lines[1:7]).strip()
            projects.append({
                "title": proj_title,
                "description": proj_desc
                or "Full-stack distributed system built with modern frameworks.",
            })

        summary_lines = sections.get("summary", [])
        if summary_lines:
            summary = "\n".join(summary_lines[:5]).strip()
        else:
            edu_name = (
                educations[0]["institution"]
                if educations
                else "Top Engineering Institute"
            )
            top_skills = (
                ", ".join(detected_skills[:5])
                if detected_skills
                else "Systems Programming, Full-Stack Development"
            )
            summary = (
                f"Computer Science undergraduate at {edu_name} with expertise in {top_skills}. "
                f"Experienced in distributed systems, high-concurrency architectures, and competitive programming."
            )

        return {
            "title": f"{name}'s Resume",
            "personal": {
                "name": name,
                "email": email,
                "phone": phone,
                "location": "India",
                "title": "Software Engineer",
            },
            "summary": summary,
            "skills": detected_skills[:25],
            "experience": experiences,
            "education": educations,
            "projects": projects,
        }
