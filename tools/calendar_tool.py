"""
CareerPilot — Calendar Tool
============================
Google Calendar API stub for scheduling interview events.
Creates calendar events, sends invites, and lists upcoming interviews.

Registered tools:
  - create_interview_event  → add interview to Google Calendar
  - list_upcoming_interviews → fetch upcoming interview events
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from core.config import settings
from core.tool_registry import registry

logger = structlog.get_logger(__name__)

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


# ── Calendar service factory ──────────────────────────────────────────────────

def _build_calendar_service() -> Any:
    """Build authenticated Google Calendar service. Returns None if unavailable."""
    creds_path = settings.gmail_credentials_path   # reuses same credentials
    token_path = settings.gmail_token_path.replace("token.json", "calendar_token.json")

    if not os.path.exists(creds_path):
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, CALENDAR_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, CALENDAR_SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        return build("calendar", "v3", credentials=creds)

    except Exception as exc:
        logger.error("calendar_tool.auth_failed", error=str(exc))
        return None


# ── Registered Tools ──────────────────────────────────────────────────────────

@registry.tool(
    name="create_interview_event",
    description="Create a Google Calendar event for a job interview.",
    tags=["calendar", "interview"],
)
async def create_interview_event(
    company: str,
    role: str,
    start_datetime: str,   # ISO 8601, e.g. "2024-09-20T14:00:00+05:30"
    duration_minutes: int = 60,
    location: str = "Video Call",
    description: str = "",
    attendee_email: str = "",
) -> dict[str, Any]:
    """
    Create a calendar event for an interview.

    Parameters
    ----------
    company:          Company name (used in event title).
    role:             Job role (used in event title).
    start_datetime:   ISO 8601 datetime string with timezone.
    duration_minutes: Interview duration in minutes (default 60).
    location:         "Video Call" or meeting link.
    description:      Additional notes.
    attendee_email:   Recruiter/interviewer email to invite.

    Returns
    -------
    dict: {"success": bool, "event_id": str | None, "event_link": str | None}
    """
    service = _build_calendar_service()

    start_dt = datetime.fromisoformat(start_datetime)
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    event_body: dict[str, Any] = {
        "summary": f"Interview — {role} @ {company}",
        "location": location,
        "description": description or f"Interview for {role} position at {company}.",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 1440},   # 24 hours
                {"method": "popup", "minutes": 30},
            ],
        },
    }

    if attendee_email:
        event_body["attendees"] = [{"email": attendee_email}]

    if service is None:
        logger.warning(
            "calendar_tool.dry_run",
            company=company,
            role=role,
            start=start_datetime,
        )
        return {
            "success": True,
            "event_id": "dry-run-event-id",
            "event_link": None,
            "dry_run": True,
            "event": event_body,
        }

    try:
        event = service.events().insert(calendarId="primary", body=event_body).execute()
        logger.info(
            "calendar_tool.event_created",
            event_id=event["id"],
            company=company,
            role=role,
        )
        return {
            "success": True,
            "event_id": event["id"],
            "event_link": event.get("htmlLink"),
        }
    except Exception as exc:
        logger.error("calendar_tool.create_failed", error=str(exc))
        return {"success": False, "error": str(exc)}


@registry.tool(
    name="list_upcoming_interviews",
    description="List all upcoming interview calendar events in the next N days.",
    tags=["calendar", "interview", "read"],
)
async def list_upcoming_interviews(days: int = 14) -> list[dict[str, Any]]:
    """
    Fetch upcoming interview events from Google Calendar.

    Parameters
    ----------
    days: Number of days ahead to look (default 14).

    Returns
    -------
    list[dict]: Interview events with title, start, end, location.
    """
    service = _build_calendar_service()

    if service is None:
        logger.warning("calendar_tool.no_service_dry_run")
        return [
            {
                "summary": "Interview — ML Engineer @ Google",
                "start": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                "end": (datetime.now(timezone.utc) + timedelta(days=3, hours=1)).isoformat(),
                "location": "https://meet.google.com/abc-defg-hij",
                "is_mock": True,
            }
        ]

    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=days)

    try:
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=time_max.isoformat(),
                q="interview",
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        return [
            {
                "summary": e.get("summary", ""),
                "start": e.get("start", {}).get("dateTime", ""),
                "end": e.get("end", {}).get("dateTime", ""),
                "location": e.get("location", ""),
                "event_id": e.get("id", ""),
            }
            for e in events
        ]
    except Exception as exc:
        logger.error("calendar_tool.list_failed", error=str(exc))
        return []
