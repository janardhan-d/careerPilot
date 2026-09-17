"""
CareerPilot — Pydantic Schemas
================================
All shared data models used across agents, tools, and the message bus.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class ApplicationStatus(str, Enum):
    """Lifecycle stages of a job application."""
    DISCOVERED = "DISCOVERED"
    BOOKMARKED = "BOOKMARKED"
    APPLIED = "APPLIED"
    OA_RECEIVED = "OA_RECEIVED"          # Online assessment
    PHONE_SCREEN = "PHONE_SCREEN"
    INTERVIEWING = "INTERVIEWING"
    OFFER = "OFFER"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class MessageType(str, Enum):
    """Typed message envelope kinds on the bus."""
    TASK = "TASK"           # Commander → Agent: do this work
    RESULT = "RESULT"       # Agent → Commander: here's the output
    EVENT = "EVENT"         # Agent → All: something happened
    QUERY = "QUERY"         # Agent → Agent: I need data
    ERROR = "ERROR"         # Agent → Commander: something failed


class MessagePriority(str, Enum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class JobSource(str, Enum):
    LINKEDIN = "LINKEDIN"
    INDEED = "INDEED"
    GLASSDOOR = "GLASSDOOR"
    NAUKRI = "NAUKRI"
    MANUAL = "MANUAL"


class ExperienceLevel(str, Enum):
    ENTRY = "ENTRY"
    MID = "MID"
    SENIOR = "SENIOR"
    LEAD = "LEAD"
    PRINCIPAL = "PRINCIPAL"
    DIRECTOR = "DIRECTOR"


# ── Core Domain Models ─────────────────────────────────────────────────────────

class JobPosting(BaseModel):
    """A single job posting discovered from any source."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    company: str
    location: str
    description: str = Field(default="")
    requirements: list[str] = Field(default_factory=list)
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str = Field(default="INR")
    source: JobSource = JobSource.LINKEDIN
    source_url: str = Field(default="")
    posted_at: datetime | None = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    experience_level: ExperienceLevel | None = None
    is_remote: bool = False
    skills_mentioned: list[str] = Field(default_factory=list)
    easy_apply: bool = False

    @field_validator("title", "company", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()

    def summary(self) -> str:
        """One-line human-readable summary."""
        remote = " [Remote]" if self.is_remote else ""
        return f"{self.title} @ {self.company} | {self.location}{remote}"


class Application(BaseModel):
    """Tracks a user's application to a specific job."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    job_title: str
    company: str
    status: ApplicationStatus = ApplicationStatus.DISCOVERED
    applied_at: datetime | None = None
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fit_score: float | None = Field(default=None, ge=0.0, le=100.0)
    notes: str = Field(default="")
    resume_version: str = Field(default="default")
    cover_letter_sent: bool = False
    follow_up_sent: bool = False
    interview_dates: list[datetime] = Field(default_factory=list)
    offer_amount: float | None = None
    rejection_reason: str | None = None

    def is_active(self) -> bool:
        """Return True if the application is still in-flight."""
        return self.status not in {
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
            ApplicationStatus.ACCEPTED,
        }


class UserProfile(BaseModel):
    """Aggregated user profile from LinkedIn + resume."""

    name: str
    email: str
    phone: str = Field(default="")
    linkedin_url: str = Field(default="")
    location: str = Field(default="")
    headline: str = Field(default="")
    summary: str = Field(default="")
    skills: list[str] = Field(default_factory=list)
    experience_years: float = Field(default=0.0, ge=0.0)
    education: list[dict[str, str]] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    github_url: str = Field(default="")
    portfolio_url: str = Field(default="")
    resume_path: str = Field(default="")
    last_synced: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PredictionResult(BaseModel):
    """Fit score + recommendation from the Predictor agent."""

    job_id: str
    job_title: str
    company: str
    fit_score: float = Field(ge=0.0, le=100.0)
    response_probability: float = Field(ge=0.0, le=1.0)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    recommendation: str = Field(default="")  # "APPLY" | "SKIP" | "REVIEW"
    reasoning: str = Field(default="")
    predicted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def should_apply(self) -> bool:
        return self.recommendation == "APPLY"


class WeeklyReport(BaseModel):
    """Summary report generated by the Predictor."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_jobs_tracked: int = 0
    total_applications: int = 0
    active_applications: int = 0
    interviews_this_week: int = 0
    offers_received: int = 0
    top_recommendations: list[PredictionResult] = Field(default_factory=list)
    trending_skills: list[str] = Field(default_factory=list)
    avg_fit_score: float = 0.0
    insights: list[str] = Field(default_factory=list)


# ── Message Bus Envelope ──────────────────────────────────────────────────────

class AgentMessage(BaseModel):
    """
    Typed message envelope for the inter-agent message bus.

    Every message flowing through the bus must be wrapped in this model.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str | None = Field(
        default=None,
        description="Set to the request message ID for reply tracking",
    )
    sender: str                          # agent_id of the sender
    recipient: str | None = None         # None = broadcast to all topic subscribers
    topic: str                           # bus topic ("jobs", "commands", etc.)
    type: MessageType
    priority: MessagePriority = MessagePriority.NORMAL
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None             # Populated on MessageType.ERROR

    def reply(
        self,
        sender: str,
        payload: dict[str, Any],
        msg_type: MessageType = MessageType.RESULT,
    ) -> "AgentMessage":
        """Create a reply message correlated to this one."""
        return AgentMessage(
            correlation_id=self.id,
            sender=sender,
            recipient=self.sender,
            topic=self.topic,
            type=msg_type,
            payload=payload,
        )


# ── Tool Input Schemas ────────────────────────────────────────────────────────

class JobSearchInput(BaseModel):
    """Input schema for job_board_tool.search_jobs."""
    query: str
    location: str = "Remote"
    max_results: int = Field(default=25, ge=1, le=100)
    source: JobSource = JobSource.LINKEDIN


class ResumeAnalysisInput(BaseModel):
    """Input schema for resume_tool.analyze_resume."""
    resume_path: str
    job_description: str


class EmailSearchInput(BaseModel):
    """Input schema for email_tool.search_emails."""
    query: str
    max_results: int = Field(default=20, ge=1, le=100)


class GoalInput(BaseModel):
    """High-level goal passed to the Commander."""
    goal: str = Field(description="Plain-language goal, e.g. 'Apply to 10 ML jobs this week'")
    context: dict[str, Any] = Field(default_factory=dict)
