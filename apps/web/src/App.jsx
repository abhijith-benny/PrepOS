import { useEffect, useMemo, useState } from 'react'
import { supabase } from './supabaseClient'
import { useAuthStore } from './store/authStore'
import { apiRequest } from './apiClient'

const navItems = [
  { label: 'Dashboard', path: '/', icon: '01' },
  { label: 'Diagnostic', path: '/diagnostic', icon: '02' },
  { label: 'Planner', path: '/planner', icon: '03' },
  { label: 'Review', path: '/review', icon: '04' },
  { label: 'Interview', path: '/interview', icon: '05' },
]

function Brand() {
  return <div className="brand"><span className="brand-mark">P</span><h1>PrepOS</h1></div>
}

function SignInForm() {
  const { setSession } = useAuthStore()
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')

    let response
    if (mode === 'signup') {
      response = await supabase.auth.signUp({ email, password })
    } else {
      response = await supabase.auth.signInWithPassword({ email, password })
    }

    if (response.error) {
      setError(response.error.message)
      return
    }

    setSession(response.data.session)
  }

  return (
    <div className="auth-layout"><div className="auth-card">
      <Brand />
      <div className="page-heading"><div><div className="eyebrow">Your preparation workspace</div><h2>{mode === 'signup' ? 'Create account' : 'Welcome back'}</h2><p>{mode === 'signup' ? 'Build a focused plan for the role ahead.' : 'Continue where your preparation left off.'}</p></div></div>
      <form onSubmit={handleSubmit} className="stack">
        <div className="form-field"><label htmlFor="email">Email address</label><input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required /></div>
        <div className="form-field"><label htmlFor="password">Password</label><input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 6 characters" required /></div>
        {error && <p className="error">{error}</p>}
        <button type="submit">{mode === 'signup' ? 'Sign up' : 'Log in'}</button>
      </form>
      <button className="secondary" onClick={() => setMode(mode === 'signup' ? 'login' : 'signup')}>
        {mode === 'signup' ? 'Switch to login' : 'Need an account?'}
      </button>
    </div></div>
  )
}

function OnboardingForm() {
  const { user } = useAuthStore()
  const [form, setForm] = useState({ target_role: '', target_date: '', weekly_hours: '10' })
  const [message, setMessage] = useState('')

  const handleChange = (field) => (event) => setForm((prev) => ({ ...prev, [field]: event.target.value }))

  async function handleSubmit(event) {
    event.preventDefault()
    setMessage('Profile saved for onboarding.')
    const payload = {
      full_name: user?.email ?? 'Learner',
      target_role: form.target_role,
      target_date: form.target_date,
      weekly_hours: Number(form.weekly_hours),
    }
    const token = user?.access_token || user?.token
    if (token) {
      await apiRequest('/me', { method: 'PATCH', body: JSON.stringify(payload) }, token)
    }
  }

  return (
    <div className="card onboarding-card">
      <div className="eyebrow">Profile setup</div><h3>Set your direction</h3><p>These details help shape your weekly study rhythm.</p>
      <form onSubmit={handleSubmit} className="stack">
        <div className="form-field"><label htmlFor="target-role">Target role</label><input id="target-role" value={form.target_role} onChange={handleChange('target_role')} placeholder="e.g. Product engineer" /></div>
        <div className="form-field"><label htmlFor="target-date">Target date</label><input id="target-date" type="date" value={form.target_date} onChange={handleChange('target_date')} /></div>
        <div className="form-field"><label htmlFor="weekly-hours">Weekly study hours</label><input id="weekly-hours" type="number" min="1" max="80" value={form.weekly_hours} onChange={handleChange('weekly_hours')} /></div>
        <button type="submit">Save profile</button>
        {message && <p className="success">{message}</p>}
      </form>
    </div>
  )
}

function Dashboard() {
  const { session } = useAuthStore()
  const [skills, setSkills] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!session?.access_token) return

    apiRequest('/skills/me', { method: 'GET' }, session.access_token)
      .then((data) => setSkills(data))
      .catch(() => setSkills({}))
      .finally(() => setLoading(false))
  }, [session])

  const skillEntries = Object.entries(skills)
  return <div className="dashboard-page"><div className="page-heading"><div><div className="eyebrow">Overview</div><h2>Good to see you.</h2><p>Your learning signal at a glance. Keep the next useful step close.</p></div></div>{loading ? <div className="dashboard-grid"><div className="card"><div className="skeleton" /><div className="skeleton" /><div className="skeleton short" /></div></div> : <><div className="dashboard-grid"><div className="card stat-card"><span className="stat-label">Topics tracked</span><strong>{skillEntries.length}</strong><span className="stat-note">Across your learner model</span></div><div className="card stat-card"><span className="stat-label">Average mastery</span><strong>{skillEntries.length ? `${Math.round(skillEntries.reduce((sum, [, value]) => sum + value.mastery, 0) / skillEntries.length * 100)}%` : '—'}</strong><span className="stat-note">Built from recent evidence</span></div><div className="card stat-card accent-card"><span className="stat-label">Next move</span><strong>Diagnostic</strong><span className="stat-note">Calibrate your starting point</span></div></div><div className="card skill-overview"><div className="section-heading"><div><h3>Skill overview</h3><p>Mastery across the topics you have touched.</p></div><a href="/planner">Open planner →</a></div>{skillEntries.length ? <div className="mastery-list">{skillEntries.map(([topic, value]) => <div className="mastery-row" key={topic}><span>{topic}</span><div className="bar"><i style={{ width: `${value.mastery * 100}%` }} /></div><strong>{Math.round(value.mastery * 100)}%</strong></div>)}</div> : <div className="empty-inline">Complete the diagnostic to start building your skill vector.</div>}</div></>}</div>
}

function Diagnostic() {
  const { session } = useAuthStore()
  const [sessionId, setSessionId] = useState(null)
  const [question, setQuestion] = useState(null)
  const [progress, setProgress] = useState(0)
  const [report, setReport] = useState(null)
  const [startedAt, setStartedAt] = useState(Date.now())
  const [error, setError] = useState('')
  const [answering, setAnswering] = useState(false)

  const token = session?.access_token

  async function start() {
    setError('')
    try {
      const created = await apiRequest('/diagnostic/sessions', { method: 'POST' }, token)
      setSessionId(created.id)
      setReport(null)
      await loadNext(created.id)
    } catch (err) {
      setError(err.message)
    }
  }

  async function loadNext(id = sessionId) {
    const next = await apiRequest(`/diagnostic/sessions/${id}/next`, { method: 'GET' }, token)
    setProgress(next.progress)
    setQuestion(next.question)
    setStartedAt(Date.now())
  }

  async function answer(value) {
    setAnswering(true)
    setError('')
    try {
      await apiRequest(`/diagnostic/sessions/${sessionId}/answer`, {
        method: 'POST',
        body: JSON.stringify({ question_id: question.id, answer: value, time_taken_s: (Date.now() - startedAt) / 1000 }),
      }, token)
      const next = await apiRequest(`/diagnostic/sessions/${sessionId}/next`, { method: 'GET' }, token)
      setProgress(next.progress)
      if (next.done) {
        const completed = await apiRequest(`/diagnostic/sessions/${sessionId}/complete`, { method: 'POST' }, token)
        setReport(completed)
        setQuestion(null)
      } else {
        setQuestion(next.question)
        setStartedAt(Date.now())
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setAnswering(false)
    }
  }

  if (report) {
    return <section className="diagnostic-panel report-panel"><div className="eyebrow">Diagnostic complete</div><div className="report-heading"><div><h2>{report.cluster_label}</h2><p>Your first profile is ready. Use it as a starting point, not a ceiling.</p></div><div className="confidence-ring"><strong>{Math.round(report.confidence * 100)}%</strong><span>confidence</span></div></div><div className="mastery-list">{Object.entries(report.mastery).map(([topic, value]) => <div className="mastery-row" key={topic}><span>{topic}</span><div className="bar"><i style={{ width: `${value * 100}%` }} /></div><strong>{Math.round(value * 100)}%</strong></div>)}</div><button className="secondary" onClick={() => { setReport(null); setSessionId(null); setQuestion(null); setProgress(0) }}>Start another</button></section>
  }

  if (!sessionId) return <section className="diagnostic-panel diagnostic-start"><div className="eyebrow">Placement diagnostic</div><div className="diagnostic-kicker">01 <span>/</span> 25</div><h2>Find your starting point</h2><p>Answer a focused set of questions so PrepOS can shape your practice plan around the skills that matter most.</p>{error && <p className="error">{error}</p>}<button onClick={start}>Start diagnostic <span aria-hidden="true">→</span></button></section>
  return <section className="diagnostic-panel question-panel"><div className="progress-line"><span>Question {progress + 1} of 25</span><span className="timer">Adaptive placement</span></div><div className="progress-track"><i style={{ width: `${Math.min((progress / 25) * 100, 100)}%` }} /></div>{question ? <><div className="question-meta">Topic check <span>•</span> Take your best answer</div><h2>{question.body}</h2><div className="answer-grid">{(question.options || []).map((option, index) => <button disabled={answering} key={option} className="answer-button" onClick={() => answer(option)}><span className="answer-index">{String.fromCharCode(65 + index)}</span><span>{option}</span></button>)}</div></> : <div className="question-loading"><div className="skeleton" /><div className="skeleton short" /></div>}{error && <p className="error">{error}</p>}</section>
}

function Planner() {
  const { session } = useAuthStore()
  const [plan, setPlan] = useState(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const token = session?.access_token

  async function loadCurrent() {
    const current = await apiRequest('/schedule/current', { method: 'GET' }, token)
    setPlan(current)
  }

  useEffect(() => {
    loadCurrent().catch((error) => setMessage(error.message)).finally(() => setLoading(false))
  }, [token])

  async function generate() {
    setMessage('')
    try {
      setPlan(await apiRequest('/schedule/generate', { method: 'POST' }, token))
    } catch (error) {
      let detail = error.message
      try {
        const parsed = JSON.parse(detail)
        detail = parsed.detail?.reason || `${parsed.detail?.minimum_hours_needed || ''} hours needed.`
      } catch {
        // Keep the raw API message when it is not JSON.
      }
      setMessage(detail)
    }
  }

  async function updateSession(id, action) {
    const updated = await apiRequest(`/schedule/sessions/${id}/${action}`, { method: 'POST' }, token)
    setPlan((current) => ({ ...current, sessions: current.sessions.map((item) => item.id === id ? { ...item, ...updated } : item) }))
  }

  const days = Array.from({ length: 7 }, (_, index) => index)
  return <section className="planner-panel"><div className="planner-header"><div><div className="eyebrow">Weekly planner</div><h2>Your study week</h2><p>Small, focused blocks arranged around your available time.</p></div><button disabled={loading} onClick={generate}>Generate this week's plan</button></div>{message && <p className="planner-message">{message}</p>}{loading && <div className="planner-loading"><div className="skeleton" /><div className="skeleton" /><div className="skeleton short" /></div>}{!loading && !plan && <div className="planner-empty"><strong>No plan for this week yet.</strong><span>Generate a plan to place your next study blocks.</span></div>}{!loading && plan && <div className="week-grid">{days.map((day) => <div className="day-column" key={day}><h3>{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day]}</h3>{plan.sessions.filter((item) => item.day_of_week === day).map((item) => <article className={`session ${item.status}`} key={item.id}><strong>{item.topic_id}</strong><span>{item.start_time} · {item.duration_minutes} min</span>{item.status === 'scheduled' && <div className="session-actions"><button onClick={() => updateSession(item.id, 'complete')}>Complete</button><button className="secondary" onClick={() => updateSession(item.id, 'skip')}>Skip</button></div>}<small>{item.status}</small></article>)}</div>)}</div>}</section>
}

function AppShell() {
  const { session, clearSession } = useAuthStore()
  const currentToken = session?.access_token

  const page = useMemo(() => {
    const pathname = window.location.pathname
    if (pathname === '/diagnostic') return 'Diagnostic'
    if (pathname === '/planner') return 'Planner'
    if (pathname === '/review') return 'Review'
    if (pathname === '/interview') return 'Interview'
    return 'Dashboard'
  }, [window.location.pathname])

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <nav>
          {navItems.map((item) => (
            <a key={item.path} href={item.path} className={page === item.label ? 'active' : ''}>
              <span aria-hidden="true">{item.icon}</span>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="user-caption">{session?.user?.email || 'Learner workspace'}</span>
          {session && <button onClick={() => supabase.auth.signOut().then(() => clearSession())}>Log out</button>}
        </div>
      </aside>
      <main className="content">
        <div className="page-frame">
          {page === 'Dashboard' && <Dashboard />}
          {page === 'Diagnostic' && <Diagnostic />}
          {page === 'Planner' && <Planner />}
          {page === 'Review' && <div className="card"><h3>Review</h3><p>Review workspace is coming soon.</p></div>}
          {page === 'Interview' && <div className="card"><h3>Interview</h3><p>Interview workspace is coming soon.</p></div>}
        </div>
        {currentToken && <div className="page-frame"><OnboardingForm /></div>}
      </main>
    </div>
  )
}

export default function App() {
  const { session, setSession } = useAuthStore()
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })

    const { data: authListener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession)
    })

    return () => authListener.subscription.unsubscribe()
  }, [setSession])

  if (loading) return <div className="loading"><div className="loading-card"><div className="skeleton short" /><div className="skeleton" /><div className="skeleton" /></div></div>

  if (!session) return <SignInForm />

  return <AppShell />
}
