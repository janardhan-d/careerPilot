"""
CareerPilot — Tools package.

Importing this package auto-registers all tools with the global registry.
"""

# Import all tool modules so their @registry.tool decorators fire.
from . import (  # noqa: F401
    ats_checker_tool,
    calendar_tool,
    email_tool,
    job_board_tool,
    linkedin_tool,
    resume_tool,
)

__all__ = [
    "ats_checker_tool",
    "calendar_tool",
    "email_tool",
    "job_board_tool",
    "linkedin_tool",
    "resume_tool",
]
