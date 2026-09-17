"""
CareerPilot — FastAPI Web Server
=================================
REST API + WebSocket event stream + single-page dashboard.

Endpoints
---------
  GET  /                  → HTML dashboard
  GET  /api/status        → agent health snapshot
  POST /api/goal          → submit goal to Commander
  GET  /api/jobs          → paginated job list with scores
  GET  /api/applications  → application pipeline
  GET  /api/report        → weekly prediction report
  WS   /ws/events         → real-time event stream (SSE-over-WS)
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import tools  # noqa: F401 — auto-register all tools

from core.message_bus import get_bus
from agents.commander import CommanderAgent
from agents.tracker import TrackerAgent
from agents.predictor import PredictorAgent
from models.database import get_session, init_db, JobPostingORM, ApplicationORM, PredictionORM
from sqlalchemy import select, func

logger = structlog.get_logger(__name__)

# ── Global pipeline state ─────────────────────────────────────────────────────

_commander: CommanderAgent | None = None
_tracker: TrackerAgent | None = None
_predictor: PredictorAgent | None = None
_ws_clients: list[WebSocket] = []


async def _broadcast(event: dict[str, Any]) -> None:
    """Push a JSON event to all connected WebSocket clients."""
    dead = []
    for ws in list(_ws_clients):
        try:
            await ws.send_text(json.dumps(event, default=str))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _commander, _tracker, _predictor

    await init_db()
    bus = get_bus()
    await bus.start()

    _commander = CommanderAgent(bus=bus)
    _tracker   = TrackerAgent(bus=bus)
    _predictor = PredictorAgent(bus=bus)

    await _commander.start()
    await _tracker.start()
    await _predictor.start()

    logger.info("api.agents_ready")
    yield

    # Shutdown
    await _predictor.stop()
    await _tracker.stop()
    await _commander.stop()
    await bus.stop()
    logger.info("api.shutdown_complete")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CareerPilot",
    description="Multi-Agent AI Job Application Manager",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST routes ───────────────────────────────────────────────────────────────

@app.get("/api/status")
async def status() -> JSONResponse:
    return JSONResponse({
        "commander": _commander.status() if _commander else {},
        "tracker":   _tracker.status()   if _tracker   else {},
        "predictor": _predictor.status() if _predictor else {},
        "timestamp": datetime.utcnow().isoformat(),
    })


@app.post("/api/goal")
async def submit_goal(body: dict[str, str]) -> JSONResponse:
    goal = body.get("goal", "").strip()
    if not goal:
        return JSONResponse({"error": "goal is required"}, status_code=400)
    asyncio.create_task(_commander.run_goal(goal))
    await _broadcast({"event": "goal_submitted", "goal": goal})
    return JSONResponse({"status": "queued", "goal": goal})


@app.get("/api/jobs")
async def list_jobs(page: int = 1, per_page: int = 20) -> JSONResponse:
    offset = (page - 1) * per_page
    async with get_session() as session:
        total_r = await session.execute(select(func.count()).select_from(JobPostingORM))
        total = total_r.scalar_one()

        result = await session.execute(
            select(JobPostingORM)
            .order_by(JobPostingORM.discovered_at.desc())
            .offset(offset).limit(per_page)
        )
        jobs = result.scalars().all()

        # Join with predictions
        pred_result = await session.execute(select(PredictionORM))
        pred_map = {p.job_id: p for p in pred_result.scalars().all()}

    rows = []
    for j in jobs:
        p = pred_map.get(j.id)
        rows.append({
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "is_remote": j.is_remote,
            "easy_apply": j.easy_apply,
            "source": j.source,
            "source_url": j.source_url,
            "discovered_at": j.discovered_at.isoformat() if j.discovered_at else None,
            "fit_score": round(p.fit_score, 1) if p else None,
            "recommendation": p.recommendation if p else "PENDING",
            "response_probability": round(p.response_probability * 100) if p else None,
            "matched_skills": (p.matched_skills or [])[:5] if p else [],
        })

    return JSONResponse({"total": total, "page": page, "per_page": per_page, "jobs": rows})


@app.get("/api/applications")
async def list_applications() -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(ApplicationORM).order_by(ApplicationORM.last_updated.desc())
        )
        apps = result.scalars().all()
    return JSONResponse([{
        "id": a.id,
        "job_title": a.job_title,
        "company": a.company,
        "status": a.status,
        "fit_score": a.fit_score,
        "applied_at": a.applied_at.isoformat() if a.applied_at else None,
        "last_updated": a.last_updated.isoformat() if a.last_updated else None,
    } for a in apps])


@app.get("/api/report")
async def weekly_report() -> JSONResponse:
    report = await _predictor._build_weekly_report()
    return JSONResponse(report.model_dump(mode="json"))


# ── WebSocket event stream ────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        await websocket.send_text(json.dumps({"event": "connected", "msg": "CareerPilot live stream ready"}))
        while True:
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"event": "ping"}))
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


# ── Dashboard HTML ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(DASHBOARD_HTML)


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CareerPilot — AI Job Manager</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet"/>
<style>
  :root {
    --bg: #0a0a0f;
    --surface: #13131a;
    --surface2: #1c1c28;
    --border: #2a2a3d;
    --accent: #6c63ff;
    --accent2: #00d4ff;
    --accent3: #ff6584;
    --green: #00e676;
    --yellow: #ffd740;
    --text: #e8e8f0;
    --text-dim: #8888aa;
    --radius: 14px;
    --glow: 0 0 30px rgba(108,99,255,0.15);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

  /* ── Header ── */
  header {
    background: linear-gradient(135deg, #13131a 0%, #1a1a2e 50%, #16213e 100%);
    border-bottom: 1px solid var(--border);
    padding: 0 2rem;
    display: flex; align-items: center; justify-content: space-between;
    height: 64px;
    position: sticky; top: 0; z-index: 100;
    backdrop-filter: blur(20px);
  }
  .logo { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 1.25rem;
          background: linear-gradient(90deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .logo-icon { width: 32px; height: 32px; background: linear-gradient(135deg, var(--accent), var(--accent2));
               border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 1rem; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green);
                box-shadow: 0 0 8px var(--green); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
  .header-right { display: flex; align-items: center; gap: 16px; font-size: 0.85rem; color: var(--text-dim); }

  /* ── Layout ── */
  .container { max-width: 1400px; margin: 0 auto; padding: 2rem; }
  .grid-3 { display: grid; grid-template-columns: repeat(3,1fr); gap: 1.5rem; margin-bottom: 2rem; }
  .grid-2 { display: grid; grid-template-columns: 2fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }
  @media(max-width:900px){ .grid-3,.grid-2{ grid-template-columns:1fr; } }

  /* ── Cards ── */
  .card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 1.5rem; transition: transform 0.2s, box-shadow 0.2s;
  }
  .card:hover { transform: translateY(-2px); box-shadow: var(--glow); }
  .card-title { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em;
                color: var(--text-dim); margin-bottom: 0.75rem; }
  .stat-value { font-size: 2.5rem; font-weight: 800; line-height: 1;
                background: linear-gradient(135deg, var(--accent), var(--accent2));
                -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .stat-label { font-size: 0.8rem; color: var(--text-dim); margin-top: 0.25rem; }

  /* ── Goal input ── */
  .goal-section { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
                  padding: 1.5rem; margin-bottom: 2rem; }
  .goal-section h2 { font-size: 1rem; font-weight: 600; margin-bottom: 1rem;
                     background: linear-gradient(90deg,var(--accent),var(--accent2));
                     -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
  .goal-form { display: flex; gap: 0.75rem; }
  .goal-input {
    flex: 1; background: var(--surface2); border: 1px solid var(--border); border-radius: 10px;
    color: var(--text); font-family: inherit; font-size: 0.95rem; padding: 0.75rem 1rem;
    outline: none; transition: border-color 0.2s;
  }
  .goal-input:focus { border-color: var(--accent); }
  .btn {
    background: linear-gradient(135deg, var(--accent), #8b5cf6); color: #fff; font-family: inherit;
    font-weight: 600; font-size: 0.9rem; padding: 0.75rem 1.5rem; border: none; border-radius: 10px;
    cursor: pointer; transition: opacity 0.2s, transform 0.1s; white-space: nowrap;
  }
  .btn:hover { opacity: 0.9; transform: scale(1.02); }
  .btn:active { transform: scale(0.98); }
  .btn.secondary { background: var(--surface2); border: 1px solid var(--border); color: var(--text); }

  /* ── Jobs table ── */
  .section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
  .section-title { font-size: 1rem; font-weight: 700; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { background: var(--surface2); color: var(--text-dim); font-weight: 600; font-size: 0.75rem;
       text-transform: uppercase; letter-spacing: 0.05em; padding: 0.75rem 1rem; text-align: left; }
  td { padding: 0.8rem 1rem; border-bottom: 1px solid var(--border); }
  tr:hover td { background: rgba(108,99,255,0.05); }
  tr:last-child td { border-bottom: none; }

  /* ── Badges ── */
  .badge { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 100px;
           font-size: 0.72rem; font-weight: 600; letter-spacing: 0.03em; }
  .badge-apply  { background: rgba(0,230,118,0.15); color: #00e676; }
  .badge-review { background: rgba(255,215,64,0.15); color: #ffd740; }
  .badge-skip   { background: rgba(255,101,132,0.15); color: #ff6584; }
  .badge-pending{ background: rgba(136,136,170,0.15); color: #8888aa; }
  .badge-remote { background: rgba(0,212,255,0.12); color: var(--accent2); }

  /* ── Score bar ── */
  .score-wrap { display: flex; align-items: center; gap: 8px; }
  .score-bar { width: 60px; height: 6px; background: var(--surface2); border-radius: 3px; overflow: hidden; }
  .score-fill { height: 100%; border-radius: 3px; transition: width 0.6s ease; }
  .score-num { font-weight: 600; font-size: 0.85rem; min-width: 28px; }

  /* ── Event log ── */
  .event-log { background: var(--surface2); border-radius: 10px; padding: 1rem;
               height: 260px; overflow-y: auto; font-size: 0.8rem; font-family: monospace; }
  .event-log::-webkit-scrollbar { width: 4px; }
  .event-log::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
  .event-entry { padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.04); color: var(--text-dim); }
  .event-entry .time { color: var(--accent); margin-right: 8px; }
  .event-entry .msg { color: var(--text); }

  /* ── Agents ── */
  .agent-card { display: flex; align-items: center; gap: 12px; padding: 1rem;
                background: var(--surface2); border-radius: 10px; margin-bottom: 0.75rem; }
  .agent-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center;
                justify-content: center; font-size: 1.3rem; flex-shrink: 0; }
  .agent-info { flex: 1; }
  .agent-name { font-weight: 600; font-size: 0.9rem; }
  .agent-desc { font-size: 0.75rem; color: var(--text-dim); margin-top: 2px; }
  .agent-status { font-size: 0.72rem; font-weight: 600; padding: 3px 8px; border-radius: 6px; }
  .agent-running { background: rgba(0,230,118,0.15); color: #00e676; }

  /* ── Tabs ── */
  .tabs { display: flex; gap: 4px; margin-bottom: 1.5rem; }
  .tab { padding: 0.5rem 1.2rem; border-radius: 8px; font-size: 0.85rem; font-weight: 500;
         cursor: pointer; border: 1px solid transparent; color: var(--text-dim); transition: all 0.2s; }
  .tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .tab:hover:not(.active) { background: var(--surface2); border-color: var(--border); color: var(--text); }

  /* ── Toast ── */
  #toast { position: fixed; bottom: 2rem; right: 2rem; background: var(--surface);
           border: 1px solid var(--accent); border-radius: 12px; padding: 1rem 1.5rem;
           font-size: 0.9rem; box-shadow: var(--glow); transform: translateY(100px);
           opacity: 0; transition: all 0.3s; z-index: 999; }
  #toast.show { transform: translateY(0); opacity: 1; }

  /* ── Loader ── */
  .loader { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--border);
            border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .empty { text-align: center; color: var(--text-dim); padding: 3rem 0; font-size: 0.9rem; }
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-icon">🚀</div>
    CareerPilot
  </div>
  <div class="header-right">
    <div class="status-dot"></div>
    <span id="agent-label">3 Agents Running</span>
    <span style="color:var(--border)">|</span>
    <span id="jobs-count">— jobs</span>
  </div>
</header>

<div class="container">

  <!-- Stats row -->
  <div class="grid-3" id="stats-row">
    <div class="card">
      <div class="card-title">Jobs Discovered</div>
      <div class="stat-value" id="stat-jobs">—</div>
      <div class="stat-label">tracked in database</div>
    </div>
    <div class="card">
      <div class="card-title">Applications Active</div>
      <div class="stat-value" id="stat-apps">—</div>
      <div class="stat-label">in pipeline</div>
    </div>
    <div class="card">
      <div class="card-title">Avg Fit Score</div>
      <div class="stat-value" id="stat-score">—</div>
      <div class="stat-label">across scored jobs</div>
    </div>
  </div>

  <!-- Goal input -->
  <div class="goal-section">
    <h2>🧠 Commander — Submit a Goal</h2>
    <div class="goal-form">
      <input class="goal-input" id="goal-input" type="text"
             placeholder='Try: "Find 20 ML Engineer jobs in Remote and score them" …'/>
      <button class="btn" onclick="submitGoal()">Run Goal</button>
      <button class="btn secondary" onclick="loadReport()">Weekly Report</button>
    </div>
  </div>

  <!-- Main grid -->
  <div class="grid-2">

    <!-- Jobs panel -->
    <div class="card" style="padding:0;overflow:hidden;">
      <div style="padding:1.25rem 1.5rem;" class="section-header">
        <span class="section-title">📋 Job Discoveries</span>
        <button class="btn secondary" style="padding:0.4rem 0.9rem;font-size:0.8rem;" onclick="loadJobs()">Refresh</button>
      </div>
      <div id="jobs-container" style="overflow:auto;max-height:480px;">
        <div class="empty"><span class="loader"></span></div>
      </div>
    </div>

    <!-- Right panel -->
    <div>
      <!-- Agents -->
      <div class="card" style="margin-bottom:1.5rem;">
        <div class="card-title">Agent Status</div>
        <div class="agent-card">
          <div class="agent-icon" style="background:rgba(108,99,255,0.15)">🧠</div>
          <div class="agent-info">
            <div class="agent-name">Commander</div>
            <div class="agent-desc" id="cmd-desc">Goal decomposition · Task delegation</div>
          </div>
          <span class="agent-status agent-running">LIVE</span>
        </div>
        <div class="agent-card">
          <div class="agent-icon" style="background:rgba(0,212,255,0.12)">📡</div>
          <div class="agent-info">
            <div class="agent-name">Tracker</div>
            <div class="agent-desc" id="trk-desc">Job discovery · Deduplication · DB</div>
          </div>
          <span class="agent-status agent-running">LIVE</span>
        </div>
        <div class="agent-card">
          <div class="agent-icon" style="background:rgba(0,230,118,0.1)">🔮</div>
          <div class="agent-info">
            <div class="agent-name">Predictor</div>
            <div class="agent-desc" id="prd-desc">ATS scoring · Recommendations</div>
          </div>
          <span class="agent-status agent-running">LIVE</span>
        </div>
      </div>

      <!-- Live events -->
      <div class="card">
        <div class="card-title">Live Event Stream</div>
        <div class="event-log" id="event-log">
          <div class="event-entry"><span class="time">--:--:--</span><span class="msg">Connecting to CareerPilot...</span></div>
        </div>
      </div>
    </div>
  </div>

  <!-- Report section (hidden by default) -->
  <div id="report-section" style="display:none;" class="card">
    <div class="section-header">
      <span class="section-title">🔮 Weekly AI Report</span>
      <button class="btn secondary" style="padding:0.4rem 0.9rem;font-size:0.8rem;" onclick="document.getElementById('report-section').style.display='none'">Close</button>
    </div>
    <div id="report-content"></div>
  </div>

</div>

<div id="toast"></div>

<script>
const API = '';

function toast(msg, duration=3000) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), duration);
}

function scoreColor(s) {
  if (!s) return '#8888aa';
  if (s >= 70) return '#00e676';
  if (s >= 50) return '#ffd740';
  return '#ff6584';
}

function addEvent(msg, type='info') {
  const log = document.getElementById('event-log');
  const now = new Date().toLocaleTimeString();
  const entry = document.createElement('div');
  entry.className = 'event-entry';
  entry.innerHTML = `<span class="time">${now}</span><span class="msg">${msg}</span>`;
  log.prepend(entry);
  // Keep last 50
  while (log.children.length > 50) log.removeChild(log.lastChild);
}

// ── WebSocket ──────────────────────────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/events`);
  ws.onmessage = e => {
    const d = JSON.parse(e.data);
    if (d.event === 'ping') return;
    if (d.event === 'connected') { addEvent('Connected to CareerPilot live stream'); return; }
    if (d.event === 'goal_submitted') { addEvent(`Goal submitted: ${d.goal}`); return; }
    addEvent(JSON.stringify(d));
  };
  ws.onclose = () => { addEvent('Disconnected — reconnecting in 3s...'); setTimeout(connectWS, 3000); };
  ws.onerror = () => ws.close();
}

// ── Load Jobs ──────────────────────────────────────────────────────────────
async function loadJobs() {
  const container = document.getElementById('jobs-container');
  container.innerHTML = '<div class="empty"><span class="loader"></span></div>';
  try {
    const res = await fetch(`${API}/api/jobs?per_page=30`);
    const data = await res.json();
    document.getElementById('stat-jobs').textContent = data.total;
    document.getElementById('jobs-count').textContent = `${data.total} jobs`;

    if (!data.jobs.length) {
      container.innerHTML = '<div class="empty">No jobs yet — submit a goal to start!</div>';
      return;
    }

    const rows = data.jobs.map(j => {
      const recBadge = j.recommendation === 'APPLY'  ? 'badge-apply'
                     : j.recommendation === 'REVIEW' ? 'badge-review'
                     : j.recommendation === 'PENDING'? 'badge-pending'
                     : 'badge-skip';
      const scoreBar = j.fit_score != null
        ? `<div class="score-wrap">
             <div class="score-bar"><div class="score-fill" style="width:${j.fit_score}%;background:${scoreColor(j.fit_score)}"></div></div>
             <span class="score-num" style="color:${scoreColor(j.fit_score)}">${j.fit_score}</span>
           </div>`
        : '<span style="color:var(--text-dim)">—</span>';
      const remote = j.is_remote ? '<span class="badge badge-remote">Remote</span>' : '';
      const easyApply = j.easy_apply ? '⚡' : '';
      return `<tr>
        <td><strong>${j.title}</strong><br><span style="color:var(--text-dim);font-size:0.78rem">${j.company}</span></td>
        <td>${j.location} ${remote}</td>
        <td>${scoreBar}</td>
        <td><span class="badge ${recBadge}">${j.recommendation}</span></td>
        <td>${j.response_probability != null ? j.response_probability+'%' : '—'} ${easyApply}</td>
        <td><a href="${j.source_url}" target="_blank" style="color:var(--accent);text-decoration:none;font-size:0.8rem">Apply →</a></td>
      </tr>`;
    }).join('');

    container.innerHTML = `
      <table>
        <thead><tr>
          <th>Role</th><th>Location</th><th>Fit Score</th><th>Action</th><th>Response %</th><th>Link</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch(e) {
    container.innerHTML = `<div class="empty">Error: ${e.message}</div>`;
  }
}

// ── Load Stats ─────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const [statusRes, appsRes, reportRes] = await Promise.all([
      fetch(`${API}/api/status`),
      fetch(`${API}/api/applications`),
      fetch(`${API}/api/report`),
    ]);
    const status = await statusRes.json();
    const apps   = await appsRes.json();
    const report = await reportRes.json();

    const active = apps.filter(a => !['REJECTED','WITHDRAWN','ACCEPTED'].includes(a.status)).length;
    document.getElementById('stat-apps').textContent = active;
    document.getElementById('stat-score').textContent = report.avg_fit_score ? report.avg_fit_score.toFixed(0) : '—';

    const t = status.tracker || {};
    const p = status.predictor || {};
    document.getElementById('trk-desc').textContent = `${t.known_jobs || 0} jobs tracked · polling every ${t.poll_interval_secs || 3600}s`;
    document.getElementById('prd-desc').textContent = `${p.scored_jobs || 0} jobs scored · min score ${p.min_fit_score || 65}`;
  } catch(e) { /* silent */ }
}

// ── Submit Goal ────────────────────────────────────────────────────────────
async function submitGoal() {
  const input = document.getElementById('goal-input');
  const goal = input.value.trim();
  if (!goal) return;
  input.value = '';
  addEvent(`Submitting: ${goal}`);
  try {
    const res = await fetch(`${API}/api/goal`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({goal})
    });
    const data = await res.json();
    if (data.error) { toast(`Error: ${data.error}`); return; }
    toast('Goal queued! Agents are working...');
    setTimeout(loadJobs, 8000);
    setTimeout(loadStats, 10000);
  } catch(e) { toast(`Error: ${e.message}`); }
}

document.getElementById('goal-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') submitGoal();
});

// ── Load Report ────────────────────────────────────────────────────────────
async function loadReport() {
  const section = document.getElementById('report-section');
  const content = document.getElementById('report-content');
  section.style.display = 'block';
  content.innerHTML = '<div class="empty"><span class="loader"></span></div>';
  try {
    const res = await fetch(`${API}/api/report`);
    const r = await res.json();
    const topRows = (r.top_recommendations || []).map((p,i) =>
      `<tr>
        <td>${i+1}</td>
        <td><strong>${p.job_title}</strong></td>
        <td>${p.company}</td>
        <td style="color:${scoreColor(p.fit_score)};font-weight:700">${p.fit_score?.toFixed(0)}/100</td>
        <td>${((p.response_probability||0)*100).toFixed(0)}%</td>
        <td><span class="badge ${p.recommendation==='APPLY'?'badge-apply':p.recommendation==='REVIEW'?'badge-review':'badge-skip'}">${p.recommendation}</span></td>
      </tr>`).join('');
    content.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:1.5rem;">
        <div style="text-align:center"><div style="font-size:2rem;font-weight:800;color:var(--accent)">${r.total_jobs_tracked}</div><div style="color:var(--text-dim);font-size:0.8rem">Jobs Tracked</div></div>
        <div style="text-align:center"><div style="font-size:2rem;font-weight:800;color:var(--accent2)">${r.total_applications}</div><div style="color:var(--text-dim);font-size:0.8rem">Applications</div></div>
        <div style="text-align:center"><div style="font-size:2rem;font-weight:800;color:var(--green)">${r.active_applications}</div><div style="color:var(--text-dim);font-size:0.8rem">Active</div></div>
        <div style="text-align:center"><div style="font-size:2rem;font-weight:800;color:var(--yellow)">${r.avg_fit_score?.toFixed(0)||'—'}</div><div style="color:var(--text-dim);font-size:0.8rem">Avg Fit</div></div>
      </div>
      ${r.insights?.map(i=>`<div style="background:rgba(108,99,255,0.08);border-left:3px solid var(--accent);padding:0.75rem 1rem;border-radius:0 8px 8px 0;margin-bottom:0.5rem;font-size:0.88rem">${i}</div>`).join('')||''}
      ${topRows ? `<table style="margin-top:1rem"><thead><tr><th>#</th><th>Job</th><th>Company</th><th>Fit</th><th>Response%</th><th>Action</th></tr></thead><tbody>${topRows}</tbody></table>` : ''}
    `;
  } catch(e) {
    content.innerHTML = `<div class="empty">Error loading report: ${e.message}</div>`;
  }
  section.scrollIntoView({behavior:'smooth'});
}

// ── Init ───────────────────────────────────────────────────────────────────
connectWS();
loadJobs();
loadStats();
setInterval(loadStats, 30000);
</script>
</body>
</html>
"""
