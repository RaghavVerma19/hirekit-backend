import asyncio
import hashlib
import json
from typing import Any, Dict, Optional
import uuid
from fastapi import status
import redis.asyncio as aioredis
import structlog

from app.core.config import settings
from app.core.errors import AppException
from app.schemas.resume import ATSImprovement, ATSScoreResult

logger = structlog.get_logger()


class ATSService:
    @staticmethod
    def compute_content_hash(content: Dict[str, Any]) -> str:
        """Compute SHA-256 fingerprint hash of resume JSON data."""
        serialized = json.dumps(content, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    async def score_resume(
        resume_id: uuid.UUID,
        content: Dict[str, Any],
        redis: aioredis.Redis,
    ) -> ATSScoreResult:
        """Score resume using Gemini AI with content-hash caching and dedup locking."""
        content_hash = ATSService.compute_content_hash(content)
        cache_key = f"ats:{resume_id}:{content_hash}"
        lock_key = f"ats_lock:{resume_id}"

        # 1. Check Redis Cache
        try:
            cached_data = await redis.get(cache_key)
            if cached_data:
                logger.info("ats_cache_hit", resume_id=str(resume_id), hash=content_hash)
                parsed = json.loads(cached_data)
                return ATSScoreResult(**parsed)
        except Exception as e:
            logger.warning("ats_cache_read_failed", error=str(e))

        # 2. Acquire In-Flight Dedup Lock (30s TTL, NX)
        try:
            acquired = await redis.set(lock_key, "locked", ex=30, nx=True)
            if not acquired:
                raise AppException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    error_code="ATS_SCORING_IN_PROGRESS",
                    message="An ATS scoring job for this resume is already processing. Please wait a moment.",
                )
        except AppException:
            raise
        except Exception as e:
            logger.warning("ats_lock_failed", error=str(e))

        try:
            # 3. Call Gemini AI or fallback to Rule-Based Scoring Engine
            result = await ATSService._evaluate_resume(content)

            # 4. Cache valid result in Redis (TTL: 1 Hour)
            try:
                await redis.set(cache_key, json.dumps(result.model_dump()), ex=3600)
            except Exception as e:
                logger.warning("ats_cache_write_failed", error=str(e))

            return result
        finally:
            # 5. Always release dedup lock
            try:
                await redis.delete(lock_key)
            except Exception:
                pass

    @staticmethod
    async def _evaluate_resume(content: Dict[str, Any]) -> ATSScoreResult:
        """Run AI scoring with timeout or deterministic rule-based evaluation."""
        if settings.GEMINI_API_KEY:
            try:
                return await asyncio.wait_for(
                    ATSService._call_gemini_api(content), timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.error("gemini_scoring_timeout")
                raise AppException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    error_code="AI_SERVICE_TIMEOUT",
                    message="ATS scoring service timed out. Please try again.",
                )
            except AppException:
                raise
            except Exception as e:
                logger.warning("gemini_api_call_failed_using_rule_engine", error=str(e))
                return ATSService._rule_based_evaluation(content)
        else:
            # Deterministic, high-fidelity rule-based engine when API key is unset
            return ATSService._rule_based_evaluation(content)

    @staticmethod
    async def _call_gemini_api(content: Dict[str, Any]) -> ATSScoreResult:
        """Call Google Gemini 2.0 Flash Lite with structured schema prompt."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        prompt = f"""
        You are a senior ATS (Applicant Tracking System) recruiter and resume optimization expert.
        Analyze the following candidate resume JSON data and evaluate its ATS readability, action verbs, quantifiable metrics, and clarity.

        Resume Data:
        {json.dumps(content, indent=2)}

        Return a JSON object with this exact structure:
        {{
          "overall_score": <int between 40 and 98>,
          "pass_rate_message": "<Brief 1-line encouraging summary of recruiter pass probability>",
          "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
          "improvements": [
            {{
              "section": "<Section Name e.g. Experience / Projects / Summary>",
              "current": "<Current text excerpt>",
              "suggested": "<Improved phrasing with action verbs and metrics>",
              "impact": "HIGH" | "MEDIUM" | "LOW"
            }}
          ],
          "missing_sections": ["<Any standard missing sections e.g. Certifications, GitHub links>"],
          "is_job_matched": false
        }}
        """

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.0-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        raw_text = response.text
        parsed = json.loads(raw_text)
        return ATSScoreResult(**parsed)

    @staticmethod
    def _rule_based_evaluation(content: Dict[str, Any]) -> ATSScoreResult:
        """High-accuracy heuristic evaluation calculating quantifiable impact and completeness."""
        score = 50
        strengths: list[str] = []
        improvements: list[ATSImprovement] = []
        missing: list[str] = []

        # 1. Check summary
        summary = content.get("summary", "")
        if len(summary) > 60:
            score += 10
            strengths.append("Clear and concise professional headline & summary.")
        else:
            missing.append("Professional Summary")
            improvements.append(
                ATSImprovement(
                    section="Summary",
                    current=summary or "Missing",
                    suggested="Add a 2-3 line summary highlighting your core tech stack, GPA, and key project outcomes.",
                    impact="HIGH",
                )
            )

        # 2. Check education
        educations = content.get("education", [])
        if educations:
            score += 10
            strengths.append("Standard academic credentials and degree details provided.")
        else:
            missing.append("Education")

        # 3. Check experiences
        experiences = content.get("experience", [])
        if experiences:
            score += 15
            strengths.append("Work experience section contains relevant role descriptions.")
        else:
            improvements.append(
                ATSImprovement(
                    section="Experience",
                    current="No internships or work experience listed.",
                    suggested="List academic internships, freelancing projects, or open-source contributions using the XYZ formula (Accomplished [X] as measured by [Y], by doing [Z]).",
                    impact="HIGH",
                )
            )

        # 4. Check projects
        projects = content.get("projects", [])
        if len(projects) >= 2:
            score += 15
            strengths.append("Strong portfolio showcasing 2+ technical software projects.")
        elif len(projects) == 1:
            score += 8
            improvements.append(
                ATSImprovement(
                    section="Projects",
                    current="Single project listed.",
                    suggested="Add a second full-stack or domain-specific project with live deployment and GitHub repository links.",
                    impact="MEDIUM",
                )
            )
        else:
            missing.append("Technical Projects")

        # 5. Check skills
        skills = content.get("skills", [])
        if len(skills) >= 5:
            score += 10
            strengths.append("Broad skill keywords matching modern recruitment filters.")
        else:
            improvements.append(
                ATSImprovement(
                    section="Skills",
                    current=f"{len(skills)} skills listed",
                    suggested="Include both core programming languages and domain frameworks (e.g. Python, TypeScript, PostgreSQL, Docker, AWS).",
                    impact="MEDIUM",
                )
            )

        score = min(96, max(45, score))

        if score >= 85:
            pass_msg = "Excellent ATS formatting! Estimated 92% pass probability across automated recruiter screeners."
        elif score >= 70:
            pass_msg = "Good profile score. Applying the suggestions below will boost recruiter match rate to 90%+."
        else:
            pass_msg = "Resume needs enhancement. Add quantifiable metrics and project details to improve recruiter shortlisting."

        return ATSScoreResult(
            overall_score=score,
            pass_rate_message=pass_msg,
            strengths=strengths,
            improvements=improvements,
            missing_sections=missing,
            is_job_matched=False,
        )
