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
        "title": "Data Analyst — Analytics & BI",
        "company": "Amazon",
        "location": "Hyderabad, Telangana, India",
        "description": "We are hiring a Data Analyst to build SQL queries, Python data pipelines, pandas/numpy data transformations, and interactive PowerBI dashboards for global business metrics.",
        "skills_mentioned": ["Python", "SQL", "PowerBI", "Data Analysis", "Pandas", "NumPy"],
        "source": "LINKEDIN",
        "source_url": "https://www.linkedin.com/jobs/search/?keywords=Data%20Analyst&location=Hyderabad",
        "is_remote": False,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "Python Developer — AI & Automation",
        "company": "Microsoft",
        "location": "Hyderabad, Telangana, India",
        "description": "Looking for a skilled Python Developer with experience in FastAPI, Docker, SQL databases, Scikit-learn, and Machine Learning integration for cloud services.",
        "skills_mentioned": ["Python", "SQL", "FastAPI", "Machine Learning", "Scikit-learn", "Docker"],
        "source": "LINKEDIN",
        "source_url": "https://www.linkedin.com/jobs/search/?keywords=Python%20Developer&location=Hyderabad",
        "is_remote": True,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "AI Engineer — GenAI & Machine Learning",
        "company": "Swiggy",
        "location": "Bengaluru, Karnataka, India (Remote)",
        "description": "Join Swiggy's AI team to design LLM workflows, PyTorch models, Scikit-learn predictors, and automated Data Pipelines using Python and SQL.",
        "skills_mentioned": ["Python", "Machine Learning", "PyTorch", "SQL", "Scikit-learn", "LLMs"],
        "source": "LINKEDIN",
        "source_url": "https://www.linkedin.com/jobs/search/?keywords=AI%20Engineer&location=Bengaluru",
        "is_remote": True,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "Financial Analyst — Risk & Data Modeling",
        "company": "Deloitte",
        "location": "Hyderabad, Telangana, India",
        "description": "Deloitte is seeking a Financial Analyst skilled in Financial Analysis, Data Analysis, SQL reporting, Python automation, and executive PowerBI dashboard creation.",
        "skills_mentioned": ["Financial Analysis", "Data Analysis", "SQL", "Python", "PowerBI"],
        "source": "LINKEDIN",
        "source_url": "https://www.linkedin.com/jobs/search/?keywords=Financial%20Analyst&location=Hyderabad",
        "is_remote": False,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "Machine Learning Engineer — Payment Risk",
        "company": "PhonePe",
        "location": "Bengaluru, Karnataka, India",
        "description": "PhonePe is looking for an ML Engineer with expertise in Python, SQL, Scikit-learn, PyTorch, Pandas, and Machine Learning deployment.",
        "skills_mentioned": ["Python", "Machine Learning", "Scikit-learn", "SQL", "PyTorch", "Pandas"],
        "source": "LINKEDIN",
        "source_url": "https://www.linkedin.com/jobs/search/?keywords=Machine%20Learning%20Engineer&location=Bengaluru",
        "is_remote": False,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "Data Analyst / BI Specialist",
        "company": "Razorpay",
        "location": "Bengaluru, Karnataka, India (Remote)",
        "description": "Build high-impact analytics pipelines using Python, SQL, PowerBI, Data Analysis, and Financial metrics.",
        "skills_mentioned": ["Data Analysis", "SQL", "Python", "PowerBI", "Financial Analysis"],
        "source": "LINKEDIN",
        "source_url": "https://www.linkedin.com/jobs/search/?keywords=Data%20Analyst&location=Bengaluru",
        "is_remote": True,
        "is_internship": False,
        "easy_apply": True,
    },
    {
        "title": "AI Research Intern — Computer Vision & NLP",
        "company": "Google",
        "location": "Hyderabad, Telangana, India",
        "description": "Summer AI internship focusing on Python, PyTorch, Deep Learning, Machine Learning algorithms, and data preprocessing.",
        "skills_mentioned": ["Python", "PyTorch", "Machine Learning", "Deep Learning", "Data Analysis"],
        "source": "LINKEDIN",
        "source_url": "https://www.linkedin.com/jobs/search/?keywords=Machine%20Learning%20Intern&location=India",
        "is_remote": False,
        "is_internship": True,
        "easy_apply": True,
    },
    {
        "title": "Data Analyst Intern",
        "company": "Flipkart",
        "location": "Bengaluru, Karnataka, India",
        "description": "Work with Flipkart's data engineering & analytics team. Required: Python, SQL, Pandas, NumPy, PowerBI basics.",
        "skills_mentioned": ["Python", "SQL", "Pandas", "NumPy", "Data Analysis", "PowerBI"],
        "source": "LINKEDIN",
        "source_url": "https://www.linkedin.com/jobs/search/?keywords=Data%20Analyst%20Intern&location=India",
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
