# CareerPilot 🚀

> **Multi-Agent AI System for Autonomous Job Application Management**  
> Three specialized agents — Commander 🧠, Tracker 📡, Predictor 🔮 — collaborate to manage your entire job search pipeline.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-orange)](https://github.com/astral-sh/ruff)
[![Type Checked: MyPy](https://img.shields.io/badge/types-mypy-informational)](https://mypy-lang.org)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        CareerPilot System                        │
│                                                                  │
│   User / CLI                                                     │
│       │                                                          │
│       ▼                                                          │
│  ┌────────────┐    TASK     ┌────────────┐   EVENT   ┌────────┐  │
│  │ 🧠Commander│ ─────────► │ 📡 Tracker │ ────────► │  DB   │  │
│  │            │ ◄────────  │            │            │SQLite │  │
│  │ Orchestrate│  RESULT     │ Discover   │            └────────┘  │
│  │ Decompose  │             │ Deduplicate│                         │
│  │ Aggregate  │    TASK     │ Persist    │                         │
│  │            │ ─────────► ├────────────┤                         │
│  └────────────┘            │ 🔮Predictor│                         │
│        ▲       ◄────────   │            │                         │
│        │        RESULT     │ Score Jobs │                         │
│        │                   │ Predict    │                         │
│     Async                  │ Report     │                         │
│   Message Bus              └────────────┘                         │
│  (pub/sub)                                                        │
│                       ── Tool Registry ──                         │
│  linkedin_tool │ email_tool │ job_board_tool │ resume_tool │ …   │
└──────────────────────────────────────────────────────────────────┘
```

### The Three Agents

| Agent | Role | Key Capabilities |
|---|---|---|
| 🧠 **Commander** | Orchestrator | LLM goal decomposition, task delegation, result aggregation |
| 📡 **Tracker** | Data Manager | Job discovery, deduplication, DB persistence, profile sync, application lifecycle |
| 🔮 **Predictor** | Intelligence | ATS fit scoring, response probability, ranking, weekly reports, skill gap analysis |

### Communication Protocol

All agents talk through an **async priority message bus** using typed `AgentMessage` envelopes:

```
topic:   jobs | profiles | predictions | commands | events
type:    TASK | RESULT | EVENT | QUERY | ERROR
priority: HIGH | NORMAL | LOW
```

---

## Quickstart

### 1. Clone & Install

```bash
git clone https://github.com/you/careerPilot.git
cd careerPilot

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install (with dev tools)
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — add your OpenAI key (or leave blank for Ollama)
```

Key variables:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI key. Leave blank to use local Ollama. |
| `TARGET_ROLES` | Comma-separated job titles to track |
| `TARGET_LOCATIONS` | Comma-separated locations (or `Remote`) |
| `LINKEDIN_EMAIL` | LinkedIn credentials (optional) |
| `GMAIL_CREDENTIALS_PATH` | Path to Google Cloud credentials.json (optional) |

### 3. Run the Demo

```bash
careerpilot start --demo
```

This runs a full end-to-end demo with mock data — no API keys required.

### 4. Interactive Mode

```bash
careerpilot start
# careerpilot> Find 10 Machine Learning jobs in Remote and Bangalore
# careerpilot> Score all jobs and show my top recommendations
# careerpilot> Sync my LinkedIn profile and email inbox
# careerpilot> status
# careerpilot> quit
```

---

## CLI Commands

```bash
careerpilot start             # Launch all agents (REPL)
careerpilot start --demo      # Run the demo flow
careerpilot start --goal "Apply to 5 AI roles"   # Single goal

careerpilot status            # Rich table: jobs + applications
careerpilot report            # Weekly prediction report

careerpilot apply \
  --job-url "https://linkedin.com/jobs/view/123" \
  --resume ./resume.pdf       # Track & score a specific job

careerpilot config            # Show current configuration
```

---

## Project Structure

```
careerPilot/
├── agents/
│   ├── base_agent.py          # Abstract BaseAgent (lifecycle, memory, LLM, tools)
│   ├── commander.py           # 🧠 Orchestrator
│   ├── tracker.py             # 📡 Data manager
│   └── predictor.py           # 🔮 Intelligence layer
├── core/
│   ├── config.py              # Pydantic Settings (env-based)
│   ├── message_bus.py         # Async priority pub/sub bus
│   ├── tool_registry.py       # Shared tool discovery & invocation
│   └── memory.py              # TTL working memory + SQLite long-term
├── tools/
│   ├── job_board_tool.py      # LinkedIn + Indeed scrapers
│   ├── linkedin_tool.py       # LinkedIn profile read/write
│   ├── email_tool.py          # Gmail search, send, parse
│   ├── resume_tool.py         # PDF/DOCX parsing + ATS scoring
│   └── calendar_tool.py       # Google Calendar interview scheduling
├── models/
│   ├── schemas.py             # Pydantic v2 domain models
│   └── database.py            # SQLAlchemy 2 async ORM
├── orchestration/
│   └── pipeline.py            # Main entrypoint
├── cli/
│   └── main.py                # Typer + Rich CLI
├── tests/
│   ├── conftest.py
│   ├── test_agents/
│   └── test_tools/
├── .env.example
├── pyproject.toml
└── Makefile
```

---

## Development

```bash
make dev          # Install with dev dependencies
make lint         # ruff check
make fmt          # ruff format
make typecheck    # mypy
make test         # pytest with coverage
make run          # python -m orchestration.pipeline
```

---

## Scoring Model

The **Predictor** scores each job entirely offline (no LLM needed):

```
fit_score (0–100) =
    60%  Skill overlap   (your resume skills ∩ JD skills / JD skills)
  + 25%  Title match     (token overlap with your target roles)
  + 15%  Location match  (remote = full 15, on-site = 8)

response_probability (0–1) =
    base_prob (fit_score bucket) + easy_apply_bonus + company_tier_bonus
```

**Thresholds** (configurable via `MIN_FIT_SCORE` env var):

| Score | Recommendation |
|---|---|
| ≥ 65 | ✅ APPLY |
| 45–64 | 🔍 REVIEW |
| < 45 | ❌ SKIP |

---

## Extending CareerPilot

### Adding a New Tool

```python
# tools/my_tool.py
from core.tool_registry import registry

@registry.tool(
    name="my_tool",
    description="Does something useful",
    tags=["custom"],
)
async def my_tool(param: str) -> dict:
    return {"result": param}
```

Then import it in `tools/__init__.py` and it's instantly available to all agents.

### Adding a New Agent

```python
# agents/my_agent.py
from agents.base_agent import BaseAgent
from models.schemas import AgentMessage

class MyAgent(BaseAgent):
    agent_id = "my_agent"
    subscribed_topics = ["jobs"]

    async def handle_message(self, message: AgentMessage) -> None:
        result = await self.use_tool("search_jobs", query="AI Engineer")
        self.remember("last_search", result)
        await self.emit_event("events", {"type": "custom_event"})
```

---

## Roadmap

- [ ] Playwright-based auto-apply (form filling)
- [ ] Naukri.com scraper
- [ ] Resume auto-tailoring via LLM
- [ ] Telegram / WhatsApp bot interface
- [ ] Redis message bus (production upgrade)
- [ ] Cover letter generator
- [ ] Interview prep Q&A (RAG over JD + your resume)

---

## License

MIT © CareerPilot Contributors
