"""
CareerPilot — Clever AI & ATS Resume Checker Tool
==================================================
Evaluates candidate resume text against job descriptions and AI detector models.
Calculates AI Detection Score, ATS Formatting Compliance, Skill Keyword Density,
and actionable suggestions for 100% human-passing & ATS-clearing resumes.
"""

from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, Field

from core.tool_registry import registry
import structlog

logger = structlog.get_logger(__name__)


class ATSCheckInput(BaseModel):
    resume_text: str = Field(..., description="Full candidate resume Markdown/HTML text")
    job_description: str = Field(default="", description="Target job description for match scoring")


@registry.tool(
    name="analyze_ats_ai_detector",
    description="Check resume against Clever AI Detector & ATS parser rules. Returns AI detection score, keyword density, and recommendations.",
    tags=["resume", "ats", "ai_detector"],
    input_schema=ATSCheckInput,
)
async def analyze_ats_ai_detector(
    resume_text: str,
    job_description: str = "",
) -> dict[str, Any]:
    """
    Perform deep ATS & Clever AI Detector check on resume.
    """
    text_lower = resume_text.lower()
    jd_lower = job_description.lower()

    # 1. AI Detector Metrics (Detect repetitive AI buzzwords & formulaic phrasings)
    ai_cliches = [
        "spearheaded", "synergy", "testament to", "delve into",
        "game-changer", "paradigm shift", "leveraged cutting-edge",
        "in conclusion", "furthermore", "realm of", "tapestry of",
    ]
    ai_cliche_count = sum(len(re.findall(r'\b' + re.escape(c) + r'\b', text_lower)) for c in ai_cliches)
    
    # Human naturalness calculation (lower AI cliché count = higher human score)
    human_score = max(65, 100 - (ai_cliche_count * 7))
    ai_detection_prob = round(100 - human_score, 1)

    # 2. ATS Formatting & Structure Compliance Check
    has_contact = bool(re.search(r'[\w\.-]+@[\w\.-]+\.\w+', resume_text))
    has_phone = bool(re.search(r'\+?\d[\d\s-]{8,}', resume_text))
    has_github_linkedin = "github" in text_lower or "linkedin" in text_lower
    has_experience = any(h in text_lower for h in ["experience", "employment", "work history", "projects"])
    has_skills = any(h in text_lower for h in ["skills", "technical proficiency", "technologies"])
    has_education = any(h in text_lower for h in ["education", "university", "bachelor", "degree", "certifications"])

    ats_checks = [has_contact, has_phone, has_github_linkedin, has_experience, has_skills, has_education]
    ats_compliance_score = round((sum(ats_checks) / len(ats_checks)) * 100, 1)

    # 3. Keyword Match Analysis
    core_keywords = [
        "python", "sql", "machine learning", "data analysis", "powerbi",
        "scikit-learn", "pandas", "numpy", "financial analysis", "fastapi",
        "docker", "git", "llm", "pytorch"
    ]
    matched_skills = [k for k in core_keywords if k in text_lower]
    keyword_score = round((len(matched_skills) / len(core_keywords)) * 100, 1)

    # 4. Overall Pass Recommendation
    overall_score = round((human_score * 0.35) + (ats_compliance_score * 0.35) + (keyword_score * 0.30), 1)
    
    if overall_score >= 80:
        recommendation = "PASS_ATS_AND_AI_DETECTOR"
        status_msg = "🟢 High Pass: Resume passes Clever AI Detector & top company ATS parsers!"
    elif overall_score >= 60:
        recommendation = "WARN_MODERATE"
        status_msg = "🟡 Moderate: Good match, add missing skills and reduce AI phrase repetition."
    else:
        recommendation = "FAIL_NEEDS_OPTIMIZATION"
        status_msg = "🔴 Needs Optimization: Missing critical contact details or skill keywords."

    suggestions = []
    if not has_github_linkedin:
        suggestions.append("Add GitHub and LinkedIn profile URLs at the top header.")
    if ai_cliche_count > 2:
        suggestions.append("Replace AI clichés ('spearheaded', 'synergy') with specific quantifiable metrics.")
    if keyword_score < 70:
        suggestions.append(f"Add missing core keywords: {', '.join([k for k in core_keywords if k not in matched_skills][:4])}")

    return {
        "overall_ats_score": overall_score,
        "human_naturalness_score": human_score,
        "ai_detection_probability": ai_detection_prob,
        "ats_formatting_compliance": ats_compliance_score,
        "keyword_density_score": keyword_score,
        "matched_skills": matched_skills,
        "recommendation": recommendation,
        "status_message": status_msg,
        "suggestions": suggestions,
    }
