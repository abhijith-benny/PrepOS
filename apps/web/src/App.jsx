import { useEffect, useMemo, useRef, useState } from 'react'

import { supabase } from './supabaseClient'
import { useAuthStore } from './store/authStore'
import { apiRequest } from './apiClient'

const navItems = [
  { label: 'Dashboard', path: '/', icon: '01' },
  { label: 'Diagnostic', path: '/diagnostic', icon: '02' },
  { label: 'Planner', path: '/planner', icon: '03' },
  { label: 'Profile', path: '/profile', icon: '04' },
  { label: 'Coding Practice', path: '/coding', icon: '05' },
  { label: 'Review', path: '/review', icon: '06' },
  { label: 'Interview', path: '/interview', icon: '07' },
]

const PROFILE_STORAGE_KEY = 'prepos:profile'

function Brand() {
  return <div className="brand"><span className="brand-mark">P</span><h1>PrepOS</h1></div>
}

function SignInForm() {
  const { setSession } = useAuthStore()
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSaving(true)

    let response
    if (mode === 'signup') {
      response = await supabase.auth.signUp({ email, password })
    } else {
      response = await supabase.auth.signInWithPassword({ email, password })
    }

    if (response.error) {
      setError(response.error.message)
      setSaving(false)
      return
    }

    setSession(response.data.session)
    setSaving(false)
  }

  return (
    <div className="auth-layout"><div className="auth-card">
      <Brand />
      <div className="page-heading"><div><div className="eyebrow">Your preparation workspace</div><h2>{mode === 'signup' ? 'Create account' : 'Welcome back'}</h2><p>{mode === 'signup' ? 'Build a focused plan for the role ahead.' : 'Continue where your preparation left off.'}</p></div></div>
      <form onSubmit={handleSubmit} className="stack">
        <div className="form-field"><label htmlFor="email">Email address</label><input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required /></div>
        <div className="form-field"><label htmlFor="password">Password</label><input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 6 characters" required /></div>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={saving}>{saving ? 'Saving...' : mode === 'signup' ? 'Sign up' : 'Log in'}</button>
      </form>
      <button className="secondary" onClick={() => setMode(mode === 'signup' ? 'login' : 'signup')}>
        {mode === 'signup' ? 'Switch to login' : 'Need an account?'}
      </button>
    </div></div>
  )
}

function OnboardingForm({ profile = null, mode = 'onboarding', onSaved }) {
  const { user, session } = useAuthStore()
  const [form, setForm] = useState({ target_role: profile?.target_role || '', target_date: profile?.target_date || '', weekly_hours: profile?.weekly_hours || '10', department: profile?.department || '', year_or_semester: profile?.year_or_semester || '', known_languages: (profile?.known_languages || []).join(', '), leetcode_username: profile?.leetcode_username || '' })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const handleChange = (field) => (event) => setForm((prev) => ({ ...prev, [field]: event.target.value }))

  async function handleSubmit(event) {
    event.preventDefault()
    setMessage('')
    setError('')
    setSaving(true)
    if (!form.department.trim()) {
      setError('Department is required before starting the diagnostic.')
      setSaving(false)
      return
    }
    const payload = {
      full_name: user?.email ?? 'Learner',
      target_role: form.target_role,
      target_date: form.target_date,
      weekly_hours: Number(form.weekly_hours),
      department: form.department.trim(),
      year_or_semester: form.year_or_semester.trim() || null,
      known_languages: form.known_languages.split(',').map((language) => language.trim()).filter(Boolean),
      leetcode_username: form.leetcode_username.trim() || null,
    }
    try {
      const { data: sessionData } = await supabase.auth.refreshSession()
      const token = sessionData.session?.access_token || session?.access_token
      if (!token) {
        throw new Error('You need to be signed in to save your profile.')
      }
        await apiRequest('/me', { method: 'PATCH', body: JSON.stringify(payload) }, token)
        window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(payload))
        window.localStorage.setItem('prepos:onboarding-complete', 'true')
        setMessage(mode === 'profile' ? 'Profile saved.' : 'Profile saved. Your diagnostic is ready.')
        onSaved?.(payload)
    } catch (err) {
      setError(err.message === 'Failed to fetch' ? 'Your session may have expired. Sign in again, then save your profile.' : err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card onboarding-card">
      <div className="eyebrow">{mode === 'profile' ? 'Edit profile' : 'Profile setup'}</div><h3>{mode === 'profile' ? 'Keep your context current' : 'Set your direction'}</h3><p>These details help shape your weekly study rhythm and diagnostic context.</p>
      <form onSubmit={handleSubmit} className="stack">
        <div className="form-field"><label htmlFor="department">Department <span className="required-mark">Required</span></label><input id="department" value={form.department} onChange={handleChange('department')} placeholder="e.g. Computer Science" required /></div>
        <div className="form-field"><label htmlFor="year-semester">Year or semester <span className="optional-mark">Optional</span></label><input id="year-semester" value={form.year_or_semester} onChange={handleChange('year_or_semester')} placeholder="e.g. 3rd year, semester 6" /></div>
        <div className="form-field"><label htmlFor="known-languages">Known languages <span className="optional-mark">Optional</span></label><input id="known-languages" value={form.known_languages} onChange={handleChange('known_languages')} placeholder="Python, Java, C++" /></div>
        <div className="form-field"><label htmlFor="leetcode-username">LeetCode username <span className="optional-mark">Optional</span></label><input id="leetcode-username" value={form.leetcode_username} onChange={handleChange('leetcode_username')} placeholder="your-public-username" /></div>
        <div className="form-field"><label htmlFor="target-role">Target role</label><input id="target-role" value={form.target_role} onChange={handleChange('target_role')} placeholder="e.g. Product engineer" /></div>
        <div className="form-field"><label htmlFor="target-date">Target date</label><input id="target-date" type="date" value={form.target_date} onChange={handleChange('target_date')} /></div>
        <div className="form-field"><label htmlFor="weekly-hours">Weekly study hours</label><input id="weekly-hours" type="number" min="1" max="80" value={form.weekly_hours} onChange={handleChange('weekly_hours')} /></div>
        <button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save profile'}</button>
        {error && <p className="error">{error}</p>}{message && <p className="success">{message}</p>}
      </form>
    </div>
  )
}

function Profile({ profile, loading, error, onSaved }) {
  const [editing, setEditing] = useState(!profile?.department)

  useEffect(() => {
    if (profile) setEditing(!profile.department)
  }, [profile])

  if (loading) return <div className="profile-page"><div className="page-heading"><div><div className="eyebrow">Student profile</div><h2>Loading your profile.</h2></div></div><div className="card"><div className="skeleton" /><div className="skeleton" /><div className="skeleton short" /></div></div>
  if (error && !profile) return <div className="profile-page"><div className="page-heading"><div><div className="eyebrow">Student profile</div><h2>We could not load your profile.</h2><p>{error}</p></div></div><div className="error">Your session may have expired. Sign out and sign in again to load your saved profile.</div></div>

  return <div className="profile-page"><div className="page-heading"><div><div className="eyebrow">Student profile</div><h2>Your context, in one place.</h2><p>Keep the details behind your study plan and diagnostic up to date.</p></div>{profile?.department && !editing && <button onClick={() => setEditing(true)}>Edit profile</button>}</div>{editing ? <OnboardingForm profile={profile} mode="profile" onSaved={(saved) => { setEditing(false); onSaved(saved) }} /> : <div className="profile-summary"><div className="profile-summary-head"><div><span className="stat-label">Department</span><strong>{profile.department}</strong></div><div><span className="stat-label">Target role</span><strong>{profile.target_role || 'Not set'}</strong></div></div><div className="profile-detail-grid"><div><span className="stat-label">Target date</span><strong>{profile.target_date || 'Not set'}</strong></div><div><span className="stat-label">Weekly hours</span><strong>{profile.weekly_hours || 'Not set'}</strong></div><div><span className="stat-label">Year / semester</span><strong>{profile.year_or_semester || 'Not set'}</strong></div><div><span className="stat-label">Known languages</span><strong>{profile.known_languages?.join(', ') || 'Not set'}</strong></div><div><span className="stat-label">LeetCode username</span><strong>{profile.leetcode_username || 'Not set'}</strong></div></div></div>}</div>
}

function Dashboard({ profile }) {
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
  return <div className="dashboard-page"><div className="page-heading"><div><div className="eyebrow">Overview</div><h2>Good to see you.</h2><p>Your learning signal at a glance. Keep the next useful step close.</p></div></div><div className={`mock-test-card ${profile?.department ? 'unlocked' : 'locked'}`}><div><div className="eyebrow">Primary next step</div><h3>Start Mock Test</h3><p>{profile?.department ? 'Take the four-section placement test to calibrate your learning path.' : 'Complete your profile to unlock the mock test'}</p></div><a className={`mock-test-action ${!profile?.department ? 'disabled' : ''}`} href={profile?.department ? '/diagnostic' : undefined} aria-disabled={!profile?.department}>Start test <span aria-hidden="true">→</span></a></div>{loading ? <div className="dashboard-grid"><div className="card"><div className="skeleton" /><div className="skeleton" /><div className="skeleton short" /></div></div> : <><div className="dashboard-grid"><div className="card stat-card"><span className="stat-label">Topics tracked</span><strong>{skillEntries.length}</strong><span className="stat-note">Across your learner model</span></div><div className="card stat-card"><span className="stat-label">Average mastery</span><strong>{skillEntries.length ? `${Math.round(skillEntries.reduce((sum, [, value]) => sum + value.mastery, 0) / skillEntries.length * 100)}%` : '—'}</strong><span className="stat-note">Built from recent evidence</span></div><div className="card stat-card accent-card"><span className="stat-label">Next move</span><strong>Planner</strong><span className="stat-note">Turn weak topics into study blocks</span></div></div><div className="card skill-overview"><div className="section-heading"><div><h3>Skill overview</h3><p>Mastery across the topics you have touched.</p></div><a href="/planner">Open planner →</a></div>{skillEntries.length ? <div className="mastery-list">{skillEntries.map(([topic, value]) => <div className="mastery-row" key={topic}><span>{topic}</span><div className="bar"><i style={{ width: `${value.mastery * 100}%` }} /></div><strong>{Math.round(value.mastery * 100)}%</strong></div>)}</div> : <div className="empty-inline">Complete the diagnostic to start building your skill vector.</div>}</div></>}</div>
}

function Diagnostic({ profile }) {
  const { session } = useAuthStore()
  const [sessionId, setSessionId] = useState(null)
  const [question, setQuestion] = useState(null)
  const [progress, setProgress] = useState(0)
  const [report, setReport] = useState(null)
  const [codingSuggestions, setCodingSuggestions] = useState(null)
  const [startedAt, setStartedAt] = useState(Date.now())
  const [error, setError] = useState('')
  const [answering, setAnswering] = useState(false)
  const [currentSection, setCurrentSection] = useState(null)
  const [sectionTransition, setSectionTransition] = useState(null)
  const [verifying, setVerifying] = useState(false)
  const [verifyMessage, setVerifyMessage] = useState('')
  const [verifyStatus, setVerifyStatus] = useState('idle')
  const [inputLeetcodeUser, setInputLeetcodeUser] = useState('')
  const [savingUser, setSavingUser] = useState(false)

  // Timer states & refs
  const [timeLeft, setTimeLeft] = useState(60)
  const [timeLimit, setTimeLimit] = useState(60)
  const [selectedOption, setSelectedOption] = useState(null)
  const autoSubmittingRef = useRef(false)
  const answeringRef = useRef(false)
  const selectedOptionRef = useRef(null)
  const questionStartMsRef = useRef(Date.now())

  const token = session?.access_token
  const isCodingSection = currentSection?.id === 'coding' || question?.type === 'leetcode'

  // Keep selectedOptionRef in sync with selectedOption
  useEffect(() => {
    selectedOptionRef.current = selectedOption
  }, [selectedOption])

  // Timer countdown hook with auto-submit
  useEffect(() => {
    if (!question || report || sectionTransition) return

    autoSubmittingRef.current = false

    const updateTimer = () => {
      const elapsed = Math.floor((Date.now() - questionStartMsRef.current) / 1000)
      const remaining = Math.max(0, timeLimit - elapsed)
      setTimeLeft(remaining)
      if (remaining <= 0) {
        if (!autoSubmittingRef.current && !answeringRef.current) {
          autoSubmittingRef.current = true
          const autoVal = selectedOptionRef.current || (isCodingSection ? 'skipped' : 'unanswered')
          answer(autoVal, true)
        }
      }
    }

    updateTimer()
    const timer = setInterval(updateTimer, 500)
    return () => clearInterval(timer)
  }, [question?.id, timeLimit, report, sectionTransition, isCodingSection])

  function formatTimeDisplay(seconds, isCoding) {
    if (isCoding) {
      const mins = Math.floor(seconds / 60)
      const secs = seconds % 60
      return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
    }
    return `${seconds}s`
  }

  async function start() {
    setError('')
    try {
      const created = await apiRequest('/diagnostic/sessions', { method: 'POST' }, token)
      setSessionId(created.id)
      setReport(null)
      await loadNext(created.id)
    } catch (err) {
      try {
        const parsed = JSON.parse(err.message)
        const existingSessionId = parsed.detail?.session_id
        if (existingSessionId) {
          setSessionId(existingSessionId)
          setReport(null)
          await loadNext(existingSessionId)
          return
        }
        setError(parsed.detail?.message || err.message)
      } catch {
        setError(err.message)
      }
    }
  }

  async function loadNext(id = sessionId) {
    const next = await apiRequest(`/diagnostic/sessions/${id}/next`, { method: 'GET' }, token)
    setProgress(next.progress)
    setQuestion(next.question)
    setCurrentSection(next.section || null)
    setSectionTransition(null)
    setVerifyMessage('')
    setVerifyStatus('idle')
    setSelectedOption(null)
    selectedOptionRef.current = null
    autoSubmittingRef.current = false

    const limit = next.time_limit_s || (next.section?.id === 'coding' ? 1500 : 60)
    setTimeLimit(limit)
    const startMs = next.served_at ? new Date(next.served_at).getTime() : Date.now()
    questionStartMsRef.current = startMs
    setStartedAt(startMs)
    const initialRemaining = Math.max(0, limit - Math.floor((Date.now() - startMs) / 1000))
    setTimeLeft(initialRemaining)
  }

  async function verifyCodingProblem(assignmentId) {
    if (!assignmentId) {
      setVerifyStatus('error')
      setVerifyMessage('No assignment active for this problem yet.')
      return
    }
    setVerifying(true)
    setVerifyMessage('Checking your recent LeetCode submissions...')
    setVerifyStatus('info')
    try {
      const updated = await apiRequest(`/coding/assignments/${assignmentId}/verify`, { method: 'POST' }, token)
      if (updated.status === 'verified') {
        setVerifyStatus('success')
        setVerifyMessage('Accepted submission verified! Submitting coding section...')
        setTimeout(() => {
          answer('verified', false)
        }, 1200)
      } else {
        setVerifyStatus('error')
        setVerifyMessage(updated.message || 'No Accepted submission found on LeetCode after assignment yet. Submit your solution on LeetCode first, or continue below.')
      }
    } catch (err) {
      setVerifyStatus('error')
      setVerifyMessage(err.message || 'Failed to verify submission.')
    } finally {
      setVerifying(false)
    }
  }

  async function saveUserAndVerify(assignmentId) {
    if (!inputLeetcodeUser.trim()) return
    setSavingUser(true)
    setVerifyStatus('info')
    setVerifyMessage('Saving LeetCode username...')
    try {
      await apiRequest('/me', {
        method: 'PATCH',
        body: JSON.stringify({ leetcode_username: inputLeetcodeUser.trim() }),
      }, token)
      if (profile) {
        profile.leetcode_username = inputLeetcodeUser.trim()
      }
      setVerifyMessage('Username saved! Now verifying submissions...')
      await verifyCodingProblem(assignmentId)
    } catch (err) {
      setVerifyStatus('error')
      setVerifyMessage(err.message || 'Failed to save username.')
    } finally {
      setSavingUser(false)
    }
  }

  async function answer(value, autoSubmitted = false) {
    if (answeringRef.current) return
    answeringRef.current = true
    setAnswering(true)
    setError('')
    try {
      const elapsedSec = (Date.now() - questionStartMsRef.current) / 1000
      await apiRequest(`/diagnostic/sessions/${sessionId}/answer`, {
        method: 'POST',
        body: JSON.stringify({
          question_id: question.id,
          answer: value || (isCodingSection ? 'skipped' : 'unanswered'),
          time_taken_s: Math.max(0, elapsedSec),
          auto_submitted: Boolean(autoSubmitted),
        }),
      }, token)
      const next = await apiRequest(`/diagnostic/sessions/${sessionId}/next`, { method: 'GET' }, token)
      setProgress(next.progress)
      if (next.done) {
        const completed = await apiRequest(`/diagnostic/sessions/${sessionId}/complete`, { method: 'POST' }, token)
        setReport(completed)
        setQuestion(null)
        // Fetch coding suggestions in the background — non-blocking.
        apiRequest(`/diagnostic/sessions/${sessionId}/coding-suggestions`, { method: 'GET' }, token)
          .then((data) => setCodingSuggestions(data))
          .catch(() => setCodingSuggestions(null))
      } else if (next.section_complete && next.next_section) {
        setQuestion(null)
        setSectionTransition(next.next_section)
      } else {
        setQuestion(next.question)
        setCurrentSection(next.section || null)
        setSelectedOption(null)
        selectedOptionRef.current = null
        autoSubmittingRef.current = false
        const limit = next.time_limit_s || (next.section?.id === 'coding' ? 1500 : 60)
        setTimeLimit(limit)
        const startMs = next.served_at ? new Date(next.served_at).getTime() : Date.now()
        questionStartMsRef.current = startMs
        setStartedAt(startMs)
        const initialRemaining = Math.max(0, limit - Math.floor((Date.now() - startMs) / 1000))
        setTimeLeft(initialRemaining)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      answeringRef.current = false
      setAnswering(false)
    }
  }

  if (report) {
    const codingSection = (report.sections || []).find((s) => s.id === 'coding')
    const suggestedProblems = codingSuggestions?.has_problems ? codingSuggestions.problems : []
    const overallPct = report.overall_score_percentage !== undefined
      ? report.overall_score_percentage
      : Math.round(((report.total_correct || 0) / Math.max(1, report.total_questions || 1)) * 100)
    const totalCorrect = report.total_correct ?? (report.sections || []).reduce((acc, s) => acc + (s.correct_count || 0), 0)
    const totalQuestions = report.total_questions ?? (report.sections || []).reduce((acc, s) => acc + (s.question_count || 0), 0)

    return (
      <section className="diagnostic-panel report-panel">
        <div className="eyebrow">Diagnostic complete</div>

        {/* Prominent Overall Score Summary Banner */}
        <div className="overall-score-hero">
          <div className="overall-score-tag">Mock Test Overall Mark</div>
          <div className="overall-score-main">
            <div className="overall-score-circle">
              <span className="score-number">{overallPct}%</span>
              <span className="score-desc">Overall Mark</span>
            </div>
            <div className="overall-score-meta">
              <h3>Diagnostic Calibration Complete</h3>
              <p>
                Overall Score: <strong>{totalCorrect}</strong> / <strong>{totalQuestions}</strong> questions correct across all sections ({overallPct}%).
              </p>
              <div className="score-badges">
                <span className="badge-item">🎯 Profile: {report.cluster_label || 'Assigned'}</span>
                <span className="badge-item">📈 Calibration: {Math.round((report.confidence || 0.8) * 100)}% confidence</span>
              </div>
            </div>
          </div>
        </div>

        <div className="report-heading">
          <div><h2>{report.cluster_label}</h2><p>Your first profile is ready. Use it as a starting point, not a ceiling.</p></div>
          <div className="confidence-ring"><strong>{Math.round(report.confidence * 100)}%</strong><span>confidence</span></div>
        </div>
        <div className="section-report-list">
          {(report.sections || []).map((section) => (
            <article className="section-report" key={section.id}>
              <div className="section-header-row">
                <div>
                  <strong>{section.label}</strong>
                  <span>{section.description}</span>
                </div>
                <div className="section-stats-summary">
                  <b>{section.correct_count}/{section.question_limit} correct</b>
                  {section.time_taken_s !== undefined && (
                    <span className="section-total-time">⏱️ Total: {Math.round(section.time_taken_s)}s</span>
                  )}
                </div>
              </div>
              <div className="section-score"><i style={{ width: `${section.score * 100}%` }} /></div>
              <small>Strong: {section.strong_topics?.join(', ') || 'Building signal'} · Focus: {section.weak_topics?.join(', ') || 'Building signal'}</small>

              {/* Question-level breakdown showing correct, time taken, and timeout flag */}
              {section.answers && section.answers.length > 0 && (
                <div className="section-breakdown-box">
                  <div className="breakdown-headline">Question Breakdown</div>
                  <div className="breakdown-rows">
                    {section.answers.map((ans, idx) => (
                      <div key={ans.question_id || idx} className={`breakdown-item ${ans.correct ? 'is-correct' : 'is-incorrect'}`}>
                        <div className="breakdown-q-info">
                          <span className="breakdown-q-index">Q{idx + 1}</span>
                          <span className="breakdown-q-title">{ans.title || ans.question_id}</span>
                        </div>
                        <div className="breakdown-q-tags">
                          <span className="tag-time">⏱️ {Math.round(ans.time_taken_s || 0)}s</span>
                          {ans.auto_submitted && (
                            <span className="tag-timeout" title="Auto-submitted on timeout">⚠️ Timed out</span>
                          )}
                          <span className={`tag-status ${ans.correct ? 'pass' : 'fail'}`}>
                            {ans.correct ? '✓ Correct' : '✗ Incorrect'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {section.id === 'coding' && suggestedProblems.length > 0 && (
                <div className="coding-cta">
                  <div className="coding-cta-header">
                    <span className="coding-cta-eyebrow">🎯 Targeted LeetCode practice</span>
                    <p className="coding-cta-blurb">
                      Based on your weakest coding topics, start with these problems.
                      Solve them on LeetCode, then verify your submission in Coding Practice.
                    </p>
                  </div>
                  <ul className="coding-cta-list">
                    {suggestedProblems.map((problem) => (
                      <li key={problem.id} className="coding-cta-item">
                        <span className={`coding-difficulty coding-diff-${(problem.difficulty || 'easy').toLowerCase()}`}>{problem.difficulty}</span>
                        <a
                          href={`https://leetcode.com/problems/${problem.leetcode_slug}/`}
                          target="_blank"
                          rel="noreferrer"
                          className="coding-cta-link"
                        >
                          {problem.title} ↗
                        </a>
                      </li>
                    ))}
                  </ul>
                  <a href="/coding" className="coding-cta-action">
                    Practice these on LeetCode <span aria-hidden="true">→</span>
                  </a>
                </div>
              )}
            </article>
          ))}
        </div>
        <h3 className="report-subheading">Topic mastery</h3>
        <div className="mastery-list">
          {Object.entries(report.mastery).map(([topic, value]) => (
            <div className="mastery-row" key={topic}>
              <span>{topic}</span>
              <div className="bar"><i style={{ width: `${value * 100}%` }} /></div>
              <strong>{Math.round(value * 100)}%</strong>
            </div>
          ))}
        </div>
        <button className="secondary" onClick={() => { setReport(null); setCodingSuggestions(null); setSessionId(null); setQuestion(null); setProgress(0) }}>Start another</button>
      </section>
    )
  }

  if (!sessionId) return <section className="diagnostic-panel diagnostic-start"><div className="eyebrow">Placement diagnostic</div><div className="diagnostic-kicker">01 <span>/</span> 04 sections</div><h2>{profile?.department ? 'Find your starting point' : 'Complete your profile first'}</h2><p>{profile?.department ? 'Answer a focused set of questions so PrepOS can shape your practice plan around the skills that matter most.' : 'Add your department and context on your Profile page before starting the placement test.'}</p>{error && <p className="error">{error}</p>}{profile?.department ? <button onClick={start}>Start diagnostic <span aria-hidden="true">→</span></button> : <a className="profile-gate" href="/profile">Go to Profile <span aria-hidden="true">→</span></a>}</section>
  if (sectionTransition) return <section className="diagnostic-panel section-transition"><div className="eyebrow">Section complete</div><div className="transition-mark">✓</div><h2>Nice work. {sectionTransition.label} is complete.</h2><p>Take a breath, then continue into the next part of the placement test.</p><button onClick={() => loadNext()}>Continue to {sectionTransition.label}</button></section>

  const isTimerWarning = timeLeft <= 10 && timeLeft > 0
  const isTimerExpired = timeLeft === 0

  return (
    <section className="diagnostic-panel question-panel">
      <div className="section-indicator">
        <span>Section {currentSection?.index || 1} of {currentSection?.total || 4}</span>
        <strong>{currentSection?.label || 'Placement'}</strong>
        <small>{currentSection?.description}</small>
      </div>
      <div className="progress-line">
        <span>{isCodingSection ? 'Practical Coding Challenge' : `Question ${progress + 1} of ${currentSection?.question_limit || 10}`}</span>
        <div className={`timer-pill ${isTimerWarning ? 'timer-warning' : ''} ${isTimerExpired ? 'timer-expired' : ''}`}>
          <span className="timer-icon">{isTimerWarning ? '⚠️' : '⏱️'}</span>
          <span className="timer-display">{formatTimeDisplay(timeLeft, isCodingSection)}</span>
          {isTimerWarning && <span className="timer-subtext">Auto-submitting soon</span>}
        </div>
      </div>
      <div className="progress-track">
        <i style={{ width: `${isCodingSection ? 100 : Math.min((progress / (currentSection?.question_limit || 10)) * 100, 100)}%` }} />
      </div>
      {question ? (
        isCodingSection ? (
          <div className="coding-challenge-container">
            <div className="question-meta">Section 4 · Coding <span>•</span> Direct LeetCode Problem (25 min limit)</div>
            <div className="coding-challenge-header">
              <div>
                <span className="coding-challenge-eyebrow">LeetCode Assessment</span>
                <h2>{question.title || question.body}</h2>
              </div>
              <span className={`coding-difficulty coding-diff-${(question.difficulty || 'easy').toLowerCase()}`}>
                {question.difficulty || 'Easy'}
              </span>
            </div>
            <p className="coding-challenge-instructions">
              Solve this problem directly on LeetCode in your preferred programming language. After getting an <strong>Accepted</strong> submission on LeetCode, verify your submission below to record your performance.
            </p>

            <div className="coding-challenge-card">
              <div className="coding-challenge-details">
                <span className="challenge-tag">LeetCode Problem</span>
                <strong>{question.title || 'Coding Problem'}</strong>
                <span className="challenge-slug">Slug: <code>{question.leetcode_slug || 'problem'}</code></span>
              </div>
              <a
                href={question.leetcode_url || `https://leetcode.com/problems/${question.leetcode_slug}/`}
                target="_blank"
                rel="noreferrer"
                className="btn-solve-leetcode"
              >
                Solve on LeetCode ↗
              </a>
            </div>

            {verifyMessage && (
              <div className={`coding-verify-banner ${verifyStatus}`}>
                {verifyMessage}
              </div>
            )}

            <div className="coding-verify-box">
              {profile?.leetcode_username ? (
                <div className="verify-user-active">
                  <div className="verify-user-info">
                    <span>LeetCode Username:</span>
                    <strong>{profile.leetcode_username}</strong>
                  </div>
                  <div className="verify-actions">
                    <button
                      type="button"
                      disabled={verifying || answering}
                      onClick={() => verifyCodingProblem(question.assignment_id)}
                    >
                      {verifying ? 'Checking submissions...' : 'Check & Verify Submission'}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={answering || verifying}
                      onClick={() => answer('skipped', false)}
                    >
                      Continue / Skip verification →
                    </button>
                  </div>
                </div>
              ) : (
                <div className="verify-user-setup">
                  <div className="verify-setup-prompt">
                    <strong>Verify with your LeetCode Account</strong>
                    <p>Enter your public LeetCode username to verify your Accepted submission:</p>
                  </div>
                  <div className="verify-input-row">
                    <input
                      type="text"
                      placeholder="LeetCode username"
                      value={inputLeetcodeUser}
                      onChange={(e) => setInputLeetcodeUser(e.target.value)}
                    />
                    <button
                      type="button"
                      disabled={!inputLeetcodeUser.trim() || savingUser || verifying}
                      onClick={() => saveUserAndVerify(question.assignment_id)}
                    >
                      {savingUser ? 'Saving...' : 'Save & Verify'}
                    </button>
                  </div>
                  <button
                    type="button"
                    className="secondary link-style"
                    disabled={answering}
                    onClick={() => answer('skipped', false)}
                  >
                    Continue without LeetCode verification →
                  </button>
                </div>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="question-meta">Topic check <span>•</span> 60 seconds per question</div>
            <h2>{question.body}</h2>
            <div className="answer-grid">
              {(question.options || []).map((option, index) => {
                const isSelected = selectedOption === option
                return (
                  <button
                    type="button"
                    disabled={answering}
                    key={option}
                    className={`answer-button ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedOption(option)}
                  >
                    <span className="answer-index">{String.fromCharCode(65 + index)}</span>
                    <span>{option}</span>
                    {isSelected && <span className="selected-indicator">✓</span>}
                  </button>
                )
              })}
            </div>
            <div className="answer-submit-bar">
              <button
                type="button"
                className="confirm-answer-btn"
                disabled={!selectedOption || answering}
                onClick={() => answer(selectedOption, false)}
              >
                {answering ? 'Submitting...' : 'Confirm Answer →'}
              </button>
              <button
                type="button"
                className="skip-btn"
                disabled={answering}
                onClick={() => answer('skipped', false)}
              >
                Skip Question
              </button>
            </div>
          </>
        )
      ) : (
        <div className="question-loading">
          <div className="skeleton" />
          <div className="skeleton short" />
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  )
}

function Planner() {
  const { session } = useAuthStore()
  const [plan, setPlan] = useState(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [updatingId, setUpdatingId] = useState(null)
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
    setGenerating(true)
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
    } finally {
      setGenerating(false)
    }
  }

  async function updateSession(id, action) {
    setMessage('')
    setUpdatingId(id)
    try {
      const updated = await apiRequest(`/schedule/sessions/${id}/${action}`, { method: 'POST' }, token)
      setPlan((current) => ({ ...current, sessions: current.sessions.map((item) => item.id === id ? { ...item, ...updated } : item) }))
      setMessage(action === 'complete' ? 'Session marked complete.' : 'Session skipped.')
    } catch (error) {
      setMessage(error.message)
    } finally {
      setUpdatingId(null)
    }
  }

  const days = Array.from({ length: 7 }, (_, index) => index)
  return <section className="planner-panel"><div className="planner-header"><div><div className="eyebrow">Weekly planner</div><h2>Your study week</h2><p>Small, focused blocks arranged around your available time.</p></div><button disabled={loading || generating} onClick={generate}>{generating ? 'Saving...' : 'Generate this week\'s plan'}</button></div>{message && <p className="planner-message">{message}</p>}{loading && <div className="planner-loading"><div className="skeleton" /><div className="skeleton" /><div className="skeleton short" /></div>}{!loading && !plan && <div className="planner-empty"><strong>No plan for this week yet.</strong><span>Generate a plan to place your next study blocks.</span></div>}{!loading && plan && <div className="week-grid">{days.map((day) => <div className="day-column" key={day}><h3>{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day]}</h3>{plan.sessions.filter((item) => item.day_of_week === day).map((item) => <article className={`session ${item.status}`} key={item.id}><strong>{item.topic_id}</strong><span>{item.start_time} · {item.duration_minutes} min</span>{item.status === 'scheduled' && <div className="session-actions"><button disabled={updatingId === item.id} onClick={() => updateSession(item.id, 'complete')}>{updatingId === item.id ? 'Saving...' : 'Complete'}</button><button disabled={updatingId === item.id} className="secondary" onClick={() => updateSession(item.id, 'skip')}>Skip</button></div>}<small>{item.status}</small></article>)}</div>)}</div>}</section>
}

function CodingPractice() {
  const { session } = useAuthStore()
  const [assignments, setAssignments] = useState([])
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(null)
  const token = session?.access_token

  async function loadAssignments() {
    const data = await apiRequest('/coding/assignments', { method: 'GET' }, token)
    setAssignments(data)
  }

  useEffect(() => {
    loadAssignments().catch((error) => setMessage(error.message)).finally(() => setLoading(false))
  }, [token])

  async function assign() {
    setWorking('assign')
    setMessage('')
    try {
      await apiRequest('/coding/assign', { method: 'POST' }, token)
      await loadAssignments()
      setMessage('New coding problem assigned by AI based on your diagnostic results.')
    } catch (error) {
      setMessage(error.message)
    } finally {
      setWorking(null)
    }
  }

  async function verify(id) {
    setWorking(id)
    setMessage('Checking LeetCode submissions...')
    try {
      const updated = await apiRequest(`/coding/assignments/${id}/verify`, { method: 'POST' }, token)
      setAssignments((current) => current.map((item) => item.id === id ? { ...item, ...updated } : item))
      setMessage(updated.message || 'Verification complete.')
    } catch (error) {
      setMessage(error.message)
    } finally {
      setWorking(null)
    }
  }

  return (
    <div className="coding-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">LeetCode verified</div>
          <h2>Coding practice</h2>
          <p>Solve assigned problems on LeetCode, then verify an Accepted submission here.</p>
        </div>
        <button disabled={working === 'assign'} onClick={assign}>
          {working === 'assign' ? 'Assigning...' : 'Assign AI Problem'}
        </button>
      </div>
      {message && <p className="planner-message">{message}</p>}
      {loading ? (
        <div className="card"><div className="skeleton" /><div className="skeleton short" /></div>
      ) : assignments.length === 0 ? (
        <div className="card empty-inline">
          <strong>No coding problems assigned yet.</strong>
          <span>Assign one to begin.</span>
        </div>
      ) : (
        <div className="coding-list">
          {assignments.map((assignment) => (
            <article className="coding-card" key={assignment.id}>
              <div className="coding-card-content">
                <span className={`coding-difficulty coding-diff-${(assignment.problem?.difficulty || 'easy').toLowerCase()}`}>
                  {assignment.problem?.difficulty}
                </span>
                <h3>{assignment.problem?.title}</h3>
                {assignment.rationale && (
                  <div className="coding-rationale-box">
                    <span className="rationale-tag">🤖 AI Rationale</span>
                    <p className="rationale-text"><strong>Assigned because:</strong> {assignment.rationale}</p>
                  </div>
                )}
                <p className="coding-status-desc">
                  {assignment.status === 'verified'
                    ? '✓ Accepted submission verified on LeetCode.'
                    : assignment.status === 'failed_to_verify'
                    ? 'No Accepted submission found after assignment.'
                    : 'Pending verification.'}
                </p>
              </div>
              <div className="coding-actions">
                <a
                  href={`https://leetcode.com/problems/${assignment.problem?.leetcode_slug}/`}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-leetcode-link"
                >
                  Solve on LeetCode ↗
                </a>
                {assignment.status !== 'verified' && (
                  <button disabled={working === assignment.id} onClick={() => verify(assignment.id)}>
                    {working === assignment.id ? 'Checking...' : 'Check my submission'}
                  </button>
                )}
                <span className={`status-pill ${assignment.status}`}>{assignment.status.replaceAll('_', ' ')}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

function AppShell() {
  const { session, clearSession } = useAuthStore()
  const currentToken = session?.access_token
  const [profile, setProfile] = useState(null)
  const [profileLoading, setProfileLoading] = useState(true)
  const [profileError, setProfileError] = useState('')

  useEffect(() => {
    if (!currentToken) return
    async function loadProfile() {
      try {
        const { data: sessionData } = await supabase.auth.refreshSession()
        const token = sessionData.session?.access_token || currentToken
        const data = await apiRequest('/me', { method: 'GET' }, token)
        setProfile(data)
        setProfileError('')
      } catch (error) {
        setProfileError(error.message)
      }
    }
    loadProfile()
      .finally(() => setProfileLoading(false))
  }, [currentToken])

  const page = useMemo(() => {
    const pathname = window.location.pathname
    if (pathname === '/diagnostic') return 'Diagnostic'
    if (pathname === '/planner') return 'Planner'
    if (pathname === '/profile') return 'Profile'
    if (pathname === '/coding') return 'Coding Practice'
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
          {page === 'Dashboard' && <Dashboard profile={profile} />}
          {page === 'Diagnostic' && <Diagnostic profile={profile} />}
          {page === 'Planner' && <Planner />}
          {page === 'Profile' && <Profile profile={profile} loading={profileLoading} error={profileError} onSaved={setProfile} />}
          {page === 'Coding Practice' && <CodingPractice />}
          {page === 'Review' && <div className="card"><h3>Review</h3><p>Review workspace is coming soon.</p></div>}
          {page === 'Interview' && <div className="card"><h3>Interview</h3><p>Interview workspace is coming soon.</p></div>}
        </div>
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
