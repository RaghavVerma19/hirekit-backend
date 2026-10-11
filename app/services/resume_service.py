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
        if update_in.last_known_updated_at and resume.updated_at:
            current_dt = resume.updated_at if resume.updated_at.tzinfo else resume.updated_at.replace(tzinfo=timezone.utc)
            known_dt = update_in.last_known_updated_at if update_in.last_known_updated_at.tzinfo else update_in.last_known_updated_at.replace(tzinfo=timezone.utc)
            if current_dt > known_dt:
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
        """Extract an editable, loss-minimising structure from an uploaded resume.

        This intentionally favours retaining source text over manufacturing generic
        content.  A user can always refine a preserved entry in Studio; they should
        never have to recover an invented job, degree, or summary.
        """
        import io
        import re
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        if len(reader.pages) > 10:
            raise ValueError("Resume PDF exceeds maximum allowed page count (10 pages).")

        full_text = "\n".join((page.extract_text() or "") for page in reader.pages)
        clean_text = re.sub(r"[\u2022\u25cf]", "•", full_text.replace("\ufffd", " "))
        raw_lines = [re.sub(r"\s+", " ", line).strip() for line in clean_text.splitlines()]
        raw_lines = [line for line in raw_lines if line and not re.fullmatch(r"page\s+\d+(?:\s+of\s+\d+)?", line, re.I)]

        email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", clean_text)
        phone_match = re.search(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,5}[\s.-]?\d{4}", clean_text)
        email = email_match.group(0) if email_match else ""
        phone = phone_match.group(0).strip() if phone_match else ""
        linkedin_match = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s|]+", clean_text, re.I)

        header_source = " ".join(raw_lines[:3])
        if email:
            header_source = header_source.split(email, 1)[0]
        header_source = re.split(r"(?i)(?:e-?mail|mobile|phone|linkedin|github|\||•)", header_source)[0]
        name = re.sub(r"[^A-Za-z .'-]", "", header_source).strip()
        name = re.sub(r"(?i)(email|mobile|phone)$", "", name).strip()
        name = name if 2 <= len(name) <= 70 else "Candidate Name"

        aliases = {
            "summary": {"summary", "professional summary", "profile", "objective", "about me", "career objective"},
            "experience": {"experience", "work experience", "professional experience", "employment", "work history", "internships"},
            "skills": {"skills", "technical skills", "skills summary", "core competencies", "technologies", "technical expertise"},
            "projects": {"projects", "academic projects", "personal projects", "technical projects", "key projects"},
            "education": {"education", "academic background", "academics", "qualifications"},
            "certificates": {"certifications", "certificates", "licenses", "certifications and achievements"},
            "languages": {"languages", "language proficiency"},
        }

        def header_key(line: str) -> Optional[str]:
            compact = re.sub(r"[^a-z\s]", "", line.lower()).strip()
            return next((key for key, names in aliases.items() if compact in names), None)

        sections: Dict[str, List[str]] = {"header": []}
        current = "header"
        for line in raw_lines:
            key = header_key(line)
            if key:
                current = key
                sections.setdefault(key, [])
            else:
                sections.setdefault(current, []).append(line)

        def clean_line(line: str) -> str:
            return re.sub(r"^[•*\-–—\s]+", "", line).strip()

        def date_in(line: str) -> str:
            found = re.search(r"(?:\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)?\s*'?\d{2,4}\s*(?:-|–|—|to)\s*(?:Present|Current|(?:[A-Za-z]+\s*)?'?\d{2,4})\b)", line, re.I)
            return found.group(0) if found else ""

        def split_entries(lines: List[str]) -> List[List[str]]:
            entries: List[List[str]] = []
            active: List[str] = []
            for line in [clean_line(item) for item in lines if clean_line(item)]:
                # A date-bearing non-bullet line commonly begins a new résumé entry.
                if active and date_in(line) and not line.startswith("•") and len(active) >= 2:
                    entries.append(active)
                    active = [line]
                else:
                    active.append(line)
            if active:
                entries.append(active)
            return entries

        skill_items: List[str] = []
        for line in sections.get("skills", []):
            value = re.sub(r"^[A-Za-z /&]+:\s*", "", clean_line(line))
            for item in re.split(r"[,|;•]", value):
                item = item.strip()
                if 1 < len(item) <= 60 and item.lower() not in {entry.lower() for entry in skill_items}:
                    skill_items.append(item)

        experiences: List[Dict[str, Any]] = []
        for index, entry in enumerate(split_entries(sections.get("experience", []))):
            heading = entry[0]
            duration = date_in(" ".join(entry[:3]))
            heading_without_date = heading.replace(duration, "").strip(" |-–—,") if duration else heading
            role, company = (heading_without_date, "")
            if " at " in heading_without_date.lower():
                role, company = re.split(r"\s+at\s+", heading_without_date, maxsplit=1, flags=re.I)
            elif " | " in heading_without_date:
                role, company = [part.strip() for part in heading_without_date.split(" | ", 1)]
            elif len(entry) > 1:
                company, role = heading_without_date, entry[1]
                entry = [entry[0]] + entry[2:]
            description = "\n".join(entry[1:]).strip()
            experiences.append({"id": f"exp-{index}", "company": company, "role": role, "duration": duration, "description": description})

        projects: List[Dict[str, Any]] = []
        for index, entry in enumerate(split_entries(sections.get("projects", []))):
            title_line = entry[0]
            tech = ""
            if "|" in title_line:
                title_line, tech = [part.strip() for part in title_line.split("|", 1)]
            projects.append({"id": f"proj-{index}", "title": title_line, "tech": tech, "description": "\n".join(entry[1:]).strip()})

        educations: List[Dict[str, Any]] = []
        for index, entry in enumerate(split_entries(sections.get("education", []))):
            year = date_in(" ".join(entry[:3]))
            institution = entry[0].replace(year, "").strip(" |-–—,") if year else entry[0]
            degree = entry[1] if len(entry) > 1 else ""
            educations.append({"id": f"edu-{index}", "institution": institution, "degree": degree, "year": year})

        certificates = [
            {"id": f"cert-{index}", "name": clean_line(line), "issuer": "", "year": date_in(line)}
            for index, line in enumerate(sections.get("certificates", [])) if clean_line(line)
        ]
        language_items = [clean_line(line) for line in sections.get("languages", []) if clean_line(line)]
        languages = [{"id": f"lang-{index}", "language": item.split("-")[0].strip(), "proficiency": item.split("-", 1)[1].strip() if "-" in item else ""} for index, item in enumerate(language_items)]

        summary = " ".join(sections.get("summary", [])).strip()
        parsed_result = {
            "title": f"{name}'s Resume" if name != "Candidate Name" else "Uploaded Resume",
            "personal": {"name": name, "email": email, "phone": phone, "location": "", "title": "", "linkedin": linkedin_match.group(0) if linkedin_match else ""},
            "summary": summary,
            "skills": skill_items,
            "experience": experiences,
            "education": educations,
            "projects": projects,
            "certificates": certificates,
            "languages": languages,
            "raw_sections": sections,
        }
        return parsed_result

    @staticmethod
    def generate_latex_from_structured_data(data: Dict[str, Any], layout: Dict[str, Any] | None = None) -> str:
        """Layout-aware deterministic LaTeX generator (single-column v1).

        Uses detected page geometry / fonts / rules / colors when `layout`
        (from layout_service.extract_layout) is provided; otherwise falls back
        to neutral 0.6in geometry WITHOUT inventing content. Section order
        follows the uploaded PDF, not a fixed template.
        """
        from app.services.layout_service import layout_to_geometry_args

        def esc(val: Any) -> str:
            replacements = {
                "\\": "\\textbackslash{}",
                "#": "\\#",
                "$": "\\$",
                "%": "\\%",
                "&": "\\&",
                "_": "\\_",
                "{": "\\{",
                "}": "\\}",
                "~": "\\textasciitilde{}",
                "^": "\\textasciicircum{}",
                "\r": "",
            }
            res = str(val or "")
            for char, rep in replacements.items():
                res = res.replace(char, rep)
            return res

        personal = data.get("personal") or {}
        name = esc(personal.get("name", "Candidate Name"))
        title = esc(personal.get("title", ""))
        email = esc(personal.get("email", ""))
        phone = esc(personal.get("phone", ""))
        loc = esc(personal.get("location", ""))
        linkedin = esc(personal.get("linkedin", ""))
        website = esc(personal.get("website", ""))

        contacts = [c for c in [email, phone, loc, linkedin, website] if c]
        contacts_line = " $\\cdot$ ".join(contacts)

        geometry_args = layout_to_geometry_args(layout)
        body_size = 10
        try:
            body_size = int(round(float((layout or {}).get("body_size", 10))))
            body_size = max(9, min(12, body_size))
        except Exception:
            body_size = 10
        has_rule = bool((layout or {}).get("has_rule"))
        colors = (layout or {}).get("colors") or {}
        needs_xcolor = bool(colors)
        rule_cmd = r"[\titlerule]" if has_rule else ""

        lines = [
            f"\\documentclass[{body_size}pt,a4paper]{{article}}",
            f"\\usepackage[{geometry_args}]{{geometry}}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage{enumitem}",
            r"\usepackage[hidelinks]{hyperref}",
            r"\usepackage{titlesec}",
            r"\usepackage{parskip}",
            *( [r"\usepackage{xcolor}"] if needs_xcolor else [] ),
            r"\setlength{\parindent}{0pt}",
            r"\setlist[itemize]{leftmargin=1.2em,nosep,topsep=2pt,partopsep=0pt}",
            f"\\titleformat{{\\section}}{{\\large\\bfseries\\uppercase}}{{}}{{0em}}{{}}{rule_cmd}",
            r"\titlespacing*{\section}{0pt}{10pt}{4pt}",
            r"\begin{document}",
            r"\begin{center}",
            f"    {{\\LARGE \\textbf{{{name}}}}}\\\\[3pt]",
        ]
        if title:
            lines.append(f"    {{\\normalsize \\textit{{{title}}}}}\\\\[2pt]")
        if contacts_line:
            lines.append(f"    {{\\small {contacts_line}}}")
        lines.append(r"\end{center}")
        lines.append(r"\vspace{-4pt}")

        if data.get("summary"):
            lines.append(r"\section*{Professional Summary}")
            lines.append(esc(data["summary"]) + r"\par")

        if data.get("skills"):
            skills_val = ", ".join(data["skills"]) if isinstance(data["skills"], list) else str(data["skills"])
            lines.append(r"\section*{Skills}")
            lines.append(r"\begin{itemize}[leftmargin=*,label={}]")
            lines.append(f"    \\item \\textbf{{Core Competencies:}} {esc(skills_val)}")
            lines.append(r"\end{itemize}")

        if data.get("experience"):
            lines.append(r"\section*{Experience}")
            for exp in data["experience"]:
                company = esc(exp.get("company", ""))
                role = esc(exp.get("role", ""))
                dur = esc(exp.get("duration", ""))
                eloc = esc(exp.get("location", ""))
                desc = str(exp.get("description", "")).strip()

                lines.append(f"\\textbf{{{company}}} \\hfill {eloc}\\\\")
                lines.append(f"\\textit{{{role}}} \\hfill {dur}")

                bullets = [b.strip().lstrip("•-*– \t") for b in desc.splitlines() if b.strip()]
                if bullets:
                    lines.append(r"\begin{itemize}")
                    for b in bullets:
                        lines.append(f"    \\item {esc(b)}")
                    lines.append(r"\end{itemize}")
                elif desc:
                    lines.append(f"\\par {esc(desc)}")
                lines.append(r"\vspace{4pt}")

        if data.get("projects"):
            lines.append(r"\section*{Projects}")
            for proj in data["projects"]:
                p_title = esc(proj.get("title", ""))
                tech = esc(proj.get("tech", ""))
                dur = esc(proj.get("duration", proj.get("year", "")))
                link = esc(proj.get("link", ""))
                desc = str(proj.get("description", "")).strip()

                header_parts = [f"\\textbf{{{p_title}}}"]
                if tech:
                    header_parts.append(f"\\textit{{{tech}}}")
                if link:
                    header_parts.append(f"\\href{{{link}}}{{Link}}")
                lines.append(" $|$ ".join(header_parts) + (f" \\hfill {dur}\\\\" if dur else "\\\\"))

                bullets = [b.strip().lstrip("•-*– \t") for b in desc.splitlines() if b.strip()]
                if bullets:
                    lines.append(r"\begin{itemize}")
                    for b in bullets:
                        lines.append(f"    \\item {esc(b)}")
                    lines.append(r"\end{itemize}")
                elif desc:
                    lines.append(f"\\par {esc(desc)}")
                lines.append(r"\vspace{4pt}")

        if data.get("education"):
            lines.append(r"\section*{Education}")
            for edu in data["education"]:
                inst = esc(edu.get("institution", edu.get("school", "")))
                degree = esc(edu.get("degree", ""))
                year = esc(edu.get("year", ""))
                grade = esc(edu.get("grade", edu.get("cgpa", "")))

                lines.append(f"\\textbf{{{inst}}} \\hfill {year}\\\\")
                deg_line = f"\\textit{{{degree}}}"
                if grade:
                    deg_line += f" --- Grade/GPA: {grade}"
                lines.append(f"{deg_line}\\par")
                lines.append(r"\vspace{3pt}")

        if data.get("certificates"):
            lines.append(r"\section*{Certifications}")
            lines.append(r"\begin{itemize}")
            for cert in data["certificates"]:
                c_name = esc(cert.get("name", ""))
                issuer = esc(cert.get("issuer", ""))
                year = esc(cert.get("year", ""))
                entry_str = f"\\textbf{{{c_name}}}"
                if issuer:
                    entry_str += f", {issuer}"
                if year:
                    entry_str += f" ({year})"
                lines.append(f"    \\item {entry_str}")
            lines.append(r"\end{itemize}")

        if data.get("languages"):
            lines.append(r"\section*{Languages}")
            lang_items = []
            for lang in data["languages"]:
                l_name = esc(lang.get("language", ""))
                prof = esc(lang.get("proficiency", ""))
                lang_items.append(f"{l_name} ({prof})" if prof else l_name)
            lines.append(", ".join(lang_items) + r"\par")

        lines.append(r"\end{document}")
        return "\n".join(lines)

    @staticmethod
    async def transcribe_pdf_to_latex_with_gemini(
        pdf_bytes: Optional[bytes] = None,
        pdf_text: Optional[str] = None,
        fallback_content: Optional[Dict[str, Any]] = None,
        layout: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Gemini 2.5 Flash vision refine: observe PDF + deterministic draft + layout, return exact single-column copy."""
        import asyncio
        from app.core.config import settings

        fallback = fallback_content or {}
        if not settings.GEMINI_API_KEY:
            return ResumeService.generate_latex_from_structured_data(fallback, layout=layout)

        prompt = f"""
You are an expert LaTeX developer. Observe the attached single-column resume PDF and refine the deterministic draft into an EXACT visual copy.

Scope: SINGLE COLUMN ONLY (v1). Do NOT use multicol/minipage/sidebar/tabularx grids.

1. Geometry/fidelity (use detected layout, do not invent):
   Detected layout JSON: {(str(layout)[:3000] if layout else "none — use 0.6in margins, 10pt")}
   - Keep single-column article class. Set \\geometry from detected margins.
   - Match headings, horizontal rules (\\titlerule only if original has a rule), spacing (\\vspace/\\titlespacing), font sizes, bold/italic, \\hfill alignments, colors via xcolor, links via \\href.
   - Standard packages only: geometry, hyperref, enumitem, titlesec, xcolor, parskip. No custom macros (no \\ResumePersonal etc.).
2. Verbatim: copy every name/title/company/date/bullet/URL VERBATIM. No rephrase/summarize/invent.
3. Valid LaTeX: escape % & $ _ # ~ ^, balanced braces/environments, complete \\documentclass..\\end{{document}}.
4. Output ONLY raw LaTeX, no fences/explanations.

Deterministic draft to refine:
\"\"\"
{ResumeService.generate_latex_from_structured_data(fallback, layout=layout)[:8000]}
\"\"\"

Reference extracted text:
\"\"\"
{(pdf_text or "")[:12000]}
\"\"\"
"""
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            loop = asyncio.get_running_loop()

            contents = []
            if pdf_bytes:
                contents.append(types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"))
            contents.append(prompt)

            resp = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=contents,
                        config=types.GenerateContentConfig(
                            temperature=0.1,
                        ),
                    ),
                ),
                timeout=45.0,
            )

            latex_text = resp.text.strip()
            if latex_text.startswith("```latex"):
                latex_text = latex_text[len("```latex"):].strip()
            elif latex_text.startswith("```"):
                latex_text = latex_text[3:].strip()
            if latex_text.endswith("```"):
                latex_text = latex_text[:-3].strip()

            if "\\begin{document}" in latex_text and "\\end{document}" in latex_text:
                return latex_text
            logger.warning("gemini_latex_missing_document_boundary_fallback")
            return ResumeService.generate_latex_from_structured_data(fallback, layout=layout)
        except Exception as e:
            logger.warning("gemini_pdf_to_latex_failed_using_fallback", error=str(e))
            return ResumeService.generate_latex_from_structured_data(fallback, layout=layout)

    @staticmethod
    async def process_pdf_transcription_background(
        resume_id: uuid.UUID,
        raw_bytes: Optional[bytes] = None,
        raw_text: str = "",
        fallback_content: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Background task to run LLM transcription without blocking initial upload."""
        from app.db.session import AsyncSessionLocal
        try:
            logger.info("pdf_latex_transcription_started", resume_id=str(resume_id))
            layout: Dict[str, Any] = {}
            if raw_bytes:
                try:
                    from app.services.layout_service import extract_layout
                    layout = extract_layout(raw_bytes)
                except Exception as le:
                    logger.warning("layout_extract_failed", error=str(le))
                    layout = {}
            generated_latex = await ResumeService.transcribe_pdf_to_latex_with_gemini(
                pdf_bytes=raw_bytes,
                pdf_text=raw_text,
                fallback_content=fallback_content or {},
                layout=layout,
            )

            # Extract Candidate Name from generated LaTeX to set the exact resume title
            import re
            name_match = (
                re.search(r"\\textbf\{([A-Za-z\s\.\-]{2,40})\}", generated_latex)
                or re.search(r"\\LARGE\s*\{?([A-Za-z\s\.\-]{2,40})\}?", generated_latex)
                or re.search(r"\\Huge\s*\{?([A-Za-z\s\.\-]{2,40})\}?", generated_latex)
            )
            candidate_name = name_match.group(1).strip() if name_match else None
            if not candidate_name and fallback_content:
                candidate_name = fallback_content.get("personal", {}).get("name")
            doc_title = f"{candidate_name}'s Resume" if candidate_name and candidate_name != "Candidate Name" else None

            async with AsyncSessionLocal() as session:
                resume = await session.get(Resume, resume_id)
                if not resume or resume.is_deleted:
                    return

                updated_content = dict(resume.content_json or {})
                updated_content["latex_source"] = generated_latex
                updated_content["layout_json"] = layout
                updated_content["llm_processing"] = False
                updated_content["llm_processed_at"] = datetime.now(timezone.utc).isoformat()
                new_hash = ATSService.compute_content_hash(updated_content)

                values_to_update = {
                    "content_json": updated_content,
                    "content_hash": new_hash,
                }
                if doc_title and ("Uploaded Resume" in resume.title or "Resume" in resume.title):
                    values_to_update["title"] = doc_title[:150]

                await session.execute(
                    update(Resume)
                    .where(Resume.id == resume_id)
                    .values(**values_to_update)
                )
                await session.commit()
                logger.info("pdf_latex_transcription_completed", resume_id=str(resume_id))
        except Exception as exc:
            logger.error("pdf_latex_transcription_failed", resume_id=str(resume_id), error=str(exc))
            # On failure, remove processing lock so user can still edit
            try:
                async with AsyncSessionLocal() as session:
                    resume = await session.get(Resume, resume_id)
                    if resume:
                        updated_content = dict(resume.content_json or {})
                        updated_content["llm_processing"] = False
                        if not updated_content.get("latex_source"):
                            updated_content["latex_source"] = ResumeService.generate_latex_from_structured_data(fallback_content or {})
                        await session.execute(
                            update(Resume)
                            .where(Resume.id == resume_id)
                            .values(
                                content_json=updated_content,
                                content_hash=ATSService.compute_content_hash(updated_content),
                            )
                        )
                        await session.commit()
            except Exception:
                pass
