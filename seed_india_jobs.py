"""
CareerPilot — India Jobs Seeder & Purger
=========================================
Purger of irrelevant foreign jobs, populator of high-fit Indian postings matching Janardhan's candidate profile.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, delete

from models.database import get_session, JobPostingORM, PredictionORM, ApplicationORM, init_db
from agents.predictor import PredictorAgent

INDIA_JOBS = [
    {
        "title": "Data Analyst — Official Career Portal",
        "company": "Amazon",
        "location": "Hyderabad, Telangana, India",
        "description": "We are hiring a Data Analyst on Amazon's official career portal. Build SQL queries, Python data pipelines, pandas/numpy data transformations, and interactive PowerBI dashboards.",
        "skills_mentioned": ["Python", "SQL", "PowerBI", "Data Analysis", "Pandas", "NumPy"],
        "source": "CAREER_PAGE",
        "source_url": "https://www.amazon.jobs/en/search?base_query=Data+Analyst&location[]=hyderabad",
        "is_remote": False,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "Python Developer — Direct Career Portal",
        "company": "Microsoft",
        "location": "Hyderabad, Telangana, India",
        "description": "Microsoft Careers opening for Python Developer. Experience in FastAPI, Docker, SQL databases, Scikit-learn, and Machine Learning integration for cloud services.",
        "skills_mentioned": ["Python", "SQL", "FastAPI", "Machine Learning", "Scikit-learn", "Docker"],
        "source": "CAREER_PAGE",
        "source_url": "https://careers.microsoft.com/us/en/search-results?keywords=Python%20Developer&location=Hyderabad",
        "is_remote": True,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "AI Engineer — Y Combinator Startup",
        "company": "Scale AI",
        "location": "Bengaluru, Karnataka, India (Remote)",
        "description": "Y-Combinator backed startup Scale AI hiring AI Engineer. Design LLM workflows, PyTorch models, Scikit-learn predictors, and automated Data Pipelines.",
        "skills_mentioned": ["Python", "Machine Learning", "PyTorch", "SQL", "Scikit-learn", "LLMs"],
        "source": "YCOMBINATOR",
        "source_url": "https://www.workatastartup.com/companies/scale-ai",
        "is_remote": True,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "Financial Analyst — Cutshort Direct Hire",
        "company": "Swiggy",
        "location": "Bengaluru, Karnataka, India",
        "description": "Cutshort verified opening at Swiggy for Financial Analyst. Skilled in Financial Analysis, Data Analysis, SQL reporting, Python automation, and executive PowerBI dashboards.",
        "skills_mentioned": ["Financial Analysis", "Data Analysis", "SQL", "Python", "PowerBI"],
        "source": "CUTSHORT",
        "source_url": "https://cutshort.io/jobs/swiggy-financial-analyst",
        "is_remote": False,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "Machine Learning Engineer — ZipRecruiter Verified",
        "company": "PhonePe",
        "location": "Bengaluru, Karnataka, India",
        "description": "ZipRecruiter verified opening for ML Engineer at PhonePe. Expertise in Python, SQL, Scikit-learn, PyTorch, Pandas, and Machine Learning deployment.",
        "skills_mentioned": ["Python", "Machine Learning", "Scikit-learn", "SQL", "PyTorch", "Pandas"],
        "source": "ZIPRECRUITER",
        "source_url": "https://www.ziprecruiter.com/candidate/search?search=Machine+Learning+Engineer&location=Bengaluru",
        "is_remote": False,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "Data Analyst — Official Career Page",
        "company": "Razorpay",
        "location": "Bengaluru, Karnataka, India (Remote)",
        "description": "Razorpay official career page position for Data Analyst. Build high-impact analytics pipelines using Python, SQL, PowerBI, Data Analysis, and Financial metrics.",
        "skills_mentioned": ["Data Analysis", "SQL", "Python", "PowerBI", "Financial Analysis"],
        "source": "CAREER_PAGE",
        "source_url": "https://razorpay.com/jobs",
        "is_remote": True,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "AI Research Intern — Google Careers Portal",
        "company": "Google",
        "location": "Hyderabad, Telangana, India",
        "description": "Google Careers official portal for Summer AI internship. Python, PyTorch, Deep Learning, Machine Learning algorithms, and data preprocessing.",
        "skills_mentioned": ["Python", "PyTorch", "Machine Learning", "Deep Learning", "Data Analysis"],
        "source": "CAREER_PAGE",
        "source_url": "https://www.google.com/about/careers/applications/jobs/results/?q=AI%20Research%20Intern&location=Hyderabad",
        "is_remote": False,
        "is_internship": True,
        "easy_apply": True,
    },
    {
        "title": "Data Analyst Intern — Flipkart Career Page",
        "company": "Flipkart",
        "location": "Bengaluru, Karnataka, India",
        "description": "Flipkart Official Career Page for Data Analyst Intern. Required: Python, SQL, Pandas, NumPy, PowerBI basics.",
        "skills_mentioned": ["Python", "SQL", "Pandas", "NumPy", "Data Analysis", "PowerBI"],
        "source": "CAREER_PAGE",
        "source_url": "https://www.flipkartcareers.com",
        "is_remote": True,
        "is_internship": True,
        "easy_apply": True,
    },
]

async def seed():
    await init_db()
    async with get_session() as session:
        # Purge predictions, applications, and jobs
        await session.execute(delete(PredictionORM))
        await session.execute(delete(ApplicationORM))
        await session.execute(delete(JobPostingORM))
        await session.commit()

        for job_data in INDIA_JOBS:
            job_id = str(uuid.uuid4())
            orm_obj = JobPostingORM(
                id=job_id,
                title=job_data["title"],
                company=job_data["company"],
                location=job_data["location"],
                description=job_data["description"],
                skills_mentioned=job_data["skills_mentioned"],
                source=job_data["source"],
                source_url=job_data["source_url"],
                is_remote=job_data["is_remote"],
                is_internship=job_data["is_internship"],
                easy_apply=job_data["easy_apply"],
                discovered_at=datetime.now(timezone.utc),
            )
            session.add(orm_obj)
        await session.commit()

    # Now score all jobs using PredictorAgent
    predictor = PredictorAgent()
    await predictor.on_start()
    async with get_session() as session:
        result = await session.execute(select(JobPostingORM))
        jobs = result.scalars().all()
        for j in jobs:
            res = await predictor._score_job_orm(j)
            pred_orm = PredictionORM(
                id=str(uuid.uuid4()),
                job_id=j.id,
                job_title=j.title,
                company=j.company,
                fit_score=res.fit_score,
                recommendation=res.recommendation,
                response_probability=res.response_probability,
                matched_skills=res.matched_skills,
                missing_skills=res.missing_skills,
                predicted_at=datetime.now(timezone.utc),
            )
            session.add(pred_orm)
        await session.commit()
    print("Seeded and scored targeted India jobs successfully!")

if __name__ == "__main__":
    asyncio.run(seed())
