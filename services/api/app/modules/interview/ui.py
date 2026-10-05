from __future__ import annotations

INTERVIEW_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PrepOS - AI Mock Interview Practice</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b1020;
      --card-bg: #111827;
      --card-border: #1f2937;
      --primary: #4f46e5;
      --primary-hover: #4338ca;
      --cyan: #06b6d4;
      --accent: #38bdf8;
      --text: #e2e8f0;
      --text-muted: #94a3b8;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: #0d1424;
      border-bottom: 1px solid var(--card-border);
      padding: 1rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .logo-badge {
      background: linear-gradient(135deg, #4f46e5, #06b6d4);
      color: white;
      font-weight: 700;
      padding: 0.35rem 0.65rem;
      border-radius: 8px;
      font-size: 0.9rem;
    }
    .brand h1 {
      font-size: 1.25rem;
      font-weight: 700;
      color: white;
      letter-spacing: -0.02em;
    }
    .brand span {
      color: var(--text-muted);
      font-size: 0.85rem;
      border-left: 1px solid var(--card-border);
      padding-left: 0.75rem;
    }
    .nav-links a {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.9rem;
      margin-left: 1.5rem;
      transition: color 0.2s;
    }
    .nav-links a:hover, .nav-links a.active {
      color: white;
    }
    main {
      flex: 1;
      max-width: 860px;
      width: 100%;
      margin: 2rem auto;
      padding: 0 1rem;
    }
    .panel {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 2.25rem;
      box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    }
    .eyebrow {
      color: var(--cyan);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      font-weight: 600;
      margin-bottom: 0.5rem;
    }
    h2 {
      font-size: 1.75rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 0.5rem;
    }
    p.subtitle {
      color: var(--text-muted);
      margin-bottom: 2rem;
      font-size: 0.98rem;
    }
    .setup-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1.25rem;
      margin-bottom: 2rem;
    }
    label {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      font-size: 0.88rem;
      color: var(--text-muted);
      font-weight: 500;
    }
    input, select, textarea {
      background: #1e293b;
      border: 1px solid #334155;
      color: white;
      padding: 0.85rem 1rem;
      border-radius: 10px;
      font-family: inherit;
      font-size: 0.95rem;
      transition: border-color 0.2s;
    }
    input:focus, select:focus, textarea:focus {
      outline: none;
      border-color: var(--primary);
    }
    button.btn {
      background: var(--primary);
      color: white;
      border: none;
      border-radius: 10px;
      padding: 0.85rem 1.5rem;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      transition: background 0.2s, transform 0.1s;
    }
    button.btn:hover { background: var(--primary-hover); }
    button.btn:active { transform: scale(0.98); }
    button.btn.mic {
      background: #312e81;
      border: 1px solid #4338ca;
    }
    button.btn.mic.recording {
      background: #991b1b;
      border-color: #ef4444;
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(1); }
      50% { transform: scale(1.04); }
      100% { transform: scale(1); }
    }
    .question-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 1rem;
    }
    .badge {
      background: #1e1b4b;
      color: #a5b4fc;
      border: 1px solid #3730a3;
      padding: 0.3rem 0.8rem;
      border-radius: 20px;
      font-size: 0.82rem;
      font-weight: 600;
    }
    .timer {
      color: var(--warning);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.95rem;
      background: #1e293b;
      padding: 0.3rem 0.75rem;
      border-radius: 8px;
    }
    .question-card {
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 12px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
    }
    .question-card h3 {
      font-size: 1.25rem;
      line-height: 1.6;
      color: #f8fafc;
    }
    .hint-box {
      margin-top: 1rem;
      color: var(--accent);
      font-size: 0.9rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .speech-bar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      margin-bottom: 0.75rem;
    }
    .speech-note {
      font-size: 0.85rem;
      color: var(--text-muted);
    }
    textarea {
      width: 100%;
      resize: vertical;
      min-height: 140px;
      margin-bottom: 1.5rem;
      line-height: 1.5;
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      gap: 1rem;
    }
    .rubric-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 1rem;
      margin: 1.5rem 0;
    }
    .rubric-meter {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 10px;
      padding: 1rem;
      text-align: center;
    }
    .rubric-meter span {
      display: block;
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-bottom: 0.4rem;
    }
    .rubric-meter strong {
      font-size: 1.4rem;
      color: #fff;
    }
    .rubric-meter.total {
      background: #1e1b4b;
      border-color: #4f46e5;
    }
    .rubric-meter.total strong {
      color: #a5b4fc;
    }
    .feedback-callout {
      background: #1e293b;
      border-left: 4px solid var(--cyan);
      border-radius: 0 10px 10px 0;
      padding: 1rem 1.25rem;
      margin-bottom: 1.5rem;
    }
    .feedback-callout strong {
      color: var(--cyan);
      display: block;
      margin-bottom: 0.35rem;
      font-size: 0.9rem;
    }
    .feedback-callout p {
      color: var(--text);
      font-size: 0.95rem;
      line-height: 1.5;
    }
    details {
      background: #0f172a;
      border: 1px dashed #334155;
      border-radius: 10px;
      padding: 1rem;
      margin-bottom: 1.5rem;
    }
    details summary {
      cursor: pointer;
      color: var(--accent);
      font-weight: 600;
      font-size: 0.92rem;
    }
    details p {
      margin-top: 0.75rem;
      color: #cbd5e1;
      font-size: 0.92rem;
      line-height: 1.6;
    }
    .score-banner {
      display: flex;
      align-items: center;
      gap: 2rem;
      background: linear-gradient(135deg, #1e1b4b, #0f172a);
      border: 1px solid #4338ca;
      border-radius: 14px;
      padding: 2rem;
      margin-bottom: 2rem;
    }
    .gauge {
      width: 105px;
      height: 105px;
      border-radius: 50%;
      background: #312e81;
      border: 4px solid var(--cyan);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }
    .gauge .number { font-size: 2.1rem; font-weight: 700; color: white; line-height: 1; }
    .gauge .denom { font-size: 0.75rem; color: #a5b4fc; }
    .summary-text h3 { font-size: 1.35rem; color: #fff; margin-bottom: 0.5rem; }
    .summary-text p { color: #cbd5e1; font-size: 0.95rem; line-height: 1.5; }
    .split-cards {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
      margin-bottom: 2rem;
    }
    .col-card {
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 12px;
      padding: 1.5rem;
    }
    .col-card h4 {
      font-size: 1rem;
      margin-bottom: 1rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .col-card.strengths h4 { color: var(--success); }
    .col-card.improvements h4 { color: var(--warning); }
    .col-card ul {
      padding-left: 1.25rem;
      color: #cbd5e1;
      font-size: 0.92rem;
      line-height: 1.7;
    }
    .error-toast {
      background: #450a0a;
      border: 1px solid var(--danger);
      color: #fca5a5;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      margin-bottom: 1rem;
      font-size: 0.9rem;
    }
    @media (max-width: 680px) {
      .split-cards { grid-template-columns: 1fr; }
      .score-banner { flex-direction: column; text-align: center; }
      header { flex-direction: column; gap: 0.75rem; align-items: flex-start; padding: 1rem; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="logo-badge">PrepOS</div>
      <h1>Adaptive Placement Preparation</h1>
      <span>Module 4: Mock Interview AI</span>
    </div>
    <div class="nav-links">
      <a href="/docs" target="_blank">API Docs</a>
      <a href="/interview/ui" class="active">Mock Interview</a>
    </div>
  </header>

  <main>
    <div id="error-container"></div>
    <div id="app-view"></div>
  </main>

  <script>
    const API_BASE = '';
    const DEV_TOKEN = 'Bearer dev-preview-token';

    let state = {
      view: 'setup', // 'setup', 'interview', 'feedback', 'report'
      roundType: 'technical',
      targetRole: 'Software Engineer',
      totalQuestions: 3,
      geminiKey: localStorage.getItem('prepos_gemini_key') || '',
      session: null,
      currentTurn: null,
      elapsedSeconds: 0,
      timerInterval: null,
      lastEvaluation: null,
      report: null,
      isRecording: false,
    };

    let recognition = null;
    let speechBaseText = '';
    let currentSessionFinal = '';
    let isUserManualStop = false;

    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      recognition.lang = 'en-US';

      recognition.onresult = (event) => {
        let interimStr = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const trans = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            currentSessionFinal += trans + ' ';
          } else {
            interimStr += trans;
          }
        }
        const textarea = document.getElementById('user-answer');
        if (textarea) {
          const base = speechBaseText ? speechBaseText.trim() + ' ' : '';
          textarea.value = (base + currentSessionFinal + interimStr).replace(/\\s+/g, ' ');
        }
      };

      recognition.onerror = (event) => {
        if (event.error === 'no-speech') return;
        if (event.error === 'not-allowed') {
          showError('Microphone blocked. Please allow mic permissions in the browser URL bar.');
          stopRecording();
        }
      };

      recognition.onend = () => {
        if (state.isRecording && !isUserManualStop) {
          try { recognition.start(); } catch (e) {}
        }
      };
    }

    function toggleRecording() {
      if (!recognition) {
        alert('Web Speech API is not supported in this browser. Please use Chrome or Edge.');
        return;
      }
      if (state.isRecording) {
        stopRecording();
      } else {
        const textarea = document.getElementById('user-answer');
        speechBaseText = textarea ? textarea.value.trim() : '';
        currentSessionFinal = '';
        isUserManualStop = false;
        try {
          recognition.start();
          state.isRecording = true;
          const micBtn = document.getElementById('mic-btn');
          if (micBtn) {
            micBtn.classList.add('recording');
            micBtn.innerHTML = '⏹ Stop Speaking';
          }
          const note = document.getElementById('speech-note');
          if (note) note.innerText = 'Listening... Speak clearly into your mic.';
        } catch (e) {
          console.error(e);
        }
      }
    }

    function stopRecording() {
      isUserManualStop = true;
      if (recognition && state.isRecording) {
        try { recognition.stop(); } catch (e) {}
      }
      state.isRecording = false;
      const textarea = document.getElementById('user-answer');
      if (textarea) {
        speechBaseText = textarea.value.trim();
      }
      const micBtn = document.getElementById('mic-btn');
      if (micBtn) {
        micBtn.classList.remove('recording');
        micBtn.innerHTML = '🎤 Speak Answer (Live STT)';
      }
      const note = document.getElementById('speech-note');
      if (note) note.innerText = 'Or type your answer directly in the box below:';
    }

    function showError(msg) {
      const c = document.getElementById('error-container');
      if (c) {
        c.innerHTML = `<div class="error-toast">⚠️ ${msg}</div>`;
        setTimeout(() => { c.innerHTML = ''; }, 6000);
      }
    }

    async function api(path, opts = {}) {
      opts.headers = opts.headers || {};
      opts.headers['Authorization'] = DEV_TOKEN;
      const key = state.geminiKey || localStorage.getItem('prepos_gemini_key');
      if (key) {
        opts.headers['X-Gemini-Key'] = key;
      }
      if (opts.body && typeof opts.body === 'object') {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(opts.body);
      }
      const res = await fetch(API_BASE + path, opts);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'API request failed');
      }
      return res.json();
    }

    async function startSession() {
      try {
        const payload = {
          round_type: state.roundType,
          target_role: state.targetRole,
          total_questions: Number(state.totalQuestions)
        };
        state.session = await api('/interview/sessions', { method: 'POST', body: payload });
        await fetchNextQuestion();
      } catch (err) {
        showError(err.message);
      }
    }

    async function fetchNextQuestion() {
      try {
        const res = await api(`/interview/sessions/${state.session.id}/next`);
        if (res.is_complete) {
          await completeSession();
        } else {
          state.currentTurn = res;
          state.view = 'interview';
          state.elapsedSeconds = 0;
          clearInterval(state.timerInterval);
          state.timerInterval = setInterval(() => {
            state.elapsedSeconds++;
            const t = document.getElementById('timer-val');
            if (t) t.innerText = state.elapsedSeconds + 's';
          }, 1000);
          render();
        }
      } catch (err) {
        showError(err.message);
      }
    }

    async function submitAnswer() {
      const textarea = document.getElementById('user-answer');
      const answer = textarea ? textarea.value.trim() : '';
      if (!answer) {
        showError('Please write or speak an answer before submitting.');
        return;
      }
      stopRecording();
      clearInterval(state.timerInterval);

      const submitBtn = document.getElementById('submit-btn');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = 'Evaluating with Rubric AI...';
      }

      try {
        const payload = {
          turn_number: state.currentTurn.turn_number,
          answer_transcript: answer,
          time_taken_s: state.elapsedSeconds
        };
        state.lastEvaluation = await api(`/interview/sessions/${state.session.id}/answer`, { method: 'POST', body: payload });
        state.view = 'feedback';
        render();
      } catch (err) {
        showError(err.message);
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerText = 'Submit Answer for Rubric Evaluation';
        }
      }
    }

    async function completeSession() {
      try {
        state.report = await api(`/interview/sessions/${state.session.id}/complete`, { method: 'POST' });
        state.view = 'report';
        render();
      } catch (err) {
        showError(err.message);
      }
    }

    function render() {
      const container = document.getElementById('app-view');
      if (state.view === 'setup') {
        container.innerHTML = `
          <div class="panel">
            <div class="eyebrow">AI Mock Interview Room</div>
            <h2>Practice Placement Rounds</h2>
            <p class="subtitle">Experience realistic technical and HR interview rounds with speech-to-text input, adaptive questioning, and rubric-based evaluations.</p>
            
            <div class="setup-grid">
              <label>
                <span>Round Type</span>
                <select id="round-type" onchange="state.roundType = this.value">
                  <option value="technical" ${state.roundType === 'technical' ? 'selected' : ''}>Technical (DSA, System Design, OS, DB)</option>
                  <option value="hr" ${state.roundType === 'hr' ? 'selected' : ''}>HR & Behavioral (STAR Method, Culture)</option>
                </select>
              </label>

              <label>
                <span>Target Role</span>
                <input type="text" id="target-role" value="${state.targetRole}" oninput="state.targetRole = this.value" placeholder="e.g. Software Engineer, Backend Engineer">
              </label>

              <label>
                <span>Question Count</span>
                <select id="total-questions" onchange="state.totalQuestions = Number(this.value)">
                  <option value="2" ${state.totalQuestions === 2 ? 'selected' : ''}>2 Questions (Quick Sprint)</option>
                  <option value="3" ${state.totalQuestions === 3 ? 'selected' : ''}>3 Questions (Standard Mock)</option>
                  <option value="5" ${state.totalQuestions === 5 ? 'selected' : ''}>5 Questions (Comprehensive)</option>
                </select>
              </label>

              <label>
                <span>Google Gemini API Key (Optional)</span>
                <input type="password" id="gemini-key" value="${state.geminiKey || ''}" oninput="state.geminiKey = this.value; localStorage.setItem('prepos_gemini_key', this.value);" placeholder="AIzaSy... (For Gemini LLM evaluation)">
              </label>
            </div>

            <button class="btn" onclick="startSession()">
              <span>🚀 Enter Interview Room</span>
            </button>
          </div>
        `;
      } else if (state.view === 'interview') {
        const q = state.currentTurn.question;
        container.innerHTML = `
          <div class="panel">
            <div class="question-header">
              <div>
                <span class="eyebrow">${state.roundType.toUpperCase()} ROUND</span>
                <span class="badge">${q.topic}</span>
              </div>
              <div style="display:flex; align-items:center; gap:0.75rem;">
                <span style="color:var(--text-muted); font-size:0.9rem;">Question ${q.turn_number} of ${state.currentTurn.total_questions}</span>
                <span class="timer" id="timer-val">${state.elapsedSeconds}s</span>
              </div>
            </div>

            <div class="question-card">
              <h3>${q.question}</h3>
              ${q.context_hint ? `<div class="hint-box">💡 Hint: ${q.context_hint}</div>` : ''}
            </div>

            <div class="speech-bar">
              <button id="mic-btn" type="button" class="btn mic" onclick="toggleRecording()">
                🎤 Speak Answer (Live STT)
              </button>
              <span class="speech-note" id="speech-note">Or type your answer directly in the box below:</span>
            </div>

            <textarea id="user-answer" placeholder="Speak into your microphone or type your answer here..."></textarea>

            <div class="actions">
              <button id="submit-btn" class="btn" onclick="submitAnswer()">
                Submit Answer for Rubric Evaluation &rarr;
              </button>
            </div>
          </div>
        `;
      } else if (state.view === 'feedback') {
        const f = state.lastEvaluation;
        const scores = f.scores;
        const isTech = state.roundType === 'technical';
        container.innerHTML = `
          <div class="panel">
            <div class="question-header">
              <div>
                <span class="eyebrow">TURN ${f.turn_number} EVALUATION</span>
                <span class="badge">${f.topic || 'Evaluation'}</span>
              </div>
              <span class="badge" style="background:#1e293b; color:#fbbf24;">⏱ ${Math.round(f.time_taken_s)}s</span>
            </div>

            <div class="question-card" style="margin-bottom:1rem;">
              <h3 style="font-size:1.05rem; color:#cbd5e1;">Q: ${f.question}</h3>
              <p style="margin-top:0.5rem; font-size:0.92rem; color:#94a3b8; font-style:italic;">Your Answer: "${f.answer_transcript}"</p>
            </div>

            <div class="rubric-grid">
              <div class="rubric-meter">
                <span>${isTech ? 'Technical Accuracy' : 'STAR / Context'}</span>
                <strong>${scores.accuracy}/10</strong>
              </div>
              <div class="rubric-meter">
                <span>${isTech ? 'Structure & Trade-offs' : 'Ownership & Fit'}</span>
                <strong>${scores.structure}/10</strong>
              </div>
              <div class="rubric-meter">
                <span>Communication Clarity</span>
                <strong>${scores.communication}/10</strong>
              </div>
              <div class="rubric-meter total">
                <span>Turn Score</span>
                <strong>${Math.round(scores.overall)}/100</strong>
              </div>
            </div>

            <div class="feedback-callout">
              <strong>AI Evaluator Feedback:</strong>
              <p>${f.feedback}</p>
            </div>

            <details>
              <summary>View Reference Model Answer</summary>
              <p>${f.model_answer}</p>
            </details>

            <div class="actions">
              ${f.is_complete ? `
                <button class="btn" onclick="completeSession()">
                  📊 View Placement Summary Report &rarr;
                </button>
              ` : `
                <button class="btn" onclick="fetchNextQuestion()">
                  Next Question (${f.next_turn_number} of ${state.session.total_questions}) &rarr;
                </button>
              `}
            </div>
          </div>
        `;
      } else if (state.view === 'report') {
        const r = state.report;
        container.innerHTML = `
          <div class="panel">
            <div class="eyebrow">PLACEMENT READINESS EVALUATION</div>
            <h2>Interview Complete</h2>
            <p class="subtitle">${r.round_type.toUpperCase()} Round for ${r.target_role}</p>

            <div class="score-banner">
              <div class="gauge">
                <span class="number">${Math.round(r.overall_score)}</span>
                <span class="denom">/ 100</span>
              </div>
              <div class="summary-text">
                <h3>${r.overall_score >= 75 ? 'Placement Ready 🎯' : 'Progressing - Focus on Core Topics 📈'}</h3>
                <p>${r.summary_feedback}</p>
              </div>
            </div>

            <div class="split-cards">
              <div class="col-card strengths">
                <h4>✅ Key Strengths</h4>
                <ul>
                  ${r.strengths.length > 0 ? r.strengths.map(s => `<li>${s}</li>`).join('') : '<li>Completed all assigned interview rounds.</li>'}
                </ul>
              </div>
              <div class="col-card improvements">
                <h4>🎯 Priority Areas to Refine</h4>
                <ul>
                  ${r.improvements.length > 0 ? r.improvements.map(i => `<li>${i}</li>`).join('') : '<li>Continue taking higher difficulty mocks.</li>'}
                </ul>
              </div>
            </div>

            <div class="actions" style="justify-content:center;">
              <button class="btn" onclick="state.view = 'setup'; render();">
                🔄 Start Another Mock Interview
              </button>
            </div>
          </div>
        `;
      }
    }

    render();
  </script>
</body>
</html>
"""
