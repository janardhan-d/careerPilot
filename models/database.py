"""
CareerPilot — Database Layer
==============================
SQLAlchemy 2.x async ORM with aiosqlite.
Provides table definitions, async session factory, and init helpers.

Usage
-----
>>> from models.database import get_session, init_db
>>> await init_db()
>>> async with get_session() as session:
...     session.add(JobPostingORM(...))
...     await session.commit()
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    JSON,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.config import settings


# ── Base class ────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


# ── ORM Tables ────────────────────────────────────────────────────────────────

class JobPostingORM(Base):
    """Persisted job posting discovered from any source."""

    __tablename__ = "job_postings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(256))
    company: Mapped[str] = mapped_column(String(256))
    location: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    source: Mapped[str] = mapped_column(String(32), default="LINKEDIN")
    source_url: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    experience_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False)
    is_internship: Mapped[bool] = mapped_column(Boolean, default=False)
    skills_mentioned: Mapped[list] = mapped_column(JSON, default=list)
    easy_apply: Mapped[bool] = mapped_column(Boolean, default=False)


class ApplicationORM(Base):
    """Persisted job application with lifecycle tracking."""

    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36))
    job_title: Mapped[str] = mapped_column(String(256))
    company: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="DISCOVERED")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    cover_letter: Mapped[str] = mapped_column(Text, default="")
    resume_version: Mapped[str] = mapped_column(String(64), default="default")
    cover_letter_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    follow_up_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    interview_dates: Mapped[list] = mapped_column(JSON, default=list)
    offer_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserProfileORM(Base):
    """Persisted User Profile for fast match & auto-apply matching."""

    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    full_name: Mapped[str] = mapped_column(String(128), default="Janardhan Devarala")
    email: Mapped[str] = mapped_column(String(128), default="devaralajanardhan@gmail.com")
    phone: Mapped[str] = mapped_column(String(32), default="+91 9876543210")
    location: Mapped[str] = mapped_column(String(128), default="Hyderabad / Bengaluru, India")
    target_roles: Mapped[list] = mapped_column(JSON, default=lambda: ["Data Analyst", "Python Developer", "Financial Analyst", "AI Engineer"])
    skills: Mapped[list] = mapped_column(JSON, default=lambda: ["Python", "SQL", "Data Analysis", "Machine Learning", "PowerBI", "Scikit-learn", "Financial Analysis", "Pandas", "NumPy", "FastAPI", "Docker", "Git"])
    experience_level: Mapped[str] = mapped_column(String(32), default="ENTRY_LEVEL")
    prefer_internships: Mapped[bool] = mapped_column(Boolean, default=True)
    bio: Mapped[str] = mapped_column(Text, default="Passionate AI & Data Analyst engineer experienced in Python, ML models, financial analysis, and full-stack automation.")
    portfolio_url: Mapped[str] = mapped_column(String(256), default="https://janardhan-d.github.io")
    linkedin_url: Mapped[str] = mapped_column(String(256), default="https://linkedin.com/in/janardhan-devarala")
    github_url: Mapped[str] = mapped_column(String(256), default="https://github.com/janardhan-d")
    gdrive_resume_url: Mapped[str] = mapped_column(String(256), default="https://drive.google.com/file/d/janardhan-devarala-master-resume")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )



class PredictionORM(Base):
    """Cached prediction results from the Predictor agent."""

    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), index=True)
    job_title: Mapped[str] = mapped_column(String(256))
    company: Mapped[str] = mapped_column(String(256))
    fit_score: Mapped[float] = mapped_column(Float)
    response_probability: Mapped[float] = mapped_column(Float)
    matched_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_skills: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(String(16), default="REVIEW")
    reasoning: Mapped[str] = mapped_column(Text, default="")
    predicted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


# ── Engine & Session Factory ───────────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    echo=False,          # Set True for SQL debugging
    future=True,
)

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that provides a database session.

    Automatically commits on success and rolls back on exception.

    Usage
    -----
    >>> async with get_session() as session:
    ...     result = await session.execute(select(JobPostingORM))
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """
    Create all tables if they don't exist.
    Call once at application startup.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    """Drop all tables. Use only in tests."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Repository helpers ────────────────────────────────────────────────────────

async def get_all_applications(session: AsyncSession) -> list[ApplicationORM]:
    """Return all applications ordered by last_updated desc."""
    result = await session.execute(
        select(ApplicationORM).order_by(ApplicationORM.last_updated.desc())
    )
    return list(result.scalars().all())


async def get_active_applications(session: AsyncSession) -> list[ApplicationORM]:
    """Return applications that are still in-flight."""
    terminal = {"REJECTED", "WITHDRAWN", "ACCEPTED"}
    result = await session.execute(select(ApplicationORM))
    return [a for a in result.scalars().all() if a.status not in terminal]


async def get_top_predictions(
    session: AsyncSession, limit: int = 10
) -> list[PredictionORM]:
    """Return top predictions by fit_score."""
    result = await session.execute(
        select(PredictionORM)
        .order_by(PredictionORM.fit_score.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
