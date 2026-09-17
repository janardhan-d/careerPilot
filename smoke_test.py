"""
CareerPilot — Import smoke test.
Run with: .venv/Scripts/python smoke_test.py
Verifies all modules import cleanly and the tool registry is populated.
"""
import sys
import io

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

print("=" * 55)
print("  CareerPilot Import Smoke Test")
print("=" * 55)

errors = []

def check(label, fn):
    try:
        result = fn()
        suffix = f"  ->  {result}" if result is not None else ""
        print(f"  [OK]   {label}{suffix}")
    except Exception as e:
        errors.append((label, str(e)))
        print(f"  [FAIL] {label}  ->  {e}")

# Core
check("core.config imports",          lambda: __import__("core.config"))
check("core.message_bus imports",     lambda: __import__("core.message_bus"))
check("core.tool_registry imports",   lambda: __import__("core.tool_registry"))
check("core.memory imports",          lambda: __import__("core.memory"))

# Models
check("models.schemas imports",       lambda: __import__("models.schemas"))
check("models.database imports",      lambda: __import__("models.database"))

# Tools (triggers @registry.tool decorators)
check("tools package imports",        lambda: __import__("tools"))

# Verify registry populated
from core.tool_registry import registry
tool_count = len(registry)
check("Tool registry populated",      lambda: f"{tool_count} tools registered")
expected_tools = [
    "search_jobs", "get_job_detail",
    "analyze_resume", "extract_resume_skills",
    "get_linkedin_profile", "search_linkedin_jobs", "update_linkedin_headline",
    "search_emails", "send_email", "parse_recruiter_email",
    "create_interview_event", "list_upcoming_interviews",
]
for t in expected_tools:
    check(f"  tool: {t}", lambda t=t: "found" if t in registry else (_ for _ in ()).throw(KeyError(t)))

# Agents
check("agents.base_agent imports",    lambda: __import__("agents.base_agent"))
check("agents.commander imports",     lambda: __import__("agents.commander"))
check("agents.tracker imports",       lambda: __import__("agents.tracker"))
check("agents.predictor imports",     lambda: __import__("agents.predictor"))

# Orchestration / CLI
check("orchestration.pipeline imports", lambda: __import__("orchestration.pipeline"))
check("cli.main imports",             lambda: __import__("cli.main"))

print()
if errors:
    print(f"  WARN: {len(errors)} import(s) failed:")
    for label, err in errors:
        print(f"     {label}: {err}")
    sys.exit(1)
else:
    total = 8 + len(expected_tools) + 6
    print(f"  PASS: All {total} checks passed — CareerPilot is ready!")
print("=" * 55)
