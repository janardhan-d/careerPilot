# 🤖 Smart AI Job Agent — Autonomous Multi-Agent Application System
> **Candidate Profile:** Janardhan Devarala | **Target Locations:** Hyderabad, Bangalore, Remote India  
> **Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (Async), Uvicorn, MessageBus, Localtunnel, GitHub  

---

## 🌟 Overview
**Smart AI Job Agent** is an autonomous multi-agent system designed to streamline, track, score, and execute job & internship applications for **Janardhan Devarala** across India (Hyderabad, Bangalore, Remote). 

Equipped with four specialized AI agents communicating via an async message bus, the system monitors job postings hourly, predicts ATS match pass probability, generates custom tailored ATS resumes & cover letters, executes applications, and sends real-time updates to mobile devices.

---

## 🧠 Multi-Agent Architecture

```
                               ┌───────────────────────────┐
                               │     COMMANDER AGENT       │
                               │  (Workflow Orchestrator)  │
                               └─────────────┬─────────────┘
                                             │
                      ┌──────────────────────┼──────────────────────┐
                      ▼                      ▼                      ▼
           ┌─────────────────────┐┌─────────────────────┐┌─────────────────────┐
           │    TRACKER AGENT    ││   PREDICTOR AGENT   ││    APPLIER AGENT    │
           │ (Hourly Job Scanner)││(ATS Score Predictor)││(1-Click Fast Apply) │
           └─────────────────────┘└─────────────────────┘└─────────────────────┘
```

| Agent | Icon | Role & Description |
|---|---|---|
| **Tracker Agent** | 🔍 | Scans LinkedIn Jobs, Naukri India, Indeed, and company career pages hourly for Data Analyst, Python Developer, and Financial Analyst roles in Hyderabad, Bangalore & Remote India. |
| **Predictor Agent** | 🔮 | Analyzes job descriptions, extracts ATS keywords, matches candidate skills (Python, SQL, Pandas, FastAPI, AI Agents), and predicts ATS Pass Probability. |
| **Commander Agent** | 🎯 | Orchestrates workflow execution, triggers search goals, enforces minimum fit score thresholds, and logs pipeline state. |
| **Applier Agent** | ⚡ | Generates tailored ATS resumes & cover letters, executes 1-click applications, builds recruiter outreach packages (Email, LinkedIn Note, Call Script), and sends mobile alerts. |

---

## 👤 Candidate Profile — Janardhan Devarala

- **Full Name:** Janardhan Devarala
- **Location:** Podalakur, Andhra Pradesh, India *(Targeting Hyderabad, Bangalore, Remote India)*
- **Emails:** `janardhand2021@gmail.com` / `devaralajanardhan@gmail.com`
- **Phones:** `+91 70934 35561` / `+91 92042 65330`
- **Links:**
  - 🐙 **GitHub:** [https://github.com/janardhan-d](https://github.com/janardhan-d)
  - 💼 **LinkedIn:** [https://www.linkedin.com/in/janardhan-devarala-1552172a1](https://www.linkedin.com/in/janardhan-devarala-1552172a1)
  - 🌐 **Portfolio:** [https://janardhan-devarala-portfolio.netlify.app](https://janardhan-devarala-portfolio.netlify.app)
- **Core Skills:** Python, SQL, Pandas, Matplotlib, Tkinter GUI, SQLite, MongoDB, React, Data Analysis, FastAPI, AI Agent Systems
- **Certifications & Badges:**
  - APSCHE + CSC India Internship *(Data Structures & Algorithms in Python)*
  - InnoByte Services Internship *(Python Developer)*
  - Google Cloud Badges *(Responsible AI, Generative AI, LLMs)*
  - Microsoft Learn Badges *(Generative AI, Cloud Computing, Big Data)*
- **Hackathon Honors:** CodeSprint-2026, Smart India Hackathon Finalist, NRCM Hackathon Finalist, SVC Hackathon Top 5

---

## 📂 Repository Structure

```
careerPilot/
├── config.yaml              # API Keys, India Location Filters & Scheduling
├── run_server.py            # Uvicorn FastAPI Server Launcher
├── main.py                  # CLI & Core System Entrypoint
├── agents/
│   ├── base_agent.py        # Base Agent Lifecycle & MessageBus Handler
│   ├── commander.py         # Workflow Commander Agent
│   ├── tracker.py           # Hourly Job Tracker Agent
│   ├── predictor.py         # ATS Match Predictor Agent
│   └── applier.py           # Fast 1-Click Applier & Outreach Agent
├── api/
│   ├── server.py            # REST API & WebSocket Event Stream
│   └── dashboard.py         # Glassmorphism HTML Frontend UI
├── models/
│   ├── database.py          # SQLAlchemy 2.0 Async ORM Schemas
│   └── schemas.py           # Pydantic Schemas & Agent Message Envelopes
├── utils/
│   ├── resume_builder.py    # ATS Resume & Cover Letter Generator
│   ├── notifier.py          # Mobile / WhatsApp Notification Utility
│   └── __init__.py
└── tools/
    ├── job_board_tool.py    # LinkedIn & Indeed Scrapers
    ├── linkedin_tool.py     # LinkedIn Profile Integration
    └── email_tool.py        # Gmail & Recruiter Email Scraper
```

---

## 🚀 Quick Start & Local Execution

### 1. Installation
```powershell
# Clone the repository
git clone https://github.com/janardhan-d/careerPilot.git
cd careerPilot

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Start API Server & Dashboard
```powershell
python run_server.py
```
Open **`http://localhost:8000`** in your browser to view the live multi-agent dashboard.

---

## 📄 License
MIT License © 2026 Janardhan Devarala
