"""
CareerPilot — Tracker Agent
============================
The data manager. Discovers new jobs, deduplicates them, persists to DB,
syncs LinkedIn/email profiles, and maintains application lifecycle state.

Subscribed topics: jobs, events
Publishes to:      events, predictions

Lifecycle events emitted
------------------------
  new_jobs_found        — after a successful job search batch
  application_updated   — when an application status changes
  profile_synced        — after LinkedIn/email sync completes
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from agents.base_agent import BaseAgent
from core.config import settings
from models.database import (
    ApplicationORM,
    JobPostingORM,
    get_session,
    init_db,
)
from models.schemas import (
    AgentMessage,
    Application,
    ApplicationStatus,
    JobPosting,
    MessageType,
)

logger = structlog.get_logger(__name__)


class TrackerAgent(BaseAgent):
    """
    📡 Tracker — Discovers, deduplicates, and tracks job applications.

    Responsibilities
    ----------------
    1. Execute job search tasks delegated by Commander.
    2. Deduplicate new jobs against the DB (by title + company).
    3. Persist new JobPosting records.
    4. Sync LinkedIn profile and email inbox.
    5. Manage Application lifecycle state transitions.
    6. Emit 'new_jobs_found' events so Predictor can score them.
    """

    agent_id = "tracker"
    subscribed_topics = ["jobs", "events"]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._known_job_keys: set[str] = set()   # (title.lower, company.lower)
        self._poll_task: asyncio.Task[None] | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def on_start(self) -> None:
        await init_db()
        await self._load_known_jobs()
        self._log.info("tracker.ready", known_jobs=len(self._known_job_keys))

        # Start background polling loop
        self._poll_task = asyncio.create_task(
            self._poll_loop(), name="tracker-poll-loop"
        )

    async def on_stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    # ── Background polling ─────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """
        Periodically search for new jobs without waiting for a Commander task.
        Interval is controlled by settings.tracker_poll_interval.
        """
        while self._running:
            try:
                await asyncio.sleep(settings.tracker_poll_interval)
                self._log.info("tracker.auto_poll_triggered")
                await self._run_searches(settings.target_roles, settings.target_locations)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._log.exception("tracker.poll_loop_error", error=str(exc))

    # ── Message dispatch ───────────────────────────────────────────────────────

    async def handle_message(self, message: AgentMessage) -> None:
        action = message.payload.get("action", "")

        if message.type == MessageType.TASK:
            if action == "search_jobs":
                await self._handle_search_task(message)
            elif action == "sync_profile":
                await self._handle_sync_profile(message)
            elif action == "update_application":
                await self._handle_update_application(message)
            else:
                self._log.warning("tracker.unknown_action", action=action)

        elif message.type == MessageType.EVENT:
            event_type = message.payload.get("type", "")
            if event_type == "application_updated":
                # Log and persist status change from other agents
                await self._persist_application_update(message.payload)

    # ── Job search ─────────────────────────────────────────────────────────────

    async def _handle_search_task(self, message: AgentMessage) -> None:
        """Execute a job search task from Commander."""
        params = message.payload.get("params", {})
        query = params.get("query", settings.target_roles[0])
        location = params.get("location", settings.target_locations[0])
        max_results = params.get("max_results", 25)

        self._log.info("tracker.searching", query=query, location=location)

        raw_jobs = await self.use_tool(
            "search_jobs",
            query=query,
            location=location,
            max_results=max_results,
        )

        jobs = [JobPosting(**j) for j in raw_jobs]
        new_jobs = await self._deduplicate_and_persist(jobs)

        self._log.info(
            "tracker.search_complete",
            total=len(jobs),
            new=len(new_jobs),
            query=query,
        )

        if new_jobs:
            await self.emit_event(
                topic="events",
                payload={
                    "type": "new_jobs_found",
                    "count": len(new_jobs),
                    "job_ids": [j.id for j in new_jobs],
                    "query": query,
                    "location": location,
                },
            )

        # Reply to Commander with summary
        await self.reply(
            message,
            payload={
                "action": "search_jobs",
                "total_found": len(jobs),
                "new_jobs": len(new_jobs),
                "query": query,
            },
        )

    async def _run_searches(
        self, roles: list[str], locations: list[str]
    ) -> None:
        """Run a batch of searches (used by poll loop)."""
        for role in roles:
            for loc in locations:
                try:
                    raw = await self.use_tool(
                        "search_jobs", query=role, location=loc, max_results=20
                    )
                    jobs = [JobPosting(**j) for j in raw]
                    new = await self._deduplicate_and_persist(jobs)
                    if new:
                        await self.emit_event(
                            topic="events",
                            payload={
                                "type": "new_jobs_found",
                                "count": len(new),
                                "job_ids": [j.id for j in new],
                                "query": role,
                                "location": loc,
                            },
                        )
                except Exception as exc:
                    self._log.error(
                        "tracker.search_failed", role=role, location=loc, error=str(exc)
                    )
                await asyncio.sleep(2)  # polite delay between searches

    # ── Deduplication & persistence ────────────────────────────────────────────

    def _job_key(self, job: JobPosting) -> str:
        return f"{job.title.lower().strip()}|{job.company.lower().strip()}"

    async def _deduplicate_and_persist(self, jobs: list[JobPosting]) -> list[JobPosting]:
        """
        Filter out already-known jobs and persist new ones.
        Returns the list of genuinely new jobs.
        """
        new_jobs: list[JobPosting] = []
        for job in jobs:
            key = self._job_key(job)
            if key in self._known_job_keys:
                continue
            self._known_job_keys.add(key)
            new_jobs.append(job)

        if new_jobs:
            await self._save_jobs_to_db(new_jobs)

        return new_jobs

    async def _save_jobs_to_db(self, jobs: list[JobPosting]) -> None:
        """Persist a batch of JobPosting objects to the database."""
        async with get_session() as session:
            for job in jobs:
                orm = JobPostingORM(
                    id=job.id,
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    description=job.description,
                    requirements=job.requirements,
                    salary_min=job.salary_min,
                    salary_max=job.salary_max,
                    currency=job.currency,
                    source=job.source.value,
                    source_url=job.source_url,
                    posted_at=job.posted_at,
                    discovered_at=job.discovered_at,
                    experience_level=job.experience_level.value if job.experience_level else None,
                    is_remote=job.is_remote,
                    skills_mentioned=job.skills_mentioned,
                    easy_apply=job.easy_apply,
                )
                session.add(orm)
        self._log.info("tracker.jobs_persisted", count=len(jobs))

    async def _load_known_jobs(self) -> None:
        """Pre-populate the dedup set from the database on startup."""
        try:
            from sqlalchemy import select
            async with get_session() as session:
                result = await session.execute(
                    select(JobPostingORM.title, JobPostingORM.company)
                )
                for row in result.all():
                    key = f"{row.title.lower()}|{row.company.lower()}"
                    self._known_job_keys.add(key)
        except Exception as exc:
            self._log.warning("tracker.load_known_jobs_failed", error=str(exc))

    # ── Profile sync ───────────────────────────────────────────────────────────

    async def _handle_sync_profile(self, message: AgentMessage) -> None:
        """Sync LinkedIn profile and email inbox data."""
        self._log.info("tracker.syncing_profile")

        profile_data = await self.use_tool("get_linkedin_profile")
        emails = await self.use_tool(
            "search_emails",
            query="job OR recruiter OR interview OR offer",
            max_results=30,
        )

        # Count recruiter emails by classification
        recruiter_emails = [e for e in emails if e.get("classification") != "OTHER"]
        interview_invites = [e for e in emails if e.get("classification") == "INTERVIEW"]

        # Persist profile to long-term memory
        self.persist("linkedin_profile", profile_data, tags=["profile", "linkedin"])
        self.persist("email_summary", {
            "total_emails": len(emails),
            "recruiter_emails": len(recruiter_emails),
            "interview_invites": len(interview_invites),
        }, tags=["profile", "email"])

        await self.emit_event(
            topic="events",
            payload={
                "type": "profile_synced",
                "linkedin_synced": True,
                "recruiter_emails": len(recruiter_emails),
                "interview_invites": len(interview_invites),
            },
        )

        await self.reply(
            message,
            payload={
                "action": "sync_profile",
                "linkedin_synced": not profile_data.get("is_mock", False),
                "recruiter_emails": len(recruiter_emails),
                "interview_invites": len(interview_invites),
            },
        )

    # ── Application state management ───────────────────────────────────────────

    async def _handle_update_application(self, message: AgentMessage) -> None:
        """Update an application's status in the database."""
        params = message.payload.get("params", {})
        app_id = params.get("application_id")
        new_status = params.get("status")

        if not app_id or not new_status:
            self._log.warning("tracker.update_app_missing_params", params=params)
            return

        try:
            from sqlalchemy import select
            async with get_session() as session:
                result = await session.execute(
                    select(ApplicationORM).where(ApplicationORM.id == app_id)
                )
                app = result.scalar_one_or_none()
                if app:
                    old_status = app.status
                    app.status = new_status
                    app.last_updated = datetime.now(timezone.utc)
                    self._log.info(
                        "tracker.application_updated",
                        app_id=app_id,
                        old_status=old_status,
                        new_status=new_status,
                    )
        except Exception as exc:
            self._log.error("tracker.update_app_failed", error=str(exc))

    async def _persist_application_update(self, payload: dict[str, Any]) -> None:
        """Handle an application_updated event from another source."""
        self._log.debug("tracker.application_event_received", payload=payload)

    # ── Public API ─────────────────────────────────────────────────────────────

    async def create_application(self, job: JobPosting) -> Application:
        """
        Create a new Application record for a job.
        Callable directly from CLI or other agents.
        """
        app = Application(
            job_id=job.id,
            job_title=job.title,
            company=job.company,
            status=ApplicationStatus.APPLIED,
            applied_at=datetime.now(timezone.utc),
        )
        async with get_session() as session:
            orm = ApplicationORM(
                id=app.id,
                job_id=app.job_id,
                job_title=app.job_title,
                company=app.company,
                status=app.status.value,
                applied_at=app.applied_at,
                last_updated=app.last_updated,
            )
            session.add(orm)

        self._log.info("tracker.application_created", job=job.title, company=job.company)
        return app

    def status(self) -> dict[str, Any]:
        """Return tracker status snapshot."""
        return {
            "agent_id": self.agent_id,
            "running": self._running,
            "known_jobs": len(self._known_job_keys),
            "poll_interval_secs": settings.tracker_poll_interval,
            "linkedin_profile": bool(self.retrieve("linkedin_profile")),
            "email_summary": self.retrieve("email_summary"),
        }
