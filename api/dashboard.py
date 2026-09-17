"""
CareerPilot — Advanced Glassmorphic Dashboard Frontend
======================================================
Features:
- 100% Toast Notifications (No native browser alerts)
- Interactive Outreach Kit Modal with tabbed preview & individual copy buttons
- Autonomous Auto-Apply Mode Toggle Switcher
- Cover Letter & Resume ATS Match Visualizer
- Profile AI Optimizer & Goal Dispatcher
"""

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CareerPilot — AI Job & Internship Application System</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet"/>
<style>
  :root {
    --bg: #0b0c10;
    --surface: #14161f;
    --surface2: #1e2230;
    --border: rgba(255,255,255,0.08);
    --accent: #6c63ff;
    --accent2: #00d4ff;
    --accent3: #ff4757;
    --green: #2ed573;
    --yellow: #ffa502;
    --text: #f1f2f6;
    --text-dim: #9aa0a6;
    --radius: 16px;
    --glow: 0 0 25px rgba(108,99,255,0.25);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding-bottom: 4rem; }

  header {
    background: rgba(20, 22, 31, 0.85);
    backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--border);
    padding: 0 2rem;
    display: flex; align-items: center; justify-content: space-between;
    height: 70px; position: sticky; top: 0; z-index: 100;
  }
  .logo { display: flex; align-items: center; gap: 12px; font-weight: 900; font-size: 1.3rem; letter-spacing: -0.02em;
          background: linear-gradient(90deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .logo-icon { width: 36px; height: 36px; background: linear-gradient(135deg, var(--accent), var(--accent2));
               border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; color: #fff; box-shadow: var(--glow); }

  .header-actions { display: flex; align-items: center; gap: 16px; }
  .status-pill { display: flex; align-items: center; gap: 8px; background: var(--surface2); padding: 6px 14px; border-radius: 30px; font-size: 0.8rem; border: 1px solid var(--border); }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 10px var(--green); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

  .mode-switch { background: var(--surface2); border: 1px solid var(--border); border-radius: 20px; padding: 4px; display: flex; gap: 4px; }
  .mode-btn { background: none; border: none; color: var(--text-dim); padding: 5px 12px; border-radius: 16px; font-size: 0.75rem; font-weight: 700; cursor: pointer; transition: all 0.2s; }
  .mode-btn.active { background: var(--accent); color: #fff; box-shadow: var(--glow); }

  .container { max-width: 1400px; margin: 0 auto; padding: 2rem; }

  /* ── Agent Fleet Status ── */
  .fleet-bar { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }
  .agent-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.25rem; display: flex; align-items: center; gap: 1rem; }
  .agent-avatar { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; background: var(--surface2); border: 1px solid var(--border); }
  .agent-info h4 { font-size: 0.95rem; font-weight: 700; color: var(--text); }
  .agent-info p { font-size: 0.75rem; color: var(--text-dim); margin-top: 2px; }

  /* ── Grid Layouts ── */
  .grid-profile { display: grid; grid-template-columns: 1fr 2fr; gap: 1.5rem; margin-bottom: 2rem; }
  @media(max-width: 1024px) { .grid-profile, .fleet-bar { grid-template-columns: 1fr; } }

  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.5rem; }
  .card-title { font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--accent2); margin-bottom: 1rem; display: flex; align-items: center; justify-content: space-between; }

  /* ── Profile Editor ── */
  .profile-form label { font-size: 0.78rem; font-weight: 600; color: var(--text-dim); display: block; margin-top: 0.75rem; margin-bottom: 0.35rem; }
  .input-field { width: 100%; background: var(--surface2); border: 1px solid var(--border); border-radius: 10px; color: var(--text); padding: 0.65rem 0.9rem; font-size: 0.88rem; outline: none; transition: border-color 0.2s; }
  .input-field:focus { border-color: var(--accent); }

  /* ── Action buttons & Presets ── */
  .btn { background: linear-gradient(135deg, var(--accent), #8b5cf6); color: #fff; font-weight: 700; font-size: 0.88rem; padding: 0.7rem 1.4rem; border: none; border-radius: 10px; cursor: pointer; transition: all 0.2s; display: inline-flex; align-items: center; gap: 8px; }
  .btn:hover { opacity: 0.92; transform: translateY(-1px); box-shadow: var(--glow); }
  .btn-secondary { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
  .btn-secondary:hover { background: rgba(255,255,255,0.06); }
  .btn-apply { background: linear-gradient(135deg, var(--green), #20bf6b); color: #052c14; font-weight: 800; }
  .btn-apply:hover { box-shadow: 0 0 20px rgba(46,213,115,0.3); }

  .presets-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 1rem; }
  .preset-chip { background: var(--surface2); border: 1px solid var(--border); color: var(--text-dim); padding: 6px 12px; border-radius: 20px; font-size: 0.78rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
  .preset-chip:hover { border-color: var(--accent2); color: var(--accent2); }

  /* ── Tabs & Search ── */
  .tab-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem; }
  .tabs { display: flex; gap: 8px; background: var(--surface); padding: 6px; border-radius: 14px; border: 1px solid var(--border); }
  .tab { padding: 8px 18px; border-radius: 10px; font-size: 0.85rem; font-weight: 700; color: var(--text-dim); cursor: pointer; transition: all 0.2s; }
  .tab.active { background: var(--accent); color: #fff; box-shadow: var(--glow); }
  .search-box { display: flex; gap: 8px; width: 320px; }

  /* ── Jobs Grid ── */
  .jobs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 1.25rem; }
  .job-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.35rem; display: flex; flex-direction: column; justify-content: space-between; transition: all 0.2s; }
  .job-card:hover { border-color: var(--accent); transform: translateY(-3px); box-shadow: var(--glow); }

  .job-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
  .job-title { font-size: 1.05rem; font-weight: 800; color: var(--text); line-height: 1.3; }
  .company-name { font-size: 0.85rem; font-weight: 600; color: var(--text-dim); margin-top: 3px; }

  .badges { display: flex; gap: 6px; flex-wrap: wrap; margin: 0.8rem 0; }
  .badge { font-size: 0.7rem; font-weight: 800; text-transform: uppercase; padding: 4px 9px; border-radius: 6px; }
  .badge-intern { background: rgba(0,212,255,0.15); color: var(--accent2); border: 1px solid rgba(0,212,255,0.3); }
  .badge-job { background: rgba(108,99,255,0.15); color: var(--accent); border: 1px solid rgba(108,99,255,0.3); }
  .badge-fit { background: rgba(46,213,115,0.15); color: var(--green); border: 1px solid rgba(46,213,115,0.3); }
  .badge-remote { background: rgba(255,165,2,0.15); color: var(--yellow); border: 1px solid rgba(255,165,2,0.3); }

  .job-skills { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 1rem; }
  .job-skill-chip { font-size: 0.72rem; background: var(--surface2); color: var(--text-dim); padding: 3px 8px; border-radius: 6px; }

  .job-footer { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border); padding-top: 0.9rem; margin-top: 0.5rem; gap: 6px; flex-wrap: wrap; }
  .source-link { font-size: 0.75rem; color: var(--text-dim); text-decoration: none; }
  .source-link:hover { color: var(--accent2); }

  /* ── Modal & Drawer ── */
  .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.82); backdrop-filter: blur(12px); display: none; align-items: center; justify-content: center; z-index: 1000; padding: 1.5rem; }
  .modal-content { background: var(--surface); border: 1px solid var(--border); border-radius: 24px; width: 100%; max-width: 760px; max-height: 88vh; overflow-y: auto; padding: 2rem; box-shadow: 0 25px 60px rgba(0,0,0,0.6); }
  .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; }
  .modal-title { font-size: 1.25rem; font-weight: 800; color: var(--text); }
  .modal-close { font-size: 1.5rem; color: var(--text-dim); cursor: pointer; border: none; background: none; }

  .outreach-tabs { display: flex; gap: 8px; margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
  .outreach-tab { padding: 6px 14px; border-radius: 8px; font-size: 0.8rem; font-weight: 700; color: var(--text-dim); cursor: pointer; }
  .outreach-tab.active { background: var(--surface2); color: var(--accent2); border: 1px solid var(--border); }

  .cover-box { background: var(--surface2); border: 1px solid var(--border); border-radius: 12px; padding: 1.2rem; font-family: monospace; font-size: 0.85rem; white-space: pre-wrap; color: #dfe4ea; margin: 1rem 0; line-height: 1.6; max-height: 400px; overflow-y: auto; }

  /* ── Applications Table ── */
  table { width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.88rem; }
  th { text-align: left; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); color: var(--text-dim); font-size: 0.75rem; text-transform: uppercase; }
  td { padding: 0.85rem 1rem; border-bottom: 1px solid var(--border); }

  /* ── Toast Container ── */
  #toast-container { position: fixed; bottom: 24px; right: 24px; z-index: 9999; display: flex; flex-direction: column; gap: 10px; pointer-events: none; }
  .toast { background: rgba(20, 22, 31, 0.95); border: 1px solid var(--green); color: var(--text); padding: 12px 20px; border-radius: 12px; font-size: 0.88rem; font-weight: 600; box-shadow: 0 10px 30px rgba(0,0,0,0.5), 0 0 15px rgba(46,213,115,0.3); backdrop-filter: blur(12px); display: flex; align-items: center; gap: 10px; transform: translateY(20px); opacity: 0; transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); pointer-events: auto; }
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-icon">🚀</div>
    <span>CareerPilot AI</span>
  </div>

  <div class="header-actions">
    <div class="mode-switch">
      <button class="mode-btn" onclick="setMode('manual', this)">⚡ Manual</button>
      <button class="mode-btn active" onclick="setMode('auto', this)">🟢 Auto-Apply (>70% Fit)</button>
      <button class="mode-btn" onclick="setMode('autonomous', this)">🤖 Fully Autonomous</button>
    </div>

    <div class="status-pill">
      <div class="status-dot"></div>
      <span>4 Agents Active</span>
    </div>
  </div>
</header>

<div class="container">

  <!-- Agent Fleet Status -->
  <div class="fleet-bar">
    <div class="agent-card">
      <div class="agent-avatar">🎯</div>
      <div class="agent-info">
        <h4>Commander Agent</h4>
        <p id="st-commander">Goal orchestrator active</p>
      </div>
    </div>
    <div class="agent-card">
      <div class="agent-avatar">🔍</div>
      <div class="agent-info">
        <h4>Tracker Agent</h4>
        <p id="st-tracker">Scrape & DB indexing</p>
      </div>
    </div>
    <div class="agent-card">
      <div class="agent-avatar">🔮</div>
      <div class="agent-info">
        <h4>Predictor Agent</h4>
        <p id="st-predictor">Skill fit scoring engine</p>
      </div>
    </div>
    <div class="agent-card">
      <div class="agent-avatar">⚡</div>
      <div class="agent-info">
        <h4>Applier Agent</h4>
        <p id="st-applier">LinkedIn, Mail & Call Outreach</p>
      </div>
    </div>
  </div>

  <!-- Goal & Profile Grid -->
  <div class="grid-profile">
    
    <!-- Profile Editor Card -->
    <div class="card">
      <div class="card-title">
        <span>👤 Candidate Profile & Contact Details</span>
        <div style="display:flex;gap:6px">
          <button class="btn btn-secondary" style="padding:4px 10px;font-size:0.75rem;background:linear-gradient(135deg,var(--accent2),#00a8ff);color:#051b2c;font-weight:800" onclick="optimizeProfile()">✨ AI Optimizer</button>
          <button class="btn btn-secondary" style="padding:4px 10px;font-size:0.75rem" onclick="saveProfile()">Save</button>
        </div>
      </div>
      <form class="profile-form" onsubmit="event.preventDefault(); saveProfile();">
        <label>Full Name</label>
        <input type="text" id="prof-name" class="input-field" value="Janardhan Devarala"/>
        
        <label>Contact Email (Direct Outreach)</label>
        <input type="email" id="prof-email" class="input-field" value="devaralajanardhan@gmail.com"/>

        <label>Phone Number (Recruiter Pitch)</label>
        <input type="text" id="prof-phone" class="input-field" value="+91 9876543210"/>

        <label>Target Roles</label>
        <input type="text" id="prof-roles" class="input-field" value="Data Analyst, Python Developer, Financial Analyst, AI Engineer"/>

        <label>Skills (comma separated)</label>
        <input type="text" id="prof-skills" class="input-field" value="Python, SQL, Data Analysis, Machine Learning, PowerBI, Scikit-learn, Financial Analysis, Pandas, NumPy, FastAPI, Docker, Git"/>

        <div style="display:flex;align-items:center;gap:10px;margin-top:1rem">
          <input type="checkbox" id="prof-intern" checked style="width:18px;height:18px;accent-color:var(--accent2)"/>
          <label for="prof-intern" style="margin:0;cursor:pointer;color:var(--text);font-size:0.85rem">Target Internships & Freshers</label>
        </div>
      </form>
    </div>

    <!-- Goal Submission & Quick Actions -->
    <div class="card">
      <div class="card-title">⚡ Agent Goal Dispatcher</div>
      <p style="font-size:0.85rem;color:var(--text-dim);margin-bottom:1rem">
        Instruct the Commander Agent to hunt, score, and queue applications for specific roles & locations.
      </p>

      <div style="display:flex;gap:10px;margin-bottom:1rem">
        <input type="text" id="goal-input" class="input-field" placeholder="e.g. Find 20 Machine Learning internships in Bangalore and score fit" style="flex:1"/>
        <button class="btn" onclick="dispatchGoal()">Run Goal</button>
      </div>

      <div style="font-size:0.78rem;font-weight:700;color:var(--text-dim)">QUICK PRESETS:</div>
      <div class="presets-bar">
        <div class="preset-chip" onclick="setGoal('Find 20 Data Analyst and Python Developer jobs in Hyderabad')">📍 Hyderabad Roles</div>
        <div class="preset-chip" onclick="setGoal('Find 15 AI Engineer Remote Jobs with high fit score')">🌐 Remote AI Jobs</div>
        <div class="preset-chip" onclick="setGoal('Find 20 Data Scientist & Machine Learning Jobs in Bangalore')">📍 Bangalore Data Roles</div>
        <div class="preset-chip" onclick="setGoal('Match candidate skills against all 36 tracked jobs')">⚡ Rescore All Jobs</div>
      </div>
    </div>
  </div>

  <!-- Tab Bar & Job Search -->
  <div class="tab-bar">
    <div class="tabs">
      <div class="tab active" id="tab-all" onclick="switchTab('all')">All Opportunities (<span id="cnt-all">0</span>)</div>
      <div class="tab" id="tab-internship" onclick="switchTab('internship')">🎓 Internships</div>
      <div class="tab" id="tab-fulltime" onclick="switchTab('fulltime')">💼 Full-Time Jobs</div>
      <div class="tab" id="tab-applications" onclick="switchTab('applications')">📑 My Applications (<span id="cnt-apps">0</span>)</div>
    </div>

    <div class="search-box">
      <input type="text" id="search-input" class="input-field" placeholder="Search by title, company, skills..." onkeyup="filterJobs()"/>
    </div>
  </div>

  <!-- Jobs Grid Container -->
  <div id="jobs-container" class="jobs-grid">
    <div style="grid-column: 1/-1; text-align:center; padding: 3rem; color: var(--text-dim);">
      Loading opportunities matching your skills...
    </div>
  </div>

  <!-- Applications Table Container -->
  <div id="apps-container" class="card" style="display:none">
    <div class="card-title">📑 Applications Submitted by Applier Agent</div>
    <div id="apps-table-wrap">Loading application status history...</div>
  </div>

</div>

<!-- Apply Modal -->
<div id="apply-modal" class="modal-overlay">
  <div class="modal-content">
    <div class="modal-header">
      <div class="modal-title" id="modal-title">Applier Agent Executing 1-Click Fast Apply...</div>
      <button class="modal-close" onclick="closeModal('apply-modal')">✕</button>
    </div>
    <p style="font-size:0.85rem;color:var(--text-dim)">Tailored Resume & Cover Letter generated by ResumeBuilder:</p>
    <div class="cover-box" id="modal-cover">Generating ATS-optimized cover letter matching Janardhan's candidate profile...</div>
    <div style="display:flex;justify-content:flex-end;gap:10px">
      <button class="btn btn-secondary" onclick="copyCoverLetter()">📋 Copy Cover Letter</button>
      <button class="btn" onclick="closeModal('apply-modal')">Done</button>
    </div>
  </div>
</div>

<!-- Outreach Kit Modal -->
<div id="outreach-modal" class="modal-overlay">
  <div class="modal-content">
    <div class="modal-header">
      <div class="modal-title" id="outreach-title">📬 Recruiter Outreach Package</div>
      <button class="modal-close" onclick="closeModal('outreach-modal')">✕</button>
    </div>

    <div class="outreach-tabs">
      <div class="outreach-tab active" id="otab-email" onclick="switchOutreachTab('email')">✉️ Cold Email</div>
      <div class="outreach-tab" id="otab-linkedin" onclick="switchOutreachTab('linkedin')">🔗 LinkedIn Note</div>
      <div class="outreach-tab" id="otab-phone" onclick="switchOutreachTab('phone')">📞 Phone Pitch</div>
    </div>

    <div id="obox-email" class="cover-box">Loading cold email pitch...</div>
    <div id="obox-linkedin" class="cover-box" style="display:none">Loading LinkedIn note...</div>
    <div id="obox-phone" class="cover-box" style="display:none">Loading phone call script...</div>

    <div style="display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:0.75rem;color:var(--text-dim)">✨ Complete package ready for recruiter outreach</span>
      <div style="display:flex;gap:10px">
        <button class="btn btn-secondary" onclick="copyOutreach()">📋 Copy Active Package</button>
        <button class="btn" onclick="closeModal('outreach-modal')">Close</button>
      </div>
    </div>
  </div>
</div>

<script>
let allJobs = [];
let allApps = [];
let currentTab = 'all';
let currentOutreachTab = 'email';

function showToast(message, type = 'success') {
  let toastContainer = document.getElementById('toast-container');
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'toast-container';
    document.body.appendChild(toastContainer);
  }
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.style.borderColor = type === 'success' ? 'var(--green)' : 'var(--accent2)';
  toast.style.boxShadow = `0 10px 30px rgba(0,0,0,0.5), 0 0 15px ${type === 'success' ? 'rgba(46,213,115,0.3)' : 'rgba(0,212,255,0.3)'}`;
  toast.innerHTML = `<span>${type === 'success' ? '✨' : '🚀'}</span> <span>${message}</span>`;
  toastContainer.appendChild(toast);

  requestAnimationFrame(() => {
    toast.style.transform = 'translateY(0)';
    toast.style.opacity = '1';
  });

  setTimeout(() => {
    toast.style.transform = 'translateY(20px)';
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function setMode(mode, btn) {
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  showToast(`Auto-Apply Mode updated to: ${mode.toUpperCase()}`, 'info');
}

async function loadProfile() {
  try {
    const res = await fetch('/api/profile');
    const p = await res.json();
    if(p.full_name) document.getElementById('prof-name').value = p.full_name;
    if(p.email) document.getElementById('prof-email').value = p.email;
    if(p.phone) document.getElementById('prof-phone').value = p.phone;
    if(p.target_roles) document.getElementById('prof-roles').value = p.target_roles.join(', ');
    if(p.skills) document.getElementById('prof-skills').value = p.skills.join(', ');
  } catch(e) {}
}

async function saveProfile() {
  const body = {
    full_name: document.getElementById('prof-name').value,
    email: document.getElementById('prof-email').value,
    phone: document.getElementById('prof-phone').value,
    target_roles: document.getElementById('prof-roles').value.split(',').map(s=>s.trim()).filter(Boolean),
    skills: document.getElementById('prof-skills').value.split(',').map(s=>s.trim()).filter(Boolean),
  };
  await fetch('/api/profile', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  showToast("Candidate profile saved & updated across all agents!", "success");
}

async function optimizeProfile() {
  showToast("AI Profile Optimizer analyzing target roles & resume...", "info");
  const res = await fetch('/api/profile/optimize', { method: 'POST' });
  const p = await res.json();
  loadProfile();
  showToast("Profile optimized! ATS keywords and skills enhanced.", "success");
}

async function loadJobs() {
  try {
    let url = '/api/jobs?per_page=60';
    if(currentTab === 'internship') url += '&job_type=internship';
    if(currentTab === 'fulltime') url += '&job_type=fulltime';
    const res = await fetch(url);
    const data = await res.json();
    allJobs = data.jobs || [];
    document.getElementById('cnt-all').innerText = allJobs.length;
    renderJobs(allJobs);
  } catch(e) {
    document.getElementById('jobs-container').innerHTML = `<p style="color:var(--accent3)">Error loading jobs: ${e.message}</p>`;
  }
}

async function loadApps() {
  try {
    const res = await fetch('/api/applications');
    allApps = await res.json();
    document.getElementById('cnt-apps').innerText = allApps.length;
    renderApps(allApps);
  } catch(e) {}
}

function getSkillList(raw) {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  if (typeof raw === 'string') return raw.split(' ').filter(Boolean);
  return [];
}

function renderJobs(jobs) {
  const container = document.getElementById('jobs-container');
  if (!jobs.length) {
    container.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:3rem; color:var(--text-dim)">No opportunities found in this category. Use Agent Goal Dispatcher above to hunt new jobs!</div>`;
    return;
  }
  container.innerHTML = jobs.map(j => {
    const isApplied = allApps.some(a => a.job_id === j.id);
    const fit = Math.round(j.fit_score || 75);
    const fitClass = fit >= 70 ? 'badge-fit' : (fit >= 50 ? 'badge-remote' : 'badge-job');
    const skills = getSkillList(j.matched_skills).slice(0, 5);

    return `
      <div class="job-card">
        <div>
          <div class="job-header">
            <div>
              <div class="job-title">${j.title}</div>
              <div class="company-name">🏢 ${j.company} &nbsp;•&nbsp; 📍 ${j.location}</div>
            </div>
            <span class="badge ${fitClass}">${fit}% FIT</span>
          </div>
          <div class="badges">
            ${j.is_internship ? '<span class="badge badge-intern">🎓 Internship</span>' : '<span class="badge badge-job">💼 Full-Time</span>'}
            ${j.is_remote ? '<span class="badge badge-remote">🌐 Remote</span>' : ''}
            ${j.easy_apply ? '<span class="badge badge-fit">⚡ Easy Apply</span>' : ''}
          </div>
          <div class="job-skills">
            ${skills.map(s => `<span class="job-skill-chip">${s}</span>`).join('')}
          </div>
        </div>
        <div class="job-footer">
          <a class="source-link" href="${j.source_url || '#'}" target="_blank">🔗 Details</a>
          <button class="btn btn-secondary" style="font-size:0.75rem;padding:5px 9px;" onclick="openOutreachModal('${j.id}')">📬 Outreach Kit</button>
          ${isApplied ? 
            `<button class="btn btn-secondary" style="font-size:0.75rem;padding:5px 9px;cursor:default" disabled>✅ Applied</button>` :
            `<button class="btn btn-apply" style="font-size:0.75rem;padding:5px 9px;" onclick="fastApply('${j.id}')">⚡ 1-Click Apply</button>`
          }
        </div>
      </div>
    `;
  }).join('');
}

function renderApps(apps) {
  const container = document.getElementById('apps-table-wrap');
  if (!apps.length) {
    container.innerHTML = `<p style="color:var(--text-dim);padding:1rem">No applications submitted yet. Click "⚡ 1-Click Apply" on any job or internship!</p>`;
    return;
  }
  container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Job / Internship</th>
          <th>Company</th>
          <th>Status</th>
          <th>Fit Score</th>
          <th>Applied Date</th>
          <th>Cover Letter</th>
        </tr>
      </thead>
      <tbody>
        ${apps.map(a => `
          <tr>
            <td><strong>${a.job_title}</strong></td>
            <td>${a.company}</td>
            <td><span class="badge badge-fit">${a.status}</span></td>
            <td><strong style="color:var(--green)">${a.fit_score || 85}%</strong></td>
            <td>${a.applied_at ? new Date(a.applied_at).toLocaleDateString() : 'Just now'}</td>
            <td><button class="btn btn-secondary" style="font-size:0.72rem;padding:4px 8px" onclick="viewCover('${a.id}')">View Letter</button></td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

async function fastApply(jobId) {
  showToast("Applier Agent generating ATS Cover Letter & applying...", "info");
  const modal = document.getElementById('apply-modal');
  document.getElementById('modal-title').innerText = "Applier Agent Working...";
  document.getElementById('modal-cover').innerText = "Generating tailored cover letter matching candidate profile skills...";
  modal.style.display = 'flex';

  try {
    const res = await fetch('/api/jobs/apply', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ job_id: jobId })
    });
    const app = await res.json();
    document.getElementById('modal-title').innerText = `✅ Applied to ${app.company}!`;
    document.getElementById('modal-cover').innerText = app.cover_letter;
    await loadApps();
    await loadJobs();
    showToast(`Successfully applied to ${app.company}! SMS alert dispatched.`, "success");
  } catch(e) {
    document.getElementById('modal-cover').innerText = "Error applying: " + e.message;
    showToast("Application failed: " + e.message, "info");
  }
}

async function openOutreachModal(jobId) {
  const modal = document.getElementById('outreach-modal');
  document.getElementById('outreach-title').innerText = "Applier Agent Generating Outreach Package...";
  document.getElementById('obox-email').innerText = "Loading cold email pitch...";
  document.getElementById('obox-linkedin').innerText = "Loading LinkedIn connection note...";
  document.getElementById('obox-phone').innerText = "Loading call script & recruiter contact info...";
  modal.style.display = 'flex';

  try {
    const res = await fetch(`/api/jobs/${jobId}/outreach`);
    const data = await res.json();
    document.getElementById('outreach-title').innerText = `📬 Recruiter Kit: ${data.job_title} @ ${data.company}`;
    document.getElementById('obox-email').innerText = `SUBJECT: ${data.email_subject}\n\n${data.email_body}`;
    document.getElementById('obox-linkedin').innerText = data.linkedin_note;
    document.getElementById('obox-phone').innerText = data.phone_script;
  } catch(e) {
    document.getElementById('obox-email').innerText = "Error generating outreach: " + e.message;
  }
}

function switchOutreachTab(tab) {
  currentOutreachTab = tab;
  document.querySelectorAll('.outreach-tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`otab-${tab}`).classList.add('active');

  document.getElementById('obox-email').style.display = tab === 'email' ? 'block' : 'none';
  document.getElementById('obox-linkedin').style.display = tab === 'linkedin' ? 'block' : 'none';
  document.getElementById('obox-phone').style.display = tab === 'phone' ? 'block' : 'none';
}

function viewCover(appId) {
  const app = allApps.find(a => a.id === appId);
  if (!app) return;
  document.getElementById('modal-title').innerText = `Cover Letter for ${app.job_title}`;
  document.getElementById('modal-cover').innerText = app.cover_letter || "Cover letter submitted successfully.";
  document.getElementById('apply-modal').style.display = 'flex';
}

function closeModal(id) {
  document.getElementById(id).style.display = 'none';
}

function copyCoverLetter() {
  const text = document.getElementById('modal-cover').innerText;
  navigator.clipboard.writeText(text);
  showToast("Cover letter copied to clipboard!", "success");
}

function copyOutreach() {
  let activeText = "";
  if (currentOutreachTab === 'email') activeText = document.getElementById('obox-email').innerText;
  else if (currentOutreachTab === 'linkedin') activeText = document.getElementById('obox-linkedin').innerText;
  else activeText = document.getElementById('obox-phone').innerText;

  navigator.clipboard.writeText(activeText);
  showToast(`Copied ${currentOutreachTab.toUpperCase()} template to clipboard!`, "success");
}

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.add('active');

  if (tab === 'applications') {
    document.getElementById('jobs-container').style.display = 'none';
    document.getElementById('apps-container').style.display = 'block';
    loadApps();
  } else {
    document.getElementById('apps-container').style.display = 'none';
    document.getElementById('jobs-container').style.display = 'grid';
    loadJobs();
  }
}

function filterJobs() {
  const query = document.getElementById('search-input').value.toLowerCase();
  const filtered = allJobs.filter(j => {
    const titleMatch = (j.title || '').toLowerCase().includes(query);
    const companyMatch = (j.company || '').toLowerCase().includes(query);
    const skillsList = getSkillList(j.matched_skills);
    const skillMatch = skillsList.some(s => String(s).toLowerCase().includes(query));
    return titleMatch || companyMatch || skillMatch;
  });
  renderJobs(filtered);
}

function setGoal(txt) {
  document.getElementById('goal-input').value = txt;
  dispatchGoal();
}

async function dispatchGoal() {
  const goal = document.getElementById('goal-input').value.trim();
  if(!goal) return;
  await fetch('/api/goal', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ goal })
  });
  showToast(`Goal submitted to Commander Agent: "${goal}"`, 'success');
}

loadProfile();
loadApps();
loadJobs();
</script>
</body>
</html>
"""
