import json
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from opengtm.analytics import run_health_check
from opengtm.qualify import qualify as _qualify

app = FastAPI(title="OpenGTM", version="0.1.0")

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OpenGTM - AEO Health Check</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0a0a0b; color: #e4e4e7; min-height: 100vh;
      display: flex; flex-direction: column; align-items: center;
    }
    .container { max-width: 800px; width: 100%; padding: 2rem 1.5rem; }
    header { text-align: center; margin-bottom: 2.5rem; }
    h1 { font-size: 2rem; font-weight: 700; background: linear-gradient(135deg, #a78bfa, #60a5fa);
         -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    p.sub { color: #71717a; margin-top: 0.5rem; font-size: 0.95rem; }
    .card { background: #18181b; border: 1px solid #27272a; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }
    .input-group { display: flex; gap: 0.75rem; }
    input[type="url"] {
      flex: 1; padding: 0.75rem 1rem; border-radius: 8px; border: 1px solid #27272a;
      background: #09090b; color: #e4e4e7; font-size: 1rem; outline: none; transition: border 0.2s;
    }
    input[type="url"]:focus { border-color: #a78bfa; }
    input[type="url"]::placeholder { color: #52525b; }
    button {
      padding: 0.75rem 1.5rem; border-radius: 8px; border: none;
      background: linear-gradient(135deg, #a78bfa, #60a5fa); color: white; font-weight: 600;
      font-size: 0.95rem; cursor: pointer; transition: opacity 0.2s; white-space: nowrap;
    }
    button:hover { opacity: 0.9; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .loader { display: none; text-align: center; padding: 2rem; }
    .loader.active { display: block; }
    .spinner { width: 32px; height: 32px; border: 3px solid #27272a; border-top-color: #a78bfa;
               border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 1rem; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .result { display: none; }
    .result.active { display: block; }
    .score-header { display: flex; align-items: center; gap: 1.5rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
    .grade-circle {
      width: 80px; height: 80px; border-radius: 50%; display: flex; align-items: center;
      justify-content: center; font-size: 2rem; font-weight: 700; flex-shrink: 0;
    }
    .stats { flex: 1; }
    .stat-row { display: flex; justify-content: space-between; margin-bottom: 0.5rem; font-size: 0.9rem; }
    .stat-row .label { color: #71717a; }
    .stat-row .value { font-weight: 600; }
    .grade-label { font-size: 1.1rem; font-weight: 600; margin-bottom: 0.25rem; }
    .bar { height: 6px; background: #27272a; border-radius: 3px; overflow: hidden; margin: 0.5rem 0 1rem; }
    .bar-fill { height: 100%; border-radius: 3px; transition: width 0.6s ease; }
    .issues { margin-top: 1rem; }
    .issue { padding: 0.75rem; border-radius: 8px; margin-bottom: 0.5rem; font-size: 0.9rem;
             border-left: 3px solid; background: #09090b; }
    .issue.error { border-color: #ef4444; }
    .issue.warning { border-color: #eab308; }
    .issue.notice { border-color: #3b82f6; }
    .issue .issue-header { display: flex; justify-content: space-between; margin-bottom: 0.25rem; }
    .issue .issue-title { font-weight: 600; }
    .issue .issue-severity { font-size: 0.8rem; padding: 0.15rem 0.5rem; border-radius: 4px; text-transform: uppercase; }
    .issue .issue-recommendation { color: #71717a; font-size: 0.85rem; margin-top: 0.25rem; }
    .severity-error { background: rgba(239,68,68,0.15); color: #fca5a5; }
    .severity-warning { background: rgba(234,179,8,0.15); color: #fde047; }
    .severity-notice { background: rgba(59,130,246,0.15); color: #93c5fd; }
    .error-msg { color: #ef4444; text-align: center; padding: 1rem; }
    .endpoints { text-align: center; margin-top: 1rem; }
    .endpoints a { color: #60a5fa; text-decoration: none; font-size: 0.85rem; }
    .endpoints a:hover { text-decoration: underline; }
    .badge-row { display: flex; gap: 0.5rem; justify-content: center; margin-top: 0.75rem; flex-wrap: wrap; }
    .badge-row img { height: 22px; }
    footer { text-align: center; padding: 2rem 0; color: #52525b; font-size: 0.85rem; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>OpenGTM</h1>
      <p class="sub">AEO Health Check — Analyze how well AI can find & understand your pages</p>
      <div class="badge-row">
        <a href="https://github.com/Austecch/opengtm"><img src="https://img.shields.io/badge/Open%20Source-MIT-blue" alt="MIT"></a>
        <a href="/health"><img src="https://img.shields.io/badge/API-Online-brightgreen" alt="API Status"></a>
      </div>
    </header>

    <div class="card">
      <div class="input-group">
        <input type="url" id="urlInput" placeholder="https://example.com" value="https://example.com">
        <button id="runBtn" onclick="runCheck()">Run Check</button>
      </div>
    </div>

    <div class="loader" id="loader">
      <div class="spinner"></div>
      <p>Analyzing page...</p>
    </div>

    <div class="result" id="result"></div>

    <div class="endpoints">
      <a href="/health">Health Check</a> &middot;
      <a href="https://github.com/Austecch/opengtm">GitHub</a> &middot;
      <a href="mailto:pnt01@foxmail.com">Contact</a>
    </div>

    <footer>OpenGTM &mdash; MIT Licensed &mdash; Built with FastAPI</footer>
  </div>

  <script>
    async function runCheck() {
      const url = document.getElementById('urlInput').value.trim();
      if (!url) return;
      const btn = document.getElementById('runBtn');
      const loader = document.getElementById('loader');
      const result = document.getElementById('result');
      btn.disabled = true;
      loader.classList.add('active');
      result.classList.remove('active');
      try {
        const res = await fetch('/aeo-health?url=' + encodeURIComponent(url));
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        renderResult(data);
      } catch (e) {
        result.innerHTML = '<div class="card error-msg">Error: ' + e.message + '</div>';
        result.classList.add('active');
      } finally {
        btn.disabled = false;
        loader.classList.remove('active');
      }
    }

    function renderResult(data) {
      const gradeColors = { A: '#22c55e', B: '#84cc16', C: '#eab308', D: '#f97316', F: '#ef4444' };
      const color = gradeColors[data.grade?.[0]] || '#71717a';
      const passed = data.checks_passed || 0;
      const failed = data.checks_failed || 0;
      const total = passed + failed;

      let issuesHtml = '';
      const order = { error: 0, warning: 1, notice: 2 };
      const issues = (data.issues || []).sort((a, b) => (order[a.severity] || 3) - (order[b.severity] || 3));
      for (const issue of issues) {
        const sev = issue.severity || 'notice';
        issuesHtml += '<div class="issue ' + sev + '">' +
          '<div class="issue-header">' +
          '<span class="issue-title">' + escapeHtml(issue.check) + '</span>' +
          '<span class="issue-severity severity-' + sev + '">' + sev + '</span>' +
          '</div>' +
          '<div>' + escapeHtml(issue.message || '') + '</div>' +
          (issue.recommendation ? '<div class="issue-recommendation">\u2192 ' + escapeHtml(issue.recommendation) + '</div>' : '') +
          '</div>';
      }

      const html = '<div class="score-header">' +
        '<div class="grade-circle" style="background:' + color + '20; color:' + color + '; border: 3px solid ' + color + '">' +
        data.grade + '</div>' +
        '<div class="stats">' +
        '<div class="grade-label" style="color:' + color + '">' + data.band + '</div>' +
        '<div class="stat-row"><span class="label">Score</span><span class="value">' + data.score + '/' + data.max_score + '</span></div>' +
        '<div class="stat-row"><span class="label">Passed</span><span class="value" style="color:#22c55e">' + passed + '/' + total + '</span></div>' +
        '<div class="stat-row"><span class="label">Failed</span><span class="value" style="color:#ef4444">' + failed + '/' + total + '</span></div>' +
        '</div></div>' +
        '<div class="bar"><div class="bar-fill" style="width:' + ((data.score / data.max_score) * 100) + '%; background:' + color + '"></div></div>';

      const finalHtml = '<div class="card">' + html + '</div>' +
        (issuesHtml ? '<div class="card"><h3 style="margin-bottom:1rem;font-size:1.1rem">Issues (' + issues.length + ')</h3><div class="issues">' + issuesHtml + '</div></div>' : '');

      document.getElementById('result').innerHTML = finalHtml;
      document.getElementById('result').classList.add('active');
    }

    function escapeHtml(t) {
      const d = document.createElement('div');
      d.textContent = t || '';
      return d.innerHTML;
    }

    document.getElementById('urlInput').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') runCheck();
    });

    // Run initial check on load
    window.addEventListener('load', function() {
      document.getElementById('urlInput').value = 'https://example.com';
      setTimeout(runCheck, 300);
    });
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def root():
    return HTML

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/aeo-health")
def aeo_health(url: str = Query(..., description="URL to analyze"), timeout: float = 30.0):
    result = run_health_check(url, timeout=timeout)
    return result

@app.post("/score-lead")
def score_lead(lead: dict, icp_profile: str = "default", custom_profile: dict = None):
    result = _qualify(lead, icp_profile=icp_profile, custom_profile=custom_profile)
    return result
