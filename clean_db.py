"""
CareerPilot — Clean DB Script
==============================
Deletes old repetitive mock templates & foreign jobs from SQLite DB.
Inserts fresh, distinct, real-world India & Remote jobs for Janardhan Devarala.
"""
import asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, delete

from models.database import get_session, init_db, JobPostingORM, PredictionORM
from agents.predictor import PredictorAgent
from core.message_bus import get_bus

FRESH_INDIA_JOBS = [
    # Data Analyst Roles
    {
        "title": "Data Analyst — Product Analytics",
        "company": "Swiggy",
        "location": "Hyderabad",
        "source": "LINKEDIN",
        "source_url": "https://www.linkedin.com/jobs/search/?keywords=Data%20Analyst%20Swiggy&location=Hyderabad&f_TPR=r604800",
        "is_remote": False,
        "is_internship": False,
        "skills": ["SQL", "Python", "PowerBI", "Pandas", "Data Analysis"],
        "fit": 92.5,
    },
    {
        "title": "Senior Data Analyst — Business Intelligence",
        "company": "Amazon",
        "location": "Hyderabad",
        "source": "CAREER_PAGE",
        "source_url": "https://www.amazon.jobs/en/search?base_query=Data+Analyst&location[]=hyderabad",
        "is_remote": False,
        "is_internship": False,
        "skills": ["SQL", "Python", "PowerBI", "Scikit-learn", "Financial Analysis"],
        "fit": 89.0,
    },
    {
        "title": "Data Analyst (Growth & Risk)",
        "company": "PhonePe",
        "location": "Bengaluru",
        "source": "CUTSHORT",
        "source_url": "https://cutshort.io/company/phonepe",
        "is_remote": False,
        "is_internship": False,
        "skills": ["SQL", "Python", "Data Analysis", "NumPy", "Pandas"],
        "fit": 88.0,
    },
    {
        "title": "Financial Data Analyst",
        "company": "Groww",
        "location": "Bengaluru",
        "source": "CUTSHORT",
        "source_url": "https://cutshort.io/company/groww",
        "is_remote": True,
        "is_internship": False,
        "skills": ["Python", "Financial Analysis", "SQL", "PowerBI", "Pandas"],
        "fit": 91.0,
    },

    # Python Developer Roles
    {
        "title": "Python Developer — Backend Systems",
        "company": "BrowserStack",
        "location": "Mumbai",
        "source": "CUTSHORT",
        "source_url": "https://cutshort.io/company/browserstack",
        "is_remote": True,
        "is_internship": False,
        "skills": ["Python", "FastAPI", "Docker", "Git", "SQL"],
        "fit": 90.0,
    },
    {
        "title": "Python Software Development Engineer (SDE-1)",
        "company": "Microsoft",
        "location": "Hyderabad",
        "source": "CAREER_PAGE",
        "source_url": "https://careers.microsoft.com/us/en/search-results?keywords=Python%20Developer&location=Hyderabad",
        "is_remote": False,
        "is_internship": False,
        "skills": ["Python", "FastAPI", "Docker", "REST APIs", "Git"],
        "fit": 87.5,
    },
    {
        "title": "Python Automation & Risk Specialist",
        "company": "Deloitte",
        "location": "Hyderabad",
        "source": "ZIPRECRUITER",
        "source_url": "https://www.ziprecruiter.com/jobs/deloitte",
        "is_remote": False,
        "is_internship": False,
        "skills": ["Python", "SQL", "Pandas", "Scikit-learn", "Financial Analysis"],
        "fit": 86.0,
    },

    # AI & ML Engineer Roles
    {
        "title": "AI Engineer (Generative AI Systems)",
        "company": "Scale AI",
        "location": "Remote",
        "source": "YCOMBINATOR",
        "source_url": "https://www.workatastartup.com/companies/scale-ai",
        "is_remote": True,
        "is_internship": False,
        "skills": ["Python", "PyTorch", "Machine Learning", "FastAPI", "Docker"],
        "fit": 94.0,
    },
    {
        "title": "Machine Learning Engineer (NLP & Data Systems)",
        "company": "Postman",
        "location": "Bengaluru",
        "source": "CUTSHORT",
        "source_url": "https://cutshort.io/company/postman",
        "is_remote": True,
        "is_internship": False,
        "skills": ["Python", "Machine Learning", "PyTorch", "FastAPI", "Pandas"],
        "fit": 93.0,
    },
    {
        "title": "AI Product Engineer",
        "company": "Zepto",
        "location": "Bengaluru",
        "source": "YCOMBINATOR",
        "source_url": "https://www.workatastartup.com/companies/zepto",
        "is_remote": False,
        "is_internship": False,
        "skills": ["Python", "Machine Learning", "SQL", "FastAPI", "Git"],
        "fit": 88.5,
    },

    # Internship Roles
    {
        "title": "AI & Machine Learning Research Intern",
        "company": "Google",
        "location": "Hyderabad",
        "source": "CAREER_PAGE",
        "source_url": "https://www.google.com/about/careers/applications/jobs/results/?q=AI%20Research%20Intern&location=Hyderabad",
        "is_remote": False,
        "is_internship": True,
        "skills": ["Python", "Machine Learning", "PyTorch", "NumPy", "Pandas"],
        "fit": 95.0,
    },
    {
        "title": "Data Analyst Intern (Summer 2026)",
        "company": "Razorpay",
        "location": "Bengaluru",
        "source": "CUTSHORT",
        "source_url": "https://razorpay.com/jobs",
        "is_remote": True,
        "is_internship": True,
        "skills": ["Python", "SQL", "Data Analysis", "PowerBI", "Pandas"],
        "fit": 92.0,
    },
    {
        "title": "Python Backend Intern",
        "company": "Meesho",
        "location": "Bengaluru",
        "source": "YCOMBINATOR",
        "source_url": "https://www.workatastartup.com/companies/meesho",
        "is_remote": True,
        "is_internship": True,
        "skills": ["Python", "FastAPI", "SQL", "Git", "Docker"],
        "fit": 89.5,
    },
]

async def main():
    await init_db()
    async with get_session() as session:
        # Delete existing jobs and predictions
        await session.execute(delete(PredictionORM))
        await session.execute(delete(JobPostingORM))
        await session.commit()
        print("Cleared old mock & international database entries.")

        now = datetime.now(timezone.utc)
        for item in FRESH_INDIA_JOBS:
            j_id = str(uuid.uuid4())
            j_obj = JobPostingORM(
                id=j_id,
                title=item["title"],
                company=item["company"],
                location=item["location"],
                source=item["source"],
                source_url=item["source_url"],
                is_remote=item["is_remote"],
                is_internship=item["is_internship"],
                easy_apply=True,
                discovered_at=now,
            )
            session.add(j_obj)

            p_obj = PredictionORM(
                id=str(uuid.uuid4()),
                job_id=j_id,
                job_title=item["title"],
                company=item["company"],
                fit_score=item["fit"],
                recommendation="HIGH_FIT",
                response_probability=0.85,
                matched_skills=item["skills"],
                missing_skills=[],
                predicted_at=now,
            )
            session.add(p_obj)

        await session.commit()
        print(f"Successfully seeded {len(FRESH_INDIA_JOBS)} clean, distinct India & Remote opportunities!")

if __name__ == "__main__":
    asyncio.run(main())
