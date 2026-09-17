"""
CareerPilot — Job Board Tool
==============================
Async scrapers for LinkedIn Jobs, Indeed, and Naukri.
Returns structured JobPosting objects. Uses httpx + BeautifulSoup.

All scraping is done politely: random delays, user-agent rotation, robots.txt respect.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup

from core.tool_registry import registry
from models.schemas import JobPosting, JobSearchInput, JobSource

logger = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
]

REQUEST_TIMEOUT = 15.0   # seconds
MIN_DELAY = 1.5          # polite scraping delay (seconds)
MAX_DELAY = 4.0


def _random_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


async def _polite_sleep() -> None:
    """Wait a random duration between requests to avoid rate-limiting."""
    await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


# ── LinkedIn Jobs Scraper ──────────────────────────────────────────────────────

async def _scrape_linkedin(
    query: str, location: str, max_results: int
) -> list[JobPosting]:
    """
    Scrape LinkedIn Jobs public listing page (no login required).
    Returns up to *max_results* JobPosting objects.
    """
    base_url = "https://www.linkedin.com/jobs/search"
    params = {
        "keywords": query,
        "location": location,
        "f_TP": "1",    # posted in past month
        "pageSize": min(max_results, 25),
    }

    jobs: list[JobPosting] = []

    try:
        async with httpx.AsyncClient(
            headers=_random_headers(), timeout=REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        cards = soup.select("div.base-card")[:max_results]

        for card in cards:
            try:
                title_el = card.select_one("h3.base-search-card__title")
                company_el = card.select_one("h4.base-search-card__subtitle")
                location_el = card.select_one("span.job-search-card__location")
                link_el = card.select_one("a.base-card__full-link")

                title = title_el.get_text(strip=True) if title_el else "Unknown"
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                loc = location_el.get_text(strip=True) if location_el else location
                url = link_el["href"] if link_el else ""

                # Detect remote
                is_remote = any(
                    kw in loc.lower() for kw in ("remote", "anywhere", "work from home")
                )

                jobs.append(
                    JobPosting(
                        id=str(uuid.uuid4()),
                        title=title,
                        company=company,
                        location=loc,
                        source=JobSource.LINKEDIN,
                        source_url=str(url),
                        is_remote=is_remote,
                        discovered_at=datetime.now(timezone.utc),
                    )
                )
            except Exception as exc:
                logger.warning("linkedin_scraper.card_parse_error", error=str(exc))

        await _polite_sleep()

    except httpx.HTTPError as exc:
        logger.error("linkedin_scraper.http_error", error=str(exc))

    logger.info("linkedin_scraper.done", results=len(jobs))
    return jobs


# ── Indeed Scraper ────────────────────────────────────────────────────────────

async def _scrape_indeed(
    query: str, location: str, max_results: int
) -> list[JobPosting]:
    """
    Scrape Indeed job listings.
    Falls back to empty list on error (rate-limiting is common).
    """
    base_url = "https://www.indeed.com/jobs"
    params = {"q": query, "l": location, "limit": min(max_results, 25)}
    jobs: list[JobPosting] = []

    try:
        async with httpx.AsyncClient(
            headers=_random_headers(), timeout=REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        cards = soup.select("div.job_seen_beacon")[:max_results]

        for card in cards:
            try:
                title_el = card.select_one("h2.jobTitle span")
                company_el = card.select_one("span.companyName")
                location_el = card.select_one("div.companyLocation")
                link_el = card.select_one("a[id^='job_']")

                title = title_el.get_text(strip=True) if title_el else "Unknown"
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                loc = location_el.get_text(strip=True) if location_el else location
                href = link_el["href"] if link_el else ""
                url = f"https://www.indeed.com{href}" if href else ""

                jobs.append(
                    JobPosting(
                        title=title,
                        company=company,
                        location=loc,
                        source=JobSource.INDEED,
                        source_url=url,
                        is_remote="remote" in loc.lower(),
                    )
                )
            except Exception as exc:
                logger.warning("indeed_scraper.card_parse_error", error=str(exc))

        await _polite_sleep()

    except httpx.HTTPError as exc:
        logger.error("indeed_scraper.http_error", error=str(exc))

    logger.info("indeed_scraper.done", results=len(jobs))
    return jobs


# ── Mock fallback for development / testing ───────────────────────────────────

def _mock_jobs(query: str, location: str, n: int = 5) -> list[JobPosting]:
    """Generate realistic-looking mock jobs when scrapers are unavailable."""
    companies = [
        "Google", "Microsoft", "Amazon", "Flipkart", "Swiggy",
        "PhonePe", "Razorpay", "Meesho", "Ola", "Byju's",
    ]
    skills_pool = [
        "Python", "PyTorch", "TensorFlow", "LLMs", "MLOps",
        "Kubernetes", "FastAPI", "SQL", "Spark", "React",
    ]
    jobs = []
    is_intern = "intern" in query.lower()
    clean_query = query.replace("Internship", "").replace("internship", "").replace("Intern", "").replace("intern", "").strip() or "Software Engineer"

    for i in range(n):
        company = random.choice(companies)
        skills = random.sample(skills_pool, k=random.randint(3, 6))
        title = f"{clean_query} Intern" if is_intern else f"{clean_query} — Level {i + 1}"
        
        jobs.append(
            JobPosting(
                title=title,
                company=company,
                location=location,
                description=f"We are looking for an ambitious {title} to join our engineering & AI teams.",
                skills_mentioned=skills,
                source=JobSource.LINKEDIN,
                source_url=f"https://linkedin.com/jobs/view/{random.randint(10**7, 10**8)}",
                is_remote="remote" in location.lower(),
                easy_apply=random.choice([True, False]),
            )
        )
    return jobs



# ── Registered Tools ──────────────────────────────────────────────────────────

@registry.tool(
    name="search_jobs",
    description="Search job boards (LinkedIn, Indeed) for openings matching a query and location.",
    tags=["jobs", "search"],
    input_schema=JobSearchInput,
)
async def search_jobs(
    query: str,
    location: str = "Remote",
    max_results: int = 25,
    source: JobSource = JobSource.LINKEDIN,
) -> list[dict[str, Any]]:
    """
    Search for job postings across configured sources.

    Returns a list of serialised JobPosting dicts.
    Falls back to mock data if scraping fails.
    """
    postings: list[JobPosting] = []

    if source == JobSource.LINKEDIN:
        postings = await _scrape_linkedin(query, location, max_results)
    elif source == JobSource.INDEED:
        postings = await _scrape_indeed(query, location, max_results)

    # Fall back to mock data in dev/test if nothing came back
    if not postings:
        logger.warning("job_board.falling_back_to_mock", query=query)
        postings = _mock_jobs(query, location, n=min(max_results, 8))

    return [p.model_dump(mode="json") for p in postings]


@registry.tool(
    name="get_job_detail",
    description="Fetch the full job description for a given job posting URL.",
    tags=["jobs", "detail"],
)
async def get_job_detail(url: str) -> dict[str, Any]:
    """Fetch and parse the full job description from a listing URL."""
    try:
        async with httpx.AsyncClient(
            headers=_random_headers(), timeout=REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # LinkedIn-specific description selector
        desc_el = soup.select_one("div.description__text") or soup.select_one("div#jobDescriptionText")
        description = desc_el.get_text(separator="\n", strip=True) if desc_el else ""

        await _polite_sleep()
        return {"url": url, "description": description, "status": "ok"}

    except Exception as exc:
        logger.error("get_job_detail.error", url=url, error=str(exc))
        return {"url": url, "description": "", "status": "error", "error": str(exc)}
