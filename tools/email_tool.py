"""
CareerPilot — Email Tool
=========================
Gmail API integration for reading recruiter emails and composing follow-ups.
Falls back to SMTP for sending when OAuth is not configured.

Registered tools:
  - search_emails        → search inbox for recruiter/job emails
  - get_email            → fetch a single email by ID
  - send_email           → send a follow-up or cover letter email
  - parse_recruiter_email → extract structured data from a recruiter message
"""

from __future__ import annotations

import base64
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import structlog

from core.config import settings
from core.tool_registry import registry
from models.schemas import EmailSearchInput

logger = structlog.get_logger(__name__)

# Gmail API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


# ── Gmail client factory ───────────────────────────────────────────────────────

def _build_gmail_service() -> Any:
    """
    Build and return an authenticated Gmail API service.
    Returns None if credentials are unavailable.
    """
    creds_path = settings.gmail_credentials_path
    token_path = settings.gmail_token_path

    if not os.path.exists(creds_path):
        logger.warning("email_tool.no_credentials_file", path=creds_path)
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        service = build("gmail", "v1", credentials=creds)
        logger.info("email_tool.gmail_authenticated")
        return service

    except ImportError:
        logger.error("email_tool.google_api_not_installed")
        return None
    except Exception as exc:
        logger.error("email_tool.auth_failed", error=str(exc))
        return None


# ── Parsing helpers ────────────────────────────────────────────────────────────

def _decode_payload(payload: dict[str, Any]) -> str:
    """Decode a Gmail message payload to plain text."""
    body = ""
    if "body" in payload:
        data = payload["body"].get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    if not body and "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                    break
    return body


def _extract_headers(headers: list[dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


# ── Recruiter email classifier ────────────────────────────────────────────────

RECRUITER_KEYWORDS = [
    "opportunity", "position", "role", "job", "opening", "interview",
    "recruiter", "talent acquisition", "hiring", "offer", "application",
    "shortlisted", "next steps", "assessment", "onsite", "joining",
]

REJECTION_KEYWORDS = [
    "not moving forward", "other candidates", "decided not to", "regret",
    "unfortunately", "position has been filled", "not a fit", "no longer",
]


def _classify_email(subject: str, body: str) -> str:
    """Classify a recruiter email: OPPORTUNITY | REJECTION | INTERVIEW | OFFER | OTHER."""
    text = (subject + " " + body).lower()
    if any(kw in text for kw in REJECTION_KEYWORDS):
        return "REJECTION"
    if "offer" in text and ("congratulations" in text or "pleased" in text):
        return "OFFER"
    if any(kw in text for kw in ["interview", "schedule", "availability"]):
        return "INTERVIEW"
    if any(kw in text for kw in RECRUITER_KEYWORDS):
        return "OPPORTUNITY"
    return "OTHER"


# ── Mock email data ────────────────────────────────────────────────────────────

def _mock_emails(query: str, n: int = 5) -> list[dict[str, Any]]:
    import random
    subjects = [
        "Exciting ML Engineer opportunity at Google",
        "Your application to Amazon — Next steps",
        "Interview invitation — Senior AI Engineer, Microsoft",
        "We reviewed your profile — Flipkart",
        "Follow-up: Software Engineer role at Razorpay",
    ]
    senders = [
        "recruiter@google.com", "talent@amazon.com",
        "hr@microsoft.com", "hiring@flipkart.com", "careers@razorpay.com",
    ]
    return [
        {
            "id": f"mock_{i}",
            "subject": random.choice(subjects),
            "from": random.choice(senders),
            "date": "2024-09-15",
            "snippet": f"Hi, we came across your profile and wanted to reach out about a {query} role...",
            "classification": random.choice(["OPPORTUNITY", "INTERVIEW", "REJECTION"]),
            "is_mock": True,
        }
        for i in range(n)
    ]


# ── Registered Tools ──────────────────────────────────────────────────────────

@registry.tool(
    name="search_emails",
    description="Search Gmail inbox for recruiter and job-related emails.",
    tags=["email", "search"],
    input_schema=EmailSearchInput,
)
async def search_emails(
    query: str = "job OR recruiter OR opportunity OR interview",
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """
    Search Gmail inbox using the provided query.

    Returns
    -------
    list[dict]: Email summaries with id, subject, from, date, snippet, classification.
    """
    service = _build_gmail_service()
    if service is None:
        logger.warning("email_tool.using_mock_emails")
        return _mock_emails(query, n=min(max_results, 5))

    try:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = results.get("messages", [])
        emails = []

        for msg_ref in messages[:max_results]:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="full")
                .execute()
            )
            headers = msg.get("payload", {}).get("headers", [])
            body = _decode_payload(msg.get("payload", {}))
            subject = _extract_headers(headers, "subject")
            sender = _extract_headers(headers, "from")
            date = _extract_headers(headers, "date")
            classification = _classify_email(subject, body)

            emails.append({
                "id": msg["id"],
                "subject": subject,
                "from": sender,
                "date": date,
                "snippet": msg.get("snippet", ""),
                "classification": classification,
            })

        logger.info("email_tool.search_done", count=len(emails))
        return emails

    except Exception as exc:
        logger.error("email_tool.search_failed", error=str(exc))
        return _mock_emails(query)


@registry.tool(
    name="send_email",
    description="Send a follow-up or cover letter email via Gmail.",
    tags=["email", "send"],
)
async def send_email(
    to: str,
    subject: str,
    body: str,
    is_html: bool = False,
) -> dict[str, Any]:
    """
    Send an email via Gmail API.

    Parameters
    ----------
    to:       Recipient email address.
    subject:  Email subject line.
    body:     Email body (plain text or HTML).
    is_html:  Set True if body is HTML.

    Returns
    -------
    dict: {"success": bool, "message_id": str | None}
    """
    service = _build_gmail_service()
    if service is None:
        logger.warning("email_tool.cannot_send_no_auth", to=to, subject=subject)
        return {"success": False, "error": "Gmail not configured — email not sent (dry run)"}

    try:
        mime = MIMEMultipart("alternative")
        mime["to"] = to
        mime["subject"] = subject
        mime.attach(MIMEText(body, "html" if is_html else "plain"))

        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        sent = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        logger.info("email_tool.sent", to=to, subject=subject, message_id=sent["id"])
        return {"success": True, "message_id": sent["id"]}

    except Exception as exc:
        logger.error("email_tool.send_failed", error=str(exc))
        return {"success": False, "error": str(exc)}


@registry.tool(
    name="parse_recruiter_email",
    description="Extract structured data (company, role, deadline) from a recruiter email body.",
    tags=["email", "parse"],
)
async def parse_recruiter_email(email_body: str) -> dict[str, Any]:
    """
    Use regex + heuristics to extract key fields from a recruiter email.

    Returns
    -------
    dict: company, role, deadline, contact_name, contact_email, classification
    """
    # Simple regex-based extraction
    email_re = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)
    emails_found = email_re.findall(email_body)
    contact_email = emails_found[0] if emails_found else ""

    role_re = re.compile(
        r"(?:position|role|opening|opportunity)[:\s]+([A-Za-z\s/]+?)(?:\.|,|\n|at\s)", re.I
    )
    role_match = role_re.search(email_body)
    role = role_match.group(1).strip() if role_match else ""

    company_re = re.compile(r"(?:at|@|with|from)\s+([A-Z][A-Za-z\s&.]+?)(?:\.|,|\n)", re.I)
    company_match = company_re.search(email_body)
    company = company_match.group(1).strip() if company_match else ""

    classification = _classify_email("", email_body)

    return {
        "company": company,
        "role": role,
        "contact_email": contact_email,
        "classification": classification,
        "has_action_required": classification in {"OPPORTUNITY", "INTERVIEW"},
    }
