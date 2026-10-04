import { useEffect, useMemo, useState } from 'react'
import { supabase } from './supabaseClient'
import { useAuthStore } from './store/authStore'
import { apiRequest } from './apiClient'

const navItems = [
  { label: 'Dashboard', path: '/' },
  { label: 'Diagnostic', path: '/diagnostic' },
  { label: 'Planner', path: '/planner' },
  { label: 'Review', path: '/review' },
  { label: 'Interview', path: '/interview' },
]

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
    <div className="auth-card">
      <h2>{mode === 'signup' ? 'Create account' : 'Log in'}</h2>
      <form onSubmit={handleSubmit} className="stack">
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" required />
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" required />
        {error && <p className="error">{error}</p>}
        <button type="submit">{mode === 'signup' ? 'Sign up' : 'Log in'}</button>
      </form>
      <button className="secondary" onClick={() => setMode(mode === 'signup' ? 'login' : 'signup')}>
        {mode === 'signup' ? 'Switch to login' : 'Need an account?'}
      </button>
    </div>
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
    <div className="card">
      <h3>Onboarding</h3>
      <form onSubmit={handleSubmit} className="stack">
        <input value={form.target_role} onChange={handleChange('target_role')} placeholder="Target role" />
        <input type="date" value={form.target_date} onChange={handleChange('target_date')} />
        <input type="number" min="1" max="80" value={form.weekly_hours} onChange={handleChange('weekly_hours')} />
        <button type="submit">Save profile</button>
        {message && <p>{message}</p>}
      </form>
    </div>
  )
}

function Dashboard() {
  const { session } = useAuthStore()
  const [skills, setSkills] = useState({})

  useEffect(() => {
    if (!session?.access_token) return

    apiRequest('/skills/me', { method: 'GET' }, session.access_token)
      .then((data) => setSkills(data))
      .catch(() => setSkills({}))
  }, [session])

  return (
    <div className="card">
      <h3>Dashboard</h3>
      <pre>{JSON.stringify(skills, null, 2)}</pre>
    </div>
  )
}

function Diagnostic() {
  const { session } = useAuthStore()
  const [sessionId, setSessionId] = useState(null)
  const [question, setQuestion] = useState(null)
  const [progress, setProgress] = useState(0)
  const [report, setReport] = useState(null)
  const [startedAt, setStartedAt] = useState(Date.now())
  const [error, setError] = useState('')

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
  }

  if (report) {
    return <section className="diagnostic-panel"><div className="eyebrow">Diagnostic complete</div><h2>{report.cluster_label}</h2><p>Confidence: {Math.round(report.confidence * 100)}%</p><div className="mastery-list">{Object.entries(report.mastery).map(([topic, value]) => <div className="mastery-row" key={topic}><span>{topic}</span><div className="bar"><i style={{ width: `${value * 100}%` }} /></div><strong>{Math.round(value * 100)}%</strong></div>)}</div><button className="secondary" onClick={() => { setReport(null); setSessionId(null); setQuestion(null); setProgress(0) }}>Start another</button></section>
  }

  if (!sessionId) return <section className="diagnostic-panel"><div className="eyebrow">Placement diagnostic</div><h2>Find your starting point</h2><p>Answer a focused set of questions so PrepOS can shape your practice plan.</p>{error && <p className="error">{error}</p>}<button onClick={start}>Start diagnostic</button></section>
  return <section className="diagnostic-panel"><div className="progress-line"><span>Question {progress + 1} of 25</span><span className="timer">Timed</span></div><div className="progress-track"><i style={{ width: `${Math.min((progress / 25) * 100, 100)}%` }} /></div><h2>{question?.body}</h2><div className="answer-grid">{(question?.options || []).map((option) => <button key={option} className="answer-button" onClick={() => answer(option)}>{option}</button>)}</div></section>
}

function Planner() {
  const { session } = useAuthStore()
  const [plan, setPlan] = useState(null)
  const [message, setMessage] = useState('')
  const token = session?.access_token

  async function loadCurrent() {
    const current = await apiRequest('/schedule/current', { method: 'GET' }, token)
    setPlan(current)
  }

  useEffect(() => {
    loadCurrent().catch((error) => setMessage(error.message))
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
  return <section className="planner-panel"><div className="planner-header"><div><div className="eyebrow">Weekly planner</div><h2>Your study week</h2></div><button onClick={generate}>Generate this week's plan</button></div>{message && <p className="planner-message">{message}</p>}{!plan && <p className="planner-empty">Generate a plan to place your next study blocks.</p>}{plan && <div className="week-grid">{days.map((day) => <div className="day-column" key={day}><h3>{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day]}</h3>{plan.sessions.filter((item) => item.day_of_week === day).map((item) => <article className={`session ${item.status}`} key={item.id}><strong>{item.topic_id}</strong><span>{item.start_time} · {item.duration_minutes} min</span>{item.status === 'scheduled' && <div className="session-actions"><button onClick={() => updateSession(item.id, 'complete')}>Complete</button><button className="secondary" onClick={() => updateSession(item.id, 'skip')}>Skip</button></div>}<small>{item.status}</small></article>)}</div>)}</div>}</section>
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
        <h1>PrepOS</h1>
        <nav>
          {navItems.map((item) => (
            <a key={item.path} href={item.path} className={page === item.label ? 'active' : ''}>
              {item.label}
            </a>
          ))}
        </nav>
        {session && <button onClick={() => supabase.auth.signOut().then(() => clearSession())}>Log out</button>}
      </aside>
      <main className="content">
        {page === 'Dashboard' && <Dashboard />}
        {page === 'Diagnostic' && <Diagnostic />}
        {page === 'Planner' && <Planner />}
        {page === 'Review' && <div className="card"><h3>Review</h3><p>Stub page</p></div>}
        {page === 'Interview' && <div className="card"><h3>Interview</h3><p>Stub page</p></div>}
        {currentToken && <OnboardingForm />}
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

  if (loading) return <div className="loading">Loading...</div>

  if (!session) return <SignInForm />

  return <AppShell />
}
