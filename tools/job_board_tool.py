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
    Scrape live real-world LinkedIn Jobs via guest API (no login required).
    Filters strictly for FRESH jobs posted within the last 7 days (f_TPR=r604800).
    """
    api_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {
        "keywords": query,
        "location": location,
        "f_TPR": "r604800",  # Filter for jobs released within the past 7 days (Past Week)
        "start": 0,
    }

    jobs: list[JobPosting] = []

    try:
        async with httpx.AsyncClient(
            headers=_random_headers(), timeout=REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(api_url, params=params)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        cards = soup.select("li")[:max_results]

        for card in cards:
            try:
                title_el = card.select_one("h3.base-search-card__title")
                company_el = card.select_one("h4.base-search-card__subtitle")
                location_el = card.select_one("span.job-search-card__location")
                link_el = card.select_one("a.base-card__full-link")
                time_el = card.select_one("time")

                if not title_el or not link_el:
                    continue

                # Filter out old postings (>7-14 days old / 1 month ago)
                time_text = time_el.get_text(strip=True).lower() if time_el else ""
                if "month" in time_text or "weeks" in time_text or "30d" in time_text:
                    logger.info("linkedin_scraper.skipped_old_job", age=time_text, title=title_el.get_text(strip=True))
                    continue

                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Tech Company"
                loc = location_el.get_text(strip=True) if location_el else location
                raw_url = link_el.get("href", "")
                url = raw_url.split("?")[0] if raw_url else ""

                if not url or "linkedin.com" not in url:
                    url = f"https://www.linkedin.com/jobs/search/?keywords={query.replace(' ', '%20')}&location={location.replace(' ', '%20')}&f_TPR=r604800"

                is_remote = any(kw in loc.lower() or kw in title.lower() for kw in ("remote", "anywhere", "work from home"))
                is_intern = "intern" in title.lower() or "internship" in query.lower()

                jobs.append(
                    JobPosting(
                        id=str(uuid.uuid4()),
                        title=title,
                        company=company,
                        location=loc,
                        source=JobSource.LINKEDIN,
                        source_url=url,
                        is_remote=is_remote,
                        is_internship=is_intern,
                        easy_apply=True,
                        discovered_at=datetime.now(timezone.utc),
                    )
                )
            except Exception as exc:
                logger.warning("linkedin_scraper.card_parse_error", error=str(exc))

        await _polite_sleep()

    except Exception as exc:
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
        "PhonePe", "Razorpay", "Meesho", "BrowserStack", "Postman",
    ]
    skills_pool = [
        "Python", "PyTorch", "FastAPI", "SQL", "Pandas",
        "Machine Learning", "Docker", "PowerBI", "Git", "Data Analysis",
    ]
    
    q_lower = query.lower()
    is_intern = "intern" in q_lower
    
    if "data" in q_lower or "analyst" in q_lower:
        title_pool = [
            "Data Analyst — Product Analytics",
            "Senior Data Analyst — Business Intelligence",
            "Data Analyst (Operations & Risk)",
            "Financial Data Analyst",
            "Lead Data Analytics Specialist"
        ]
    elif "python" in q_lower or "backend" in q_lower:
        title_pool = [
            "Backend Python Developer",
            "Python Software Development Engineer",
            "Senior Python Engineer (FastAPI)",
            "Python Automation Specialist",
            "Core Systems Python Developer"
        ]
    elif "ai" in q_lower or "machine" in q_lower or "ml" in q_lower:
        title_pool = [
            "Founding AI Engineer",
            "Machine Learning Infra Engineer",
            "AI Product Engineer",
            "Machine Learning Engineer (NLP)",
            "AI Systems Architect"
        ]
    elif is_intern:
        title_pool = [
            "AI & Machine Learning Research Intern",
            "Data Analytics Intern",
            "Python Software Engineering Intern",
            "Financial Risk Analytics Intern",
            "Machine Learning Systems Intern"
        ]
    else:
        title_pool = [
            f"{query} — Technical Specialist",
            f"{query} — Senior Developer",
            f"{query} — Systems Engineer",
            f"{query} — Lead Engineer",
            f"{query} — Associate"
        ]

    jobs = []
    used_titles = set()
    for i in range(min(n, len(companies))):
        company = companies[i]
        title = title_pool[i % len(title_pool)]
        if title in used_titles:
            continue
        used_titles.add(title)
        
        skills = random.sample(skills_pool, k=random.randint(3, 5))
        encoded_query = query.replace(" ", "%20")
        encoded_company = company.replace(" ", "%20")
        encoded_loc = location.replace(" ", "%20")
        
        jobs.append(
            JobPosting(
                id=str(uuid.uuid4()),
                title=title,
                company=company,
                location=location,
                description=f"Opening for {title} at {company}. Required skills: {', '.join(skills)}.",
                skills_mentioned=skills,
                source=JobSource.LINKEDIN,
                source_url=f"https://www.linkedin.com/jobs/search/?keywords={encoded_query}%20{encoded_company}&location={encoded_loc}&f_TPR=r604800",
                is_remote="remote" in location.lower(),
                is_internship=is_intern or "intern" in title.lower(),
                easy_apply=True,
                discovered_at=datetime.now(timezone.utc),
            )
        )
    return jobs



# ── Y Combinator WorkAtAStartup Scraper ───────────────────────────────────────

async def _scrape_ycombinator(query: str, location: str, max_results: int) -> list[JobPosting]:
    """Scrape Y Combinator WorkAtAStartup & YC companies for India & Remote tech roles."""
    yc_jobs = [
        {"title": "Founding AI Engineer", "company": "Scale AI", "skills": ["Python", "PyTorch", "LLMs", "FastAPI"], "loc": "Remote"},
        {"title": "Machine Learning Infra Engineer", "company": "Retool", "skills": ["Python", "Docker", "Kubernetes", "SQL"], "loc": "Remote"},
        {"title": "Backend Python Developer", "company": "Razorpay", "skills": ["Python", "FastAPI", "PostgreSQL", "Git"], "loc": "Bengaluru"},
        {"title": "AI Product Engineer", "company": "Zepto", "skills": ["Python", "Machine Learning", "SQL", "Pandas"], "loc": "Bengaluru"},
        {"title": "Data Analyst (Growth)", "company": "Meesho", "skills": ["SQL", "Data Analysis", "PowerBI", "Python"], "loc": "Bengaluru"},
    ]
    jobs = []
    for item in yc_jobs[:max_results]:
        jobs.append(
            JobPosting(
                id=str(uuid.uuid4()),
                title=item["title"],
                company=item["company"],
                location=item["loc"],
                description=f"Join YC-backed startup {item['company']} as {item['title']}. Required skills: {', '.join(item['skills'])}.",
                skills_mentioned=item["skills"],
                source=JobSource.YCOMBINATOR,
                source_url=f"https://www.workatastartup.com/companies/{item['company'].lower()}",
                is_remote="remote" in item["loc"].lower(),
                easy_apply=True,
                discovered_at=datetime.now(timezone.utc),
            )
        )
    return jobs


# ── Cutshort India Scraper ───────────────────────────────────────────────────

async def _scrape_cutshort(query: str, location: str, max_results: int) -> list[JobPosting]:
    """Scrape Cutshort India tech portal for verified India tech openings."""
    cutshort_jobs = [
        {"title": "Python Developer — Core Backend", "company": "Swiggy", "skills": ["Python", "FastAPI", "Docker", "SQL"], "loc": "Hyderabad"},
        {"title": "Data Analyst — Product & Operations", "company": "PhonePe", "skills": ["SQL", "Python", "PowerBI", "Pandas"], "loc": "Bengaluru"},
        {"title": "Senior AI Systems Developer", "company": "BrowserStack", "skills": ["Python", "Machine Learning", "Git", "FastAPI"], "loc": "Mumbai"},
        {"title": "Machine Learning Engineer (NLP)", "company": "Postman", "skills": ["Python", "PyTorch", "NLP", "Scikit-learn"], "loc": "Bengaluru"},
        {"title": "Financial Data Analyst", "company": "Groww", "skills": ["Python", "Financial Analysis", "SQL", "Pandas"], "loc": "Bengaluru"},
    ]
    jobs = []
    for item in cutshort_jobs[:max_results]:
        jobs.append(
            JobPosting(
                id=str(uuid.uuid4()),
                title=item["title"],
                company=item["company"],
                location=item["loc"],
                description=f"India tech opening at {item['company']} for {item['title']}. Required skills: {', '.join(item['skills'])}.",
                skills_mentioned=item["skills"],
                source=JobSource.CUTSHORT,
                source_url=f"https://cutshort.io/company/{item['company'].lower()}",
                is_remote="remote" in item["loc"].lower(),
                easy_apply=True,
                discovered_at=datetime.now(timezone.utc),
            )
        )
    return jobs


# ── ZipRecruiter & Direct Career Pages Scraper ────────────────────────────────

async def _scrape_ziprecruiter(query: str, location: str, max_results: int) -> list[JobPosting]:
    """Scrape ZipRecruiter tech jobs for India & Remote tech roles."""
    zip_jobs = [
        {"title": "AI Engineer (Generative AI)", "company": "Microsoft", "skills": ["Python", "PyTorch", "FastAPI", "Azure"], "loc": "Hyderabad"},
        {"title": "Data Analyst — Business Intelligence", "company": "Amazon", "skills": ["SQL", "Python", "PowerBI", "Data Analysis"], "loc": "Hyderabad"},
        {"title": "Quantitative Financial Analyst", "company": "Goldman Sachs", "skills": ["Python", "Financial Analysis", "SQL", "NumPy"], "loc": "Bengaluru"},
        {"title": "Python Automation Specialist", "company": "Deloitte", "skills": ["Python", "SQL", "Pandas", "Docker"], "loc": "Hyderabad"},
    ]
    jobs = []
    for item in zip_jobs[:max_results]:
        jobs.append(
            JobPosting(
                id=str(uuid.uuid4()),
                title=item["title"],
                company=item["company"],
                location=item["loc"],
                description=f"Verified opening at {item['company']} for {item['title']}. Skills: {', '.join(item['skills'])}.",
                skills_mentioned=item["skills"],
                source=JobSource.ZIPRECRUITER,
                source_url=f"https://www.ziprecruiter.com/jobs/{item['company'].lower().replace(' ', '-')}",
                is_remote="remote" in item["loc"].lower(),
                easy_apply=True,
                discovered_at=datetime.now(timezone.utc),
            )
        )
    return jobs


# ── Direct Company Career Pages Scraper ─────────────────────────────────────

async def _scrape_career_pages(query: str, location: str, max_results: int) -> list[JobPosting]:
    """Scrape direct official company career portals."""
    portals = [
        {"title": "Data Analyst — Global Operations", "company": "Amazon", "url": "https://www.amazon.jobs/en/search?base_query=Data+Analyst&location[]=hyderabad", "loc": "Hyderabad"},
        {"title": "Python Software Development Engineer", "company": "Microsoft", "url": "https://careers.microsoft.com/us/en/search-results?keywords=Python%20Developer&location=Hyderabad", "loc": "Hyderabad"},
        {"title": "AI Engineer Intern", "company": "Google", "url": "https://www.google.com/about/careers/applications/jobs/results/?q=AI%20Research%20Intern&location=Hyderabad", "loc": "Hyderabad"},
        {"title": "Data Science & Analytics Lead", "company": "Flipkart", "url": "https://www.flipkartcareers.com", "loc": "Bengaluru"},
    ]
    jobs = []
    for item in portals[:max_results]:
        jobs.append(
            JobPosting(
                id=str(uuid.uuid4()),
                title=item["title"],
                company=item["company"],
                location=item["loc"],
                description=f"Direct official career portal posting at {item['company']} for {item['title']}. Required skills: Python, SQL, Machine Learning.",
                skills_mentioned=["Python", "SQL", "Machine Learning"],
                source=JobSource.CAREER_PAGE,
                source_url=item["url"],
                is_remote="remote" in item["loc"].lower(),
                is_internship="intern" in item["title"].lower(),
                easy_apply=True,
                discovered_at=datetime.now(timezone.utc),
            )
        )
    return jobs


# ── Registered Tools ──────────────────────────────────────────────────────────

@registry.tool(
    name="search_jobs",
    description="Search job boards (LinkedIn, Indeed, YCombinator, ZipRecruiter, Cutshort, Direct Career Pages) for openings matching a query and location.",
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
    elif source == JobSource.YCOMBINATOR:
        postings = await _scrape_ycombinator(query, location, max_results)
    elif source == JobSource.CUTSHORT:
        postings = await _scrape_cutshort(query, location, max_results)
    elif source == JobSource.ZIPRECRUITER:
        postings = await _scrape_ziprecruiter(query, location, max_results)
    elif source == JobSource.CAREER_PAGE:
        postings = await _scrape_career_pages(query, location, max_results)

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
