"""
CareerPilot — Test Configuration
==================================
Shared fixtures for the entire test suite.

Design
------
- Each test gets its own fresh SQLite DB file (via tmp_path).
- The SQLAlchemy engine + session factory on the `models.database` module
  are patched in-place so all code paths see the test DB automatically.
- The global MessageBus singleton is reset between tests.
- Agent fixtures start / stop cleanly around each test.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio


# ── Event loop (session-scoped) ───────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Isolated test database ────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def test_db(tmp_path):
    """
    Give every test its own SQLite DB.

    Patches `models.database.engine` and `models.database.AsyncSessionFactory`
    in-place so all imports see the test engine — including those that
    captured a reference at module import time.
    """
    import os
    import models.database as db_mod
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    # Unique DB file per test (tmp_path is per-test)
    db_file = tmp_path / f"test_{uuid.uuid4().hex}.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    os.environ["DATABASE_URL"] = db_url

    # Clear the settings cache so config picks up the new URL
    from core.config import get_settings
    get_settings.cache_clear()

    # Patch the module-level engine + session factory
    old_engine = db_mod.engine
    old_factory = db_mod.AsyncSessionFactory

    test_engine = create_async_engine(db_url, future=True)
    test_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    db_mod.engine = test_engine
    db_mod.AsyncSessionFactory = test_factory

    # Create schema
    from models.database import Base
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Tear down
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()

    # Restore originals (keeps module state clean between tests)
    db_mod.engine = old_engine
    db_mod.AsyncSessionFactory = old_factory


# ── Reset global bus singleton ────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def reset_bus():
    """Reset the global MessageBus singleton between tests."""
    import core.message_bus as bus_mod
    bus_mod._bus = None
    yield
    if bus_mod._bus is not None:
        await bus_mod._bus.stop()
    bus_mod._bus = None


# ── Message bus fixture ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def bus() -> AsyncGenerator[object, None]:
    """Provide a started MessageBus for each test."""
    from core.message_bus import MessageBus
    b = MessageBus()
    await b.start()
    yield b
    await b.stop()


# ── Agent fixtures ────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def commander(bus):
    from agents.commander import CommanderAgent
    agent = CommanderAgent(bus=bus)
    await agent.start()
    yield agent
    await agent.stop()


@pytest_asyncio.fixture
async def tracker(bus):
    from agents.tracker import TrackerAgent
    agent = TrackerAgent(bus=bus)
    await agent.start()
    yield agent
    await agent.stop()


@pytest_asyncio.fixture
async def predictor(bus):
    from agents.predictor import PredictorAgent
    agent = PredictorAgent(bus=bus)
    await agent.start()
    yield agent
    await agent.stop()


# ── Sample data fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_job():
    """A realistic ML Engineer job posting."""
    from models.schemas import JobPosting, JobSource
    return JobPosting(
        title="Machine Learning Engineer",
        company="Acme Corp",
        location="Remote",
        description="We need Python, PyTorch, MLOps, Docker, SQL experience.",
        skills_mentioned=["python", "pytorch", "mlops", "docker", "sql"],
        source=JobSource.LINKEDIN,
        source_url="https://linkedin.com/jobs/view/123456",
        is_remote=True,
        easy_apply=True,
    )


@pytest.fixture
def sample_jobs(sample_job):
    """Two distinct job postings for deduplication tests."""
    from models.schemas import JobPosting, JobSource
    return [
        sample_job,
        JobPosting(
            title="Data Scientist",
            company="Beta Inc",
            location="Bangalore",
            description="R, Python, sklearn, statistics, SQL, Spark",
            skills_mentioned=["python", "sklearn", "sql", "spark"],
            source=JobSource.INDEED,
            source_url="https://indeed.com/viewjob?jk=abc123",
            is_remote=False,
        ),
    ]
