"""
CareerPilot — Predictor Agent
==============================
The intelligence layer. Scores every tracked job for fit, predicts
response probability, ranks recommendations, and generates weekly reports.

Subscribed topics: predictions, events
Publishes to:      events

Scoring model
-------------
  fit_score (0–100)
    = 60%  skill overlap  (resume ↔ JD keyword match via TF-IDF)
    + 25%  title match    (fuzzy role similarity)
    + 15%  location match (remote bonus, location preference)

  response_probability (0–1)
    = heuristic model:  easy_apply, company_size_tier, fit_score bucket
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from agents.base_agent import BaseAgent
from core.config import settings
from models.database import (
    JobPostingORM,
    PredictionORM,
    get_session,
    get_top_predictions,
)
from models.schemas import (
    AgentMessage,
    MessageType,
    PredictionResult,
    WeeklyReport,
)

logger = structlog.get_logger(__name__)


# ── Heuristic constants ────────────────────────────────────────────────────────

# Approximate response probability by fit_score bucket
RESPONSE_PROB_TABLE = {
    (90, 101): 0.55,
    (75, 90):  0.40,
    (60, 75):  0.25,
    (45, 60):  0.15,
    (0,  45):  0.07,
}

# Bonus for easy-apply (LinkedIn one-click)
EASY_APPLY_BONUS = 0.10

# Titles that strongly suggest seniority mismatch
SENIORITY_OVERQUALIFIED = {"intern", "junior", "entry", "fresher", "graduate"}
SENIORITY_UNDERQUALIFIED = {"director", "vp", "head of", "chief"}

# Companies known for high response rates (heuristic tier)
HIGH_RESPONSE_TIER = {
    "google", "microsoft", "amazon", "meta", "apple",
    "flipkart", "swiggy", "razorpay", "meesho", "zepto",
}


class PredictorAgent(BaseAgent):
    """
    🔮 Predictor — Scores jobs, predicts outcomes, generates reports.

    Responsibilities
    ----------------
    1. Score pending (un-predicted) jobs for fit against the user's profile.
    2. Predict response probability using a heuristic model.
    3. Rank and recommend top jobs.
    4. Generate weekly trend reports on demand.
    5. Flag skill gaps so the user knows what to learn.
    """

    agent_id = "predictor"
    subscribed_topics = ["predictions", "events"]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._user_skills: list[str] = []
        self._user_profile: dict[str, Any] = {}
        self._scored_job_ids: set[str] = set()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def on_start(self) -> None:
        await self._load_user_profile()
        await self._load_scored_ids()
        self._log.info(
            "predictor.ready",
            known_skills=len(self._user_skills),
            already_scored=len(self._scored_job_ids),
        )

    async def _load_user_profile(self) -> None:
        """Load cached LinkedIn profile from long-term memory."""
        profile = self.retrieve("linkedin_profile")
        if profile:
            raw_skills = profile.get("skills", [])
            self._user_skills = [
                s["name"].lower() if isinstance(s, dict) else str(s).lower()
                for s in raw_skills
            ]
            self._user_profile = profile
        else:
            # Sensible defaults when profile not yet synced
            self._user_skills = [
                "python", "pytorch", "fastapi", "mlops", "langchain",
                "sql", "docker", "git",
            ]

    async def _load_scored_ids(self) -> None:
        """Load IDs of already-scored jobs to avoid re-scoring."""
        try:
            from sqlalchemy import select
            async with get_session() as session:
                result = await session.execute(select(PredictionORM.job_id))
                self._scored_job_ids = {row[0] for row in result.all()}
        except Exception as exc:
            self._log.warning("predictor.load_scored_ids_failed", error=str(exc))

    # ── Message dispatch ───────────────────────────────────────────────────────

    async def handle_message(self, message: AgentMessage) -> None:
        action = message.payload.get("action", "")

        if message.type == MessageType.TASK:
            if action == "score_all_pending":
                await self._handle_score_all(message)
            elif action == "score_job":
                await self._handle_score_single(message)
            elif action == "generate_report":
                await self._handle_generate_report(message)
            else:
                self._log.warning("predictor.unknown_action", action=action)

        elif message.type == MessageType.EVENT:
            event_type = message.payload.get("type", "")
            if event_type == "new_jobs_found":
                # Auto-score whenever Tracker finds new jobs
                await self._score_pending_jobs()
            elif event_type == "profile_synced":
                # Reload skills after profile sync
                await self._load_user_profile()

    # ── Score all pending ──────────────────────────────────────────────────────

    async def _handle_score_all(self, message: AgentMessage) -> None:
        """Score all jobs that haven't been scored yet."""
        results = await self._score_pending_jobs()
        await self.reply(
            message,
            payload={
                "action": "score_all_pending",
                "scored": len(results),
                "top_job": results[0].job_title if results else None,
                "top_score": results[0].fit_score if results else None,
            },
        )

    async def _score_pending_jobs(self) -> list[PredictionResult]:
        """Fetch un-scored jobs from DB, score them, persist predictions."""
        from sqlalchemy import select

        try:
            async with get_session() as session:
                result = await session.execute(select(JobPostingORM))
                all_jobs = result.scalars().all()
        except Exception as exc:
            self._log.error("predictor.db_fetch_failed", error=str(exc))
            return []

        pending = [j for j in all_jobs if j.id not in self._scored_job_ids]
        self._log.info("predictor.scoring_pending", count=len(pending))

        predictions: list[PredictionResult] = []
        for job_orm in pending:
            pred = await self._score_job_orm(job_orm)
            predictions.append(pred)
            await asyncio.sleep(0)  # yield to event loop

        if predictions:
            await self._persist_predictions(predictions)
            top = sorted(predictions, key=lambda p: p.fit_score, reverse=True)[:5]
            await self.emit_event(
                topic="events",
                payload={
                    "type": "predictions_ready",
                    "scored": len(predictions),
                    "top_recommendations": [
                        {
                            "job_title": p.job_title,
                            "company": p.company,
                            "fit_score": p.fit_score,
                            "recommendation": p.recommendation,
                        }
                        for p in top
                    ],
                },
            )

        return sorted(predictions, key=lambda p: p.fit_score, reverse=True)

    # ── Single job scoring ─────────────────────────────────────────────────────

    async def _handle_score_single(self, message: AgentMessage) -> None:
        """Score a single job passed in the payload."""
        params = message.payload.get("params", {})
        job_id = params.get("job_id")
        job_description = params.get("description", "")
        job_title = params.get("title", "")
        company = params.get("company", "")

        if not job_id:
            await self.reply(message, payload={"error": "job_id is required"})
            return

        pred = self._compute_score(
            job_id=job_id,
            job_title=job_title,
            company=company,
            description=job_description,
            skills_mentioned=params.get("skills_mentioned", []),
            is_remote=params.get("is_remote", False),
            easy_apply=params.get("easy_apply", False),
        )
        await self.reply(message, payload=pred.model_dump(mode="json"))

    # ── Scoring logic ──────────────────────────────────────────────────────────

    async def _score_job_orm(self, job: JobPostingORM) -> PredictionResult:
        """Score a single JobPostingORM record."""
        return self._compute_score(
            job_id=job.id,
            job_title=job.title,
            company=job.company,
            description=job.description or "",
            skills_mentioned=job.skills_mentioned or [],
            is_remote=job.is_remote,
            easy_apply=job.easy_apply,
        )

    def _compute_score(
        self,
        job_id: str,
        job_title: str,
        company: str,
        description: str,
        skills_mentioned: list[str],
        is_remote: bool,
        easy_apply: bool,
    ) -> PredictionResult:
        """
        Core scoring function — fully offline, no LLM required.

        Returns a PredictionResult with fit_score, response_probability,
        matched/missing skills, and a recommendation string.
        """
        # ── 1. Skill overlap (60 pts) ─────────────────────────────────────────
        jd_text = (description + " " + " ".join(skills_mentioned)).lower()
        jd_skills = {
            s for s in self._user_skills
            if s in jd_text
        }
        # Also use explicitly listed skills
        jd_skill_set = {s.lower() for s in skills_mentioned}
        matched = sorted(set(self._user_skills) & (jd_skills | jd_skill_set))
        all_jd_skills = jd_skills | jd_skill_set
        missing = sorted(all_jd_skills - set(self._user_skills))

        skill_score = 0.0
        if all_jd_skills:
            skill_score = (len(matched) / len(all_jd_skills)) * 60

        # ── 2. Title match (25 pts) ───────────────────────────────────────────
        title_score = self._title_match_score(job_title) * 25

        # ── 3. Location match (15 pts) ────────────────────────────────────────
        location_score = 15.0 if is_remote else 8.0

        fit_score = round(min(skill_score + title_score + location_score, 100.0), 2)

        # ── Response probability ──────────────────────────────────────────────
        base_prob = 0.07
        for (low, high), prob in RESPONSE_PROB_TABLE.items():
            if low <= fit_score < high:
                base_prob = prob
                break

        if easy_apply:
            base_prob = min(base_prob + EASY_APPLY_BONUS, 0.80)
        if company.lower() in HIGH_RESPONSE_TIER:
            base_prob = min(base_prob + 0.05, 0.80)

        response_prob = round(base_prob, 3)

        # ── Recommendation ────────────────────────────────────────────────────
        if fit_score >= settings.min_fit_score:
            recommendation = "APPLY"
            reasoning = (
                f"Strong fit ({fit_score:.0f}/100). "
                f"Matched skills: {', '.join(matched[:5]) or 'general overlap'}. "
                f"Estimated response probability: {response_prob:.0%}."
            )
        elif fit_score >= 45:
            recommendation = "REVIEW"
            reasoning = (
                f"Moderate fit ({fit_score:.0f}/100). "
                f"Missing key skills: {', '.join(missing[:3])}. "
                "Consider applying if you can highlight transferable experience."
            )
        else:
            recommendation = "SKIP"
            reasoning = (
                f"Low fit ({fit_score:.0f}/100). "
                f"Significant skill gaps: {', '.join(missing[:5])}. "
                "Skipping to prioritise better-matched opportunities."
            )

        self._scored_job_ids.add(job_id)

        return PredictionResult(
            job_id=job_id,
            job_title=job_title,
            company=company,
            fit_score=fit_score,
            response_probability=response_prob,
            matched_skills=matched[:10],
            missing_skills=missing[:10],
            recommendation=recommendation,
            reasoning=reasoning,
        )

    def _title_match_score(self, title: str) -> float:
        """
        Score 0.0–1.0 based on title similarity to target roles.
        Uses simple token overlap — no fuzzy lib required.
        """
        title_tokens = set(title.lower().split())
        best = 0.0
        for target_role in settings.target_roles:
            role_tokens = set(target_role.lower().split())
            if not role_tokens:
                continue
            overlap = len(title_tokens & role_tokens) / len(role_tokens)
            best = max(best, overlap)
        return best

    # ── Persistence ────────────────────────────────────────────────────────────

    async def _persist_predictions(self, predictions: list[PredictionResult]) -> None:
        """Save prediction results to the database."""
        async with get_session() as session:
            for pred in predictions:
                orm = PredictionORM(
                    id=str(uuid.uuid4()),
                    job_id=pred.job_id,
                    job_title=pred.job_title,
                    company=pred.company,
                    fit_score=pred.fit_score,
                    response_probability=pred.response_probability,
                    matched_skills=pred.matched_skills,
                    missing_skills=pred.missing_skills,
                    recommendation=pred.recommendation,
                    reasoning=pred.reasoning,
                    predicted_at=pred.predicted_at,
                )
                session.add(orm)
        self._log.info("predictor.predictions_persisted", count=len(predictions))

    # ── Weekly report ──────────────────────────────────────────────────────────

    async def _handle_generate_report(self, message: AgentMessage) -> None:
        """Generate and emit a WeeklyReport."""
        report = await self._build_weekly_report()
        await self.emit_event(
            topic="events",
            payload={"type": "weekly_report_ready", "report": report.model_dump(mode="json")},
        )
        await self.reply(
            message,
            payload={"action": "generate_report", "report": report.model_dump(mode="json")},
        )

    async def _build_weekly_report(self) -> WeeklyReport:
        """Aggregate DB data into a WeeklyReport."""
        from sqlalchemy import func, select
        from models.database import ApplicationORM

        total_jobs = 0
        total_apps = 0
        active_apps = 0
        avg_score = 0.0
        top_preds: list[PredictionResult] = []
        trending_skills: list[str] = []
        insights: list[str] = []

        try:
            async with get_session() as session:
                # Job count
                j_count = await session.execute(select(func.count()).select_from(JobPostingORM))
                total_jobs = j_count.scalar_one()

                # Application counts
                a_count = await session.execute(select(func.count()).select_from(ApplicationORM))
                total_apps = a_count.scalar_one()

                terminal = {"REJECTED", "WITHDRAWN", "ACCEPTED"}
                a_result = await session.execute(select(ApplicationORM))
                apps = a_result.scalars().all()
                active_apps = sum(1 for a in apps if a.status not in terminal)

                # Top predictions
                top_orm = await get_top_predictions(session, limit=5)
                top_preds = [
                    PredictionResult(
                        job_id=p.job_id,
                        job_title=p.job_title,
                        company=p.company,
                        fit_score=p.fit_score,
                        response_probability=p.response_probability,
                        matched_skills=p.matched_skills,
                        missing_skills=p.missing_skills,
                        recommendation=p.recommendation,
                        reasoning=p.reasoning,
                    )
                    for p in top_orm
                ]

                # Average fit score
                avg_result = await session.execute(
                    select(func.avg(PredictionORM.fit_score))
                )
                avg_score = round(avg_result.scalar_one() or 0.0, 1)

                # Trending missing skills (most common gaps)
                all_preds_result = await session.execute(select(PredictionORM.missing_skills))
                skill_counter: dict[str, int] = {}
                for row in all_preds_result.all():
                    for skill in (row[0] or []):
                        skill_counter[skill] = skill_counter.get(skill, 0) + 1
                trending_skills = sorted(skill_counter, key=lambda s: -skill_counter[s])[:5]

        except Exception as exc:
            self._log.error("predictor.report_build_failed", error=str(exc))

        # Generate insights
        if avg_score >= 70:
            insights.append(f"Strong pipeline — avg fit score {avg_score}/100. Keep applying!")
        elif avg_score >= 50:
            insights.append(f"Moderate pipeline (avg {avg_score}/100). Target roles more precisely.")
        else:
            insights.append(f"Low avg fit ({avg_score}/100). Consider upskilling in: {', '.join(trending_skills[:3])}.")

        if active_apps > 5:
            insights.append(f"{active_apps} active applications in flight — follow up on those over 7 days old.")

        if trending_skills:
            insights.append(f"Most common skill gaps in your target roles: {', '.join(trending_skills)}.")

        return WeeklyReport(
            total_jobs_tracked=total_jobs,
            total_applications=total_apps,
            active_applications=active_apps,
            top_recommendations=top_preds,
            trending_skills=trending_skills,
            avg_fit_score=avg_score,
            insights=insights,
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    async def get_top_recommendations(self, n: int = 10) -> list[PredictionResult]:
        """Return top-N recommendations from the database."""
        async with get_session() as session:
            top = await get_top_predictions(session, limit=n)
            return [
                PredictionResult(
                    job_id=p.job_id,
                    job_title=p.job_title,
                    company=p.company,
                    fit_score=p.fit_score,
                    response_probability=p.response_probability,
                    matched_skills=p.matched_skills,
                    missing_skills=p.missing_skills,
                    recommendation=p.recommendation,
                    reasoning=p.reasoning,
                )
                for p in top
            ]

    def status(self) -> dict[str, Any]:
        """Return predictor status snapshot."""
        return {
            "agent_id": self.agent_id,
            "running": self._running,
            "user_skills": len(self._user_skills),
            "scored_jobs": len(self._scored_job_ids),
            "target_roles": settings.target_roles,
            "min_fit_score": settings.min_fit_score,
        }
