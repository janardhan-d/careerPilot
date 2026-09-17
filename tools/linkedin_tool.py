"""
CareerPilot — LinkedIn Tool
============================
Read and update your LinkedIn profile using the unofficial linkedin-api library.
Falls back to a mock profile when credentials are not configured.

Registered tools:
  - get_linkedin_profile   → fetch your public profile data
  - search_linkedin_jobs   → search LinkedIn Jobs (with full detail)
  - update_linkedin_headline → update profile headline (requires auth)
"""

from __future__ import annotations

from typing import Any

import structlog

from core.config import settings
from core.tool_registry import registry
from models.schemas import JobPosting, JobSource

logger = structlog.get_logger(__name__)


# ── Lazy LinkedIn client ───────────────────────────────────────────────────────

_linkedin_client: Any = None


def _get_client() -> Any:
    """
    Lazily initialise the linkedin-api client.
    Returns None if credentials are not configured.
    """
    global _linkedin_client
    if _linkedin_client is not None:
        return _linkedin_client

    if not settings.linkedin_email or not settings.linkedin_password:
        logger.warning("linkedin_tool.no_credentials")
        return None

    try:
        from linkedin_api import Linkedin  # type: ignore[import]
        _linkedin_client = Linkedin(settings.linkedin_email, settings.linkedin_password)
        logger.info("linkedin_tool.authenticated", email=settings.linkedin_email)
        return _linkedin_client
    except ImportError:
        logger.error(
            "linkedin_tool.library_not_installed",
            hint="pip install linkedin-api",
        )
        return None
    except Exception as exc:
        logger.error("linkedin_tool.auth_failed", error=str(exc))
        return None


# ── Mock profile (dev / no credentials) ──────────────────────────────────────

def _mock_profile() -> dict[str, Any]:
    return {
        "firstName": "Your",
        "lastName": "Name",
        "headline": "AI/ML Engineer | Open to Work",
        "summary": "Experienced in building scalable ML systems...",
        "industryName": "Technology",
        "locationName": "India",
        "skills": [
            {"name": "Python"}, {"name": "PyTorch"}, {"name": "FastAPI"},
            {"name": "MLOps"}, {"name": "LangChain"},
        ],
        "experience": [
            {
                "companyName": "Previous Company",
                "title": "ML Engineer",
                "timePeriod": {"startDate": {"year": 2021}, "endDate": {"year": 2024}},
            }
        ],
        "education": [
            {
                "schoolName": "University",
                "degreeName": "B.Tech",
                "fieldOfStudy": "Computer Science",
            }
        ],
        "is_mock": True,
    }


# ── Registered Tools ──────────────────────────────────────────────────────────

@registry.tool(
    name="get_linkedin_profile",
    description="Fetch your LinkedIn profile data including skills, experience, and education.",
    tags=["linkedin", "profile", "read"],
)
async def get_linkedin_profile(profile_url: str = "") -> dict[str, Any]:
    """
    Retrieve LinkedIn profile information.

    Parameters
    ----------
    profile_url: Optional public profile URL or username. Defaults to own profile.

    Returns
    -------
    dict: Profile data (name, headline, skills, experience, etc.)
    """
    client = _get_client()

    if client is None:
        logger.warning("linkedin_tool.using_mock_profile")
        return _mock_profile()

    try:
        # Extract username from URL or use as-is
        username = profile_url.rstrip("/").split("/")[-1] if profile_url else "me"
        profile = client.get_profile(username)
        logger.info("linkedin_tool.profile_fetched", username=username)
        return dict(profile)
    except Exception as exc:
        logger.error("linkedin_tool.profile_fetch_failed", error=str(exc))
        return _mock_profile()


@registry.tool(
    name="search_linkedin_jobs",
    description="Search LinkedIn for job postings. Returns structured JobPosting objects.",
    tags=["linkedin", "jobs", "search"],
)
async def search_linkedin_jobs(
    keywords: str,
    location: str = "Remote",
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """
    Search LinkedIn Jobs via the authenticated API (more results + detail than scraping).

    Parameters
    ----------
    keywords:    Job title or skill keywords.
    location:    Target location string.
    max_results: Maximum number of results to return.

    Returns
    -------
    list[dict]: Serialised JobPosting objects.
    """
    client = _get_client()
    jobs: list[JobPosting] = []

    if client is None:
        # Fall back to public scraper
        from tools.job_board_tool import _scrape_linkedin, _mock_jobs
        scraped = await _scrape_linkedin(keywords, location, max_results)
        return [j.model_dump(mode="json") for j in scraped] if scraped else [
            j.model_dump(mode="json") for j in _mock_jobs(keywords, location, max_results)
        ]

    try:
        raw_jobs = client.search_jobs(
            keywords=keywords,
            location_name=location,
            limit=max_results,
        )
        for raw in raw_jobs:
            entity = raw.get("trackingUrn", "")
            title = raw.get("title", "Unknown")
            company_data = raw.get("primaryDescription", {})
            company = company_data.get("text", "Unknown") if isinstance(company_data, dict) else "Unknown"
            loc_data = raw.get("secondaryDescription", {})
            loc = loc_data.get("text", location) if isinstance(loc_data, dict) else location

            jobs.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=loc,
                    source=JobSource.LINKEDIN,
                    source_url=f"https://www.linkedin.com/jobs/view/{entity}",
                    is_remote="remote" in loc.lower(),
                )
            )
        logger.info("linkedin_tool.jobs_found", count=len(jobs))
    except Exception as exc:
        logger.error("linkedin_tool.job_search_failed", error=str(exc))

    return [j.model_dump(mode="json") for j in jobs]


@registry.tool(
    name="update_linkedin_headline",
    description="Update your LinkedIn profile headline.",
    tags=["linkedin", "profile", "write"],
)
async def update_linkedin_headline(new_headline: str) -> dict[str, Any]:
    """
    Update the LinkedIn profile headline.

    Parameters
    ----------
    new_headline: The new headline string (max 220 chars).

    Returns
    -------
    dict: {"success": bool, "headline": str}
    """
    if len(new_headline) > 220:
        return {"success": False, "error": "Headline exceeds 220 characters"}

    client = _get_client()
    if client is None:
        logger.warning("linkedin_tool.cannot_update_no_credentials")
        return {"success": False, "error": "LinkedIn credentials not configured"}

    try:
        client.update_profile(headline=new_headline)
        logger.info("linkedin_tool.headline_updated", headline=new_headline)
        return {"success": True, "headline": new_headline}
    except Exception as exc:
        logger.error("linkedin_tool.update_failed", error=str(exc))
        return {"success": False, "error": str(exc)}
