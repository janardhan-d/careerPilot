"""
CareerPilot — Resume Tool
==========================
Parse PDF/DOCX resumes, extract skills, and score against a job description
using TF-IDF keyword overlap (ATS simulation).

No ML model required — works offline with pure Python.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import structlog

from core.tool_registry import registry
from models.schemas import ResumeAnalysisInput

logger = structlog.get_logger(__name__)


# ── Common tech skill keywords ────────────────────────────────────────────────

SKILL_KEYWORDS: set[str] = {
    # Languages
    "python", "java", "javascript", "typescript", "go", "rust", "scala", "r",
    "c++", "c#", "kotlin", "swift", "ruby", "php",
    # ML / AI
    "pytorch", "tensorflow", "keras", "scikit-learn", "sklearn", "huggingface",
    "transformers", "llm", "gpt", "bert", "xgboost", "lightgbm", "catboost",
    "langchain", "llamaindex", "rag", "fine-tuning", "rlhf", "diffusion",
    # MLOps / Infra
    "mlflow", "kubeflow", "airflow", "prefect", "dagster", "dvc",
    "docker", "kubernetes", "helm", "terraform", "ansible",
    "aws", "gcp", "azure", "s3", "ec2", "gke", "sagemaker", "vertex",
    # Data
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "spark", "hadoop", "kafka", "flink", "dbt", "snowflake", "bigquery",
    "pandas", "numpy", "polars", "dask",
    # Web / API
    "fastapi", "django", "flask", "react", "nodejs", "graphql", "rest",
    # Practices
    "ci/cd", "git", "github actions", "jenkins", "agile", "scrum",
    "microservices", "system design", "distributed systems",
    # Soft skills
    "leadership", "mentoring", "communication", "cross-functional",
}


# ── Text extraction ────────────────────────────────────────────────────────────

def _extract_text_pdf(path: str) -> str:
    """Extract plain text from a PDF resume using pdfplumber."""
    try:
        import pdfplumber
        text_parts: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        return "\n".join(text_parts)
    except ImportError:
        logger.error("resume_tool.pdfplumber_not_installed")
        return ""
    except Exception as exc:
        logger.error("resume_tool.pdf_error", path=path, error=str(exc))
        return ""


def _extract_text_docx(path: str) -> str:
    """Extract plain text from a DOCX resume."""
    try:
        from docx import Document
        doc = Document(path)
        return "\n".join(para.text for para in doc.paragraphs)
    except ImportError:
        logger.error("resume_tool.python_docx_not_installed")
        return ""
    except Exception as exc:
        logger.error("resume_tool.docx_error", path=path, error=str(exc))
        return ""


def extract_text(path: str) -> str:
    """Auto-detect format and extract text from PDF or DOCX."""
    p = Path(path)
    if not p.exists():
        logger.error("resume_tool.file_not_found", path=path)
        return ""
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _extract_text_pdf(path)
    elif suffix in (".docx", ".doc"):
        return _extract_text_docx(path)
    else:
        # Plain text fallback
        return p.read_text(encoding="utf-8", errors="ignore")


# ── Skill extraction ───────────────────────────────────────────────────────────

def extract_skills(text: str) -> list[str]:
    """
    Extract technology skills from raw text using keyword matching.
    Returns a sorted list of unique skills found.
    """
    text_lower = text.lower()
    found = sorted({skill for skill in SKILL_KEYWORDS if skill in text_lower})
    return found


# ── TF-IDF ATS Scorer ─────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Lowercase, remove punctuation, split into tokens."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s/#+]", " ", text)
    return [t for t in text.split() if len(t) > 2]


def _tf(tokens: list[str]) -> dict[str, float]:
    count = Counter(tokens)
    total = max(len(tokens), 1)
    return {word: cnt / total for word, cnt in count.items()}


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Compute cosine similarity between two TF dictionaries."""
    keys = set(vec_a) & set(vec_b)
    if not keys:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
    mag_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def compute_ats_score(resume_text: str, job_description: str) -> dict[str, Any]:
    """
    Compute an ATS-style fit score between a resume and job description.

    Returns
    -------
    dict with:
        fit_score         float 0–100
        matched_skills    list[str]
        missing_skills    list[str]
        keyword_overlap   float  (0–1, cosine similarity)
    """
    resume_skills = set(extract_skills(resume_text))
    jd_skills = set(extract_skills(job_description))

    matched = sorted(resume_skills & jd_skills)
    missing = sorted(jd_skills - resume_skills)

    # Skill overlap score (0-60 points)
    skill_score = 0.0
    if jd_skills:
        skill_score = (len(matched) / len(jd_skills)) * 60

    # Cosine TF similarity score (0-40 points)
    resume_tf = _tf(_tokenize(resume_text))
    jd_tf = _tf(_tokenize(job_description))
    cos_sim = _cosine_similarity(resume_tf, jd_tf)
    cos_score = cos_sim * 40

    fit_score = round(min(skill_score + cos_score, 100.0), 2)

    return {
        "fit_score": fit_score,
        "matched_skills": matched,
        "missing_skills": missing[:10],   # top 10 gaps
        "keyword_overlap": round(cos_sim, 4),
        "resume_skill_count": len(resume_skills),
        "jd_skill_count": len(jd_skills),
    }


# ── Registered Tools ──────────────────────────────────────────────────────────

@registry.tool(
    name="analyze_resume",
    description="Parse a resume file (PDF/DOCX) and compute ATS fit score against a job description.",
    tags=["resume", "ats", "scoring"],
    input_schema=ResumeAnalysisInput,
)
async def analyze_resume(
    resume_path: str,
    job_description: str,
) -> dict[str, Any]:
    """
    Extract skills from resume and score against a job description.

    Parameters
    ----------
    resume_path:     Path to the PDF or DOCX resume file.
    job_description: Raw text of the job description.

    Returns
    -------
    dict: fit_score, matched_skills, missing_skills, keyword_overlap
    """
    resume_text = extract_text(resume_path)
    if not resume_text:
        return {
            "fit_score": 0.0,
            "matched_skills": [],
            "missing_skills": [],
            "keyword_overlap": 0.0,
            "error": "Could not extract text from resume",
        }

    result = compute_ats_score(resume_text, job_description)
    logger.info(
        "resume_tool.scored",
        path=resume_path,
        fit_score=result["fit_score"],
        matched=len(result["matched_skills"]),
        missing=len(result["missing_skills"]),
    )
    return result


@registry.tool(
    name="extract_resume_skills",
    description="Extract a list of technical skills from a resume file.",
    tags=["resume", "skills"],
)
async def extract_resume_skills(resume_path: str) -> dict[str, Any]:
    """
    Extract all recognised skills from a resume.

    Returns
    -------
    dict: skills (list[str])
    """
    text = extract_text(resume_path)
    skills = extract_skills(text)
    return {"resume_path": resume_path, "skills": skills, "count": len(skills)}
