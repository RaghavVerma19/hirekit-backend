import asyncio
import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pypdf
import structlog
from app.core.config import settings

logger = structlog.get_logger()

ROLE_KEYWORDS: Dict[str, List[str]] = {
    "Software Engineering": [
        "Data Structures",
        "Algorithms",
        "Full-Stack",
        "System Design",
        "RESTful APIs",
        "PostgreSQL",
        "SQL",
        "Microservices",
        "CI/CD",
        "Git",
        "Docker",
        "Python",
        "Java",
        "C++",
        "TypeScript",
        "Node.js",
    ],
    "Frontend / Web Development": [
        "React",
        "Next.js",
        "TypeScript",
        "JavaScript",
        "Tailwind CSS",
        "HTML5",
        "CSS3",
        "Redux",
        "Zustand",
        "Responsive Design",
        "Web Performance",
        "REST APIs",
        "UI/UX",
        "Git",
    ],
    "Data Science & AI": [
        "Python",
        "SQL",
        "Machine Learning",
        "Deep Learning",
        "Pandas",
        "NumPy",
        "Scikit-Learn",
        "TensorFlow",
        "PyTorch",
        "Data Analysis",
        "Data Visualization",
        "Tableau",
        "PowerBI",
        "Statistics",
    ],
}


class LinkedInAuditService:
    @staticmethod
    def parse_linkedin_pdf(file_bytes: bytes) -> Dict[str, Any]:
        """Extract structured sections from an official LinkedIn 'Save to PDF' document."""
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        full_text = ""
        for page in reader.pages:
            extracted = page.extract_text() or ""
            full_text += extracted + "\n"

        lines = [line.strip() for line in full_text.split("\n") if line.strip()]

        # Section extractors
        name = ""
        headline = ""
        summary = ""
        skills: List[str] = []
        certifications: List[str] = []
        experiences: List[Dict[str, Any]] = []
        educations: List[Dict[str, Any]] = []
        contact: Dict[str, str] = {}

        # LinkedIn PDF header typically has Name on line 0/1, Headline right after
        # But let's identify sections using standard LinkedIn PDF headings:
        # "Contact", "Top Skills", "Certifications", "Summary", "Experience", "Education", "Languages"
        current_section = "header"
        header_lines: List[str] = []
        summary_lines: List[str] = []
        skills_lines: List[str] = []
        cert_lines: List[str] = []
        exp_lines: List[str] = []
        edu_lines: List[str] = []

        section_headers = {
            "contact": "contact",
            "top skills": "skills",
            "skills": "skills",
            "certifications": "certifications",
            "licenses & certifications": "certifications",
            "summary": "summary",
            "experience": "experience",
            "education": "education",
            "languages": "languages",
            "honors-awards": "honors",
        }

        for line in lines:
            lower = line.lower().strip()
            # Check if line matches a known section header
            matched_sec = section_headers.get(lower)
            if matched_sec:
                current_section = matched_sec
                continue

            # Route lines to sections
            if current_section == "header":
                header_lines.append(line)
            elif current_section == "contact":
                if "linkedin.com" in lower:
                    contact["linkedin"] = line.split("(")[0].strip()
                elif "@" in lower:
                    contact["email"] = line.split("(")[0].strip()
            elif current_section == "skills":
                # Filter out metadata lines like "(Programming Language)", "Page 1 of 2", etc.
                if not re.search(r"page \d+ of \d+", lower) and len(line) < 50:
                    clean_skill = re.sub(r"\(.*?\)", "", line).strip()
                    if clean_skill and clean_skill not in skills:
                        skills.append(clean_skill)
            elif current_section == "certifications":
                if not re.search(r"page \d+ of \d+", lower) and len(line) < 80:
                    cert_lines.append(line)
            elif current_section == "summary":
                if not re.search(r"page \d+ of \d+", lower):
                    summary_lines.append(line)
            elif current_section == "experience":
                if not re.search(r"page \d+ of \d+", lower):
                    exp_lines.append(line)
            elif current_section == "education":
                if not re.search(r"page \d+ of \d+", lower):
                    edu_lines.append(line)

        # Parse header: First line is usually candidate name, next lines are headline/location
        if header_lines:
            name = header_lines[0]
            if len(header_lines) > 1:
                headline = " ".join(header_lines[1:3])

        summary = "\n".join(summary_lines).strip()

        # Parse experiences simply by looking for job blocks or lines
        if exp_lines:
            # Group into basic text chunks
            experiences.append({
                "raw_text": "\n".join(exp_lines[:20]).strip(),
                "count": max(1, len(exp_lines) // 4),
            })

        # Parse educations
        if edu_lines:
            educations.append({
                "raw_text": "\n".join(edu_lines[:15]).strip(),
                "count": max(1, len(edu_lines) // 3),
            })

        certifications = cert_lines[:10]

        return {
            "name": name,
            "headline": headline,
            "summary": summary,
            "skills": skills,
            "certifications": certifications,
            "experiences": experiences,
            "educations": educations,
            "contact": contact,
            "total_pages": len(reader.pages),
        }

    @staticmethod
    def audit_profile(data: Dict[str, Any], target_role: str = "Software Engineering") -> Dict[str, Any]:
        """Perform comprehensive ATS & recruiter search optimization audit on parsed LinkedIn data."""
        headline = (data.get("headline") or "").strip()
        summary = (data.get("summary") or "").strip()
        skills = data.get("skills") or []
        experiences = data.get("experiences") or []
        certifications = data.get("certifications") or []
        educations = data.get("educations") or []

        role_kw = ROLE_KEYWORDS.get(target_role, ROLE_KEYWORDS["Software Engineering"])
        combined_text = f"{headline} {summary} {' '.join(skills)}".lower()

        # 1. Headline Scoring (0 - 100)
        headline_score = 0
        h_lower = headline.lower()
        has_title = any(t in h_lower for t in ["engineer", "developer", "student", "specialist", "architect", "lead"])
        has_divider = "|" in headline or "•" in headline or "-" in headline
        has_skills_in_h = any(kw.lower() in h_lower for kw in role_kw)

        if len(headline) >= 30:
            headline_score += 30
        elif len(headline) >= 10:
            headline_score += 15

        if has_title:
            headline_score += 30
        if has_skills_in_h:
            headline_score += 25
        if has_divider:
            headline_score += 15
        headline_score = min(100, headline_score)

        # 2. Summary Scoring (0 - 100)
        summary_score = 0
        word_count = len(summary.split()) if summary else 0
        if word_count >= 100:
            summary_score += 35
        elif word_count >= 40:
            summary_score += 20
        elif word_count >= 10:
            summary_score += 10

        has_metrics = bool(re.search(r"\d+%?|\$|users|scale|optimized|reduced", summary, re.IGNORECASE))
        if has_metrics:
            summary_score += 25

        has_contact = any(c in summary.lower() for c in ["connect", "email", "reach", "contact", "linkedin"])
        if has_contact:
            summary_score += 20

        has_formatting = "•" in summary or "-" in summary or ":" in summary
        if has_formatting:
            summary_score += 20
        summary_score = min(100, summary_score)

        # 3. Skills Scoring (0 - 100)
        # LinkedIn allows up to 50 skills. Ideal is 10-25 verified skills.
        skills_count = len(skills)
        if skills_count >= 15:
            skills_score = 100
        elif skills_count >= 8:
            skills_score = 75
        elif skills_count >= 4:
            skills_score = 50
        elif skills_count >= 1:
            skills_score = 25
        else:
            skills_score = 0

        # 4. Keyword Match
        matched_keywords = [kw for kw in role_kw if kw.lower() in combined_text]
        missing_keywords = [kw for kw in role_kw if kw.lower() not in combined_text]
        keyword_match_rate = round((len(matched_keywords) / max(1, len(role_kw))) * 100)

        # 5. Experience & Certifications Scoring (0 - 100)
        exp_score = 50 if len(experiences) > 0 else 0
        if len(certifications) > 0:
            exp_score += 30
        if len(educations) > 0:
            exp_score += 20
        exp_score = min(100, exp_score)

        # Overall Composite Score
        overall_score = round(
            headline_score * 0.25 +
            summary_score * 0.25 +
            skills_score * 0.20 +
            keyword_match_rate * 0.20 +
            exp_score * 0.10
        )

        # Generate Strengths & Improvements
        strengths: List[str] = []
        improvements: List[Dict[str, str]] = []

        if has_title and len(headline) >= 25:
            strengths.append(f"Clear role designation in headline: \"{headline[:60]}...\"")
        else:
            improvements.append({
                "area": "Headline",
                "text": "Add a specific target role title (e.g. 'Software Engineer' or 'Full Stack Developer') with key tech tags.",
                "priority": "HIGH",
            })

        if skills_count >= 8:
            strengths.append(f"Strong skills portfolio with {skills_count} LinkedIn skills detected.")
        else:
            improvements.append({
                "area": "Skills",
                "text": f"Only {skills_count} skill(s) detected. Add at least 10-15 industry-relevant skills on LinkedIn to increase search visibility.",
                "priority": "HIGH",
            })

        if word_count >= 60 and has_metrics:
            strengths.append("About section is well-articulated with measurable impact or project highlights.")
        else:
            improvements.append({
                "area": "Summary",
                "text": "Expand your About summary to 3-4 paragraphs highlighting key projects, technical stack, and your contact email.",
                "priority": "MEDIUM",
            })

        if len(certifications) > 0:
            strengths.append(f"{len(certifications)} official certification(s) verified on LinkedIn profile.")
        else:
            improvements.append({
                "area": "Certifications",
                "text": "Add relevant industry certifications (AWS, HackerRank, Coursera, LeetCode) to establish credential authority.",
                "priority": "LOW",
            })

        return {
            "overall_score": overall_score,
            "headline_score": headline_score,
            "summary_score": summary_score,
            "skills_score": skills_score,
            "keyword_score": keyword_match_rate,
            "experience_score": exp_score,
            "target_role": target_role,
            "skills_count": skills_count,
            "word_count": word_count,
            "detected_skills": skills,
            "matched_keywords": matched_keywords,
            "missing_keywords": missing_keywords,
            "strengths": strengths,
            "improvements": improvements,
            "raw_headline": headline,
            "raw_summary": summary,
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    async def ai_audit_profile(
        data: Dict[str, Any], target_role: str = "Software Engineering"
    ) -> Dict[str, Any]:
        """Perform deep, structured tech recruiter evaluation using Google Gemini AI."""
        fallback_audit = LinkedInAuditService.audit_profile(data, target_role)

        if not settings.GEMINI_API_KEY:
            return fallback_audit

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.GEMINI_API_KEY)

            candidate_payload = {
                "name": data.get("name", "Candidate"),
                "current_headline": data.get("headline", ""),
                "summary_about": data.get("summary", ""),
                "skills": data.get("skills", []),
                "experience_excerpts": [
                    e.get("raw_text", "") for e in data.get("experiences", [])
                ][:4],
                "education_excerpts": [
                    e.get("raw_text", "") for e in data.get("educations", [])
                ][:2],
                "certifications": data.get("certifications", []),
                "target_placement_role": target_role,
            }

            prompt = f"""
You are an Elite Principal Technical Recruiter & Senior Director of Campus Placements at top-tier tech companies (FAANG and Tier-1 startups).
You assess university graduates and software engineering candidates with extreme rigor and surgical insight.
Evaluate this candidate's official LinkedIn profile data against real recruitment algorithms, hiring manager first-impressions, STAR methodology, and ATS discoverability for the target role: "{target_role}".

Candidate Profile Data:
{json.dumps(candidate_payload, indent=2)}

Produce a deeply detailed, highly actionable executive audit report.
Your response MUST be a valid, parseable JSON object matching this schema:
{{
  "overall_score": <integer between 30 and 96>,
  "readiness_verdict": "<e.g. Tier-1 Placement Ready | Highly Competitive Candidate | Needs Strategic Refinement | Early Developing Profile>",
  "executive_summary": "<A powerful, 2-3 sentence executive recruiter verdict on the candidate's strengths, weaknesses, and market positioning>",
  
  "pillars": {{
    "headline": {{
      "score": <integer 0-100>,
      "status": "<e.g. Highly Optimized | Generic Title | Missing Target Domain>",
      "critique": "<Specific critique of the headline: what recruiters think, search ranking impact, presence of buzzwords>",
      "missing_elements": ["<item 1>", "<item 2>"]
    }},
    "summary": {{
      "score": <integer 0-100>,
      "status": "<e.g. Compelling Storytelling | Adequate | Lacks Quantifiable Metrics | Missing>",
      "critique": "<Detailed recruiter critique on narrative hook, technical depth, metrics, and call-to-action>",
      "word_count_analysis": "<Brief comment on length, structure, readability>"
    }},
    "skills": {{
      "score": <integer 0-100>,
      "status": "<e.g. Strong Tech Stack | Missing Key Frameworks | Thin>",
      "critique": "<Specific analysis of core languages vs frameworks vs tools for {target_role}>",
      "verified_count": <integer count of skills detected>,
      "matched_keywords": ["<keyword 1>", "<keyword 2>"],
      "critical_missing_skills": ["<missing high-value skill 1>", "<missing high-value skill 2>"]
    }},
    "experience_projects": {{
      "score": <integer 0-100>,
      "status": "<e.g. High Impact | Moderate | Duty-Focused>",
      "critique": "<Critique of experience/projects: are bullets using STAR methodology? Are quantifiable metrics (latencies, users, %, scale) present?>",
      "weak_bullets_identified": ["<weak aspect or point 1>", "<weak aspect or point 2>"]
    }}
  }},

  "action_checklist": [
    {{
      "priority": "<CRITICAL | HIGH | MEDIUM | LOW>",
      "category": "<Headline | Summary | Skills | Projects | Certifications>",
      "action": "<Exact, specific action step the candidate must take>",
      "expected_impact": "<How this directly improves recruiter search ranking or interview callback rate>"
    }}
  ],

  "ai_recommendations": {{
    "optimized_headlines": [
      {{
        "style": "Industry Standard (Clean & Searchable)",
        "headline": "<Punchy headline tailored to candidate's skills and {target_role}, under 220 chars>"
      }},
      {{
        "style": "Project & Metric Driven",
        "headline": "<Headline emphasizing impact, projects, or metrics, under 220 chars>"
      }},
      {{
        "style": "Campus Placement Specialist",
        "headline": "<Headline tailored for university placement drives and campus recruiters, under 220 chars>"
      }}
    ],
    "optimized_about_section": "<A complete, beautifully formatted LinkedIn About section written specifically for this candidate with custom intro, technical competencies list, project highlights, and contact CTA, using modern professional formatting with bullets>"
  }},

  "interviewer_psychology": {{
    "first_impression_verdict": "<What a technical hiring manager concludes within the first 6 seconds of scanning this profile>",
    "perceived_seniority_level": "<Intern / Junior Engineer | Mid-Level Contributor | Senior / Lead Potential>",
    "culture_fit_signals": "<Work style and collaboration traits signaled by profile language, projects, and tone>",
    "red_flags_for_recruiters": [
      "<Potential red flag or ambiguity that causes recruiters to hesitate or skip>",
      "<Second red flag or area where proof/metrics are critically missing>"
    ],
    "trust_signals": [
      "<High-credibility indicator present in this profile (e.g. live deployments, specific tech versions, measurable results)>",
      "<Second credibility booster>"
    ]
  }},

  "ats_simulation": {{
    "keyword_density_score": <integer 0-100>,
    "boolean_search_matchability": "<High | Moderate | Low — how easily this profile matches recruiter Boolean queries like '(Python OR Go) AND AWS AND Docker'>",
    "recruiter_search_rank_estimate": "<Top 5% | Top 15% | Top 35% | Below Average in Campus Batch>",
    "visibility_booster_tips": [
      "<Concrete tactic to increase LinkedIn search impression appearances>",
      "<Profile keyword positioning improvement>"
    ]
  }}
}}
"""

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            )

            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=config,
                ),
            )

            ai_result = json.loads(resp.text)

            ai_result["is_ai_evaluated"] = True
            ai_result["model_used"] = "Google Gemini 2.5 Flash"
            ai_result["target_role"] = target_role
            ai_result["raw_headline"] = data.get("headline", "")
            ai_result["raw_summary"] = data.get("summary", "")
            ai_result["detected_skills"] = data.get("skills", [])
            ai_result["skills_count"] = len(data.get("skills", []))
            ai_result["audited_at"] = datetime.now(timezone.utc).isoformat()

            pillars = ai_result.get("pillars", {})
            ai_result["headline_score"] = pillars.get("headline", {}).get(
                "score", fallback_audit["headline_score"]
            )
            ai_result["summary_score"] = pillars.get("summary", {}).get(
                "score", fallback_audit["summary_score"]
            )
            ai_result["skills_score"] = pillars.get("skills", {}).get(
                "score", fallback_audit["skills_score"]
            )
            ai_result["experience_score"] = pillars.get(
                "experience_projects", {}
            ).get("score", fallback_audit["experience_score"])

            skills_pillar = pillars.get("skills", {})
            ai_result["matched_keywords"] = skills_pillar.get(
                "matched_keywords", fallback_audit["matched_keywords"]
            )
            ai_result["missing_keywords"] = skills_pillar.get(
                "critical_missing_skills", fallback_audit["missing_keywords"]
            )

            logger.info(
                "gemini_linkedin_audit_success",
                overall_score=ai_result.get("overall_score"),
            )
            return ai_result

        except Exception as e:
            logger.error(
                "gemini_linkedin_audit_failed_fallback_to_rules",
                error=str(e),
                exc_info=True,
            )
            return fallback_audit
