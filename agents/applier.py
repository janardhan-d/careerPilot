"""
CareerPilot — ApplierAgent
===========================
Automated Job & Internship Application Agent.

Features:
  - Profile Management: Stores user skills, experience, target roles, and internship preferences.
  - 1-Click Fast Application Engine: Generates tailored cover letters/cold emails for any job/internship.
  - Automatic Application Pipeline Tracking: Records application submission state and timeline.
  - Real-time Event Broadcast: Notifies UI of application progress via MessageBus.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select

from agents.base_agent import BaseAgent
from models.database import ApplicationORM, JobPostingORM, PredictionORM, UserProfileORM, get_session
from models.schemas import AgentMessage, MessagePriority, MessageType

logger = structlog.get_logger(__name__)


class ApplierAgent(BaseAgent):
    """
    ApplierAgent — Fast automated job & internship application agent.
    """

    agent_id: str = "applier"
    subscribed_topics: list[str] = ["commands", "events", "jobs", "predictions", "profiles"]


    async def on_start(self) -> None:
        """Initialize profile in DB if not existing."""
        async with get_session() as session:
            result = await session.execute(select(UserProfileORM).where(UserProfileORM.id == "default"))
            profile = result.scalar_one_or_none()
            if not profile:
                profile = UserProfileORM(id="default")
                session.add(profile)
                await session.commit()
                logger.info("applier.profile_initialized")

    async def handle_message(self, message: AgentMessage) -> None:
        """Handle incoming message bus events."""
        if message.msg_type == MessageType.GOAL_SUBMITTED:
            logger.info("applier.goal_received", goal=message.payload.get("goal"))

    async def get_profile(self) -> dict[str, Any]:
        """Fetch the default user profile."""
        async with get_session() as session:
            result = await session.execute(select(UserProfileORM).where(UserProfileORM.id == "default"))
            profile = result.scalar_one_or_none()
            if not profile:
                profile = UserProfileORM(id="default")
                session.add(profile)
                await session.commit()
            return {
                "id": profile.id,
                "full_name": profile.full_name,
                "email": profile.email,
                "phone": profile.phone,
                "location": profile.location,
                "target_roles": profile.target_roles or [],
                "skills": profile.skills or [],
                "experience_level": profile.experience_level,
                "prefer_internships": profile.prefer_internships,
                "bio": profile.bio,
                "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
            }

    async def update_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        """Update user profile skills, details, and preferences."""
        async with get_session() as session:
            result = await session.execute(select(UserProfileORM).where(UserProfileORM.id == "default"))
            profile = result.scalar_one_or_none()
            if not profile:
                profile = UserProfileORM(id="default")
                session.add(profile)

            if "full_name" in data:
                profile.full_name = data["full_name"]
            if "email" in data:
                profile.email = data["email"]
            if "phone" in data:
                profile.phone = data["phone"]
            if "location" in data:
                profile.location = data["location"]
            if "skills" in data and isinstance(data["skills"], list):
                profile.skills = data["skills"]
            if "target_roles" in data and isinstance(data["target_roles"], list):
                profile.target_roles = data["target_roles"]
            if "experience_level" in data:
                profile.experience_level = data["experience_level"]
            if "prefer_internships" in data:
                profile.prefer_internships = bool(data["prefer_internships"])
            if "bio" in data:
                profile.bio = data["bio"]

            profile.updated_at = datetime.now(timezone.utc)
            await session.commit()

            return await self.get_profile()

    async def apply_to_job(self, job_id: str, custom_notes: str = "") -> dict[str, Any]:
        """
        Fast 1-Click Application Agent processing.
        1. Reads job posting + prediction fit score.
        2. Reads user profile.
        3. Generates tailored cover letter & application notes.
        4. Saves/updates Application record in DB.
        """
        async with get_session() as session:
            # 1. Fetch Job
            job_res = await session.execute(select(JobPostingORM).where(JobPostingORM.id == job_id))
            job = job_res.scalar_one_or_none()
            if not job:
                raise ValueError(f"Job with ID {job_id} not found")

            # 2. Fetch Prediction fit score if available
            pred_res = await session.execute(select(PredictionORM).where(PredictionORM.job_id == job_id))
            pred = pred_res.scalar_one_or_none()
            fit_score = pred.fit_score if pred else 85.0

            # 3. Fetch User Profile
            prof_res = await session.execute(select(UserProfileORM).where(UserProfileORM.id == "default"))
            user_profile = prof_res.scalar_one_or_none()
            candidate_name = user_profile.full_name if user_profile else "Applicant Candidate"
            user_skills = ", ".join((user_profile.skills if user_profile else ["Python", "Machine Learning"])[:6])

            # 4. Generate Tailored Cover Letter
            is_intern = job.is_internship or ("intern" in job.title.lower())
            role_type = "Internship" if is_intern else "Position"

            cover_letter = (
                f"Dear Hiring Manager at {job.company},\n\n"
                f"I am writing to express my enthusiastic interest in the {job.title} {role_type}. "
                f"With a strong background in {user_skills}, I bring proven technical proficiency and a problem-solving mindset tailored to {job.company}'s goals.\n\n"
                f"My key technical strengths include:\n"
                f"• High hands-on experience in {user_skills}\n"
                f"• Demonstrated capability building end-to-end software & AI solutions\n"
                f"• Strong focus on clean code, scalability, and fast execution\n\n"
                f"I would welcome the opportunity to discuss how my skillset aligns with the {job.title} role. "
                f"Thank you for your time and consideration.\n\n"
                f"Sincerely,\n{candidate_name}\n"
                f"{user_profile.email if user_profile else ''} | {user_profile.phone if user_profile else ''}"
            )

            # 5. Check existing application or create new
            app_res = await session.execute(select(ApplicationORM).where(ApplicationORM.job_id == job_id))
            existing_app = app_res.scalar_one_or_none()

            now = datetime.now(timezone.utc)
            if existing_app:
                existing_app.status = "APPLIED"
                existing_app.applied_at = now
                existing_app.last_updated = now
                existing_app.fit_score = fit_score
                existing_app.cover_letter = cover_letter
                existing_app.notes = custom_notes or "Auto-Applied via CareerPilot 1-Click Fast Applier"
                app_entry = existing_app
            else:
                app_entry = ApplicationORM(
                    id=str(uuid.uuid4()),
                    job_id=job.id,
                    job_title=job.title,
                    company=job.company,
                    status="APPLIED",
                    applied_at=now,
                    last_updated=now,
                    fit_score=fit_score,
                    notes=custom_notes or "Auto-Applied via CareerPilot 1-Click Fast Applier",
                    cover_letter=cover_letter,
                    cover_letter_sent=True,
                )
                session.add(app_entry)

            await session.commit()

            # 6. Publish event on MessageBus
            await self._bus.publish(
                topic="application.submitted",
                message=AgentMessage(
                    sender=self.agent_id,
                    msg_type=MessageType.EVENT,
                    payload={
                        "application_id": app_entry.id,
                        "job_title": job.title,
                        "company": job.company,
                        "status": "APPLIED",
                        "fit_score": fit_score,
                    },
                    priority=MessagePriority.HIGH,
                ),
            )

            return {
                "id": app_entry.id,
                "job_id": job.id,
                "job_title": job.title,
                "company": job.company,
                "status": "APPLIED",
                "fit_score": fit_score,
                "cover_letter": cover_letter,
                "applied_at": now.isoformat(),
            }

    def status(self) -> dict[str, Any]:
        """Return operational status."""
        return {
            "agent_id": self.agent_id,
            "running": self._running,
            "auto_apply_mode": "1-CLICK_FAST",
        }
