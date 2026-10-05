import { useState, useEffect, useRef } from 'react'
import { useAuthStore } from './store/authStore'
import { apiRequest } from './apiClient'

export default function Interview() {
  const { session } = useAuthStore()
  const token = session?.access_token

  // Session configuration state
  const [roundType, setRoundType] = useState('technical')
  const [targetRole, setTargetRole] = useState('Software Engineer')
  const [totalQuestions, setTotalQuestions] = useState(3)

  // Active interview state
  const [activeSession, setActiveSession] = useState(null)
  const [currentTurn, setCurrentTurn] = useState(null)
  const [userAnswer, setUserAnswer] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [lastTurnFeedback, setLastTurnFeedback] = useState(null)
  const [sessionReport, setSessionReport] = useState(null)
  const [elapsedTime, setElapsedTime] = useState(0)
  const [error, setError] = useState('')

  const timerRef = useRef(null)
  const recognitionRef = useRef(null)
  const speechBaseTextRef = useRef('')

  // Initialize Web Speech Recognition if supported by browser
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'

      recognition.onresult = (event) => {
        let finalPhrase = ''
        let interimPhrase = ''

        for (let i = 0; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript
          if (event.results[i].isFinal) {
            finalPhrase += (finalPhrase ? ' ' : '') + transcript.trim()
          } else {
            interimPhrase += transcript
          }
        }

        const base = speechBaseTextRef.current ? speechBaseTextRef.current + ' ' : ''
        const finalPart = finalPhrase ? finalPhrase : ''
        const interimPart = interimPhrase ? (finalPart ? ' ' : '') + interimPhrase.trim() : ''
        setUserAnswer((base + finalPart + (interimPart ? ' ' + interimPart : '')).trim())
      }

      recognition.onerror = () => {
        setIsRecording(false)
      }

      recognition.onend = () => {
        setIsRecording(false)
      }

      recognitionRef.current = recognition
    }
  }, [])

  // Timer effect for answer duration
  useEffect(() => {
    if (currentTurn && !lastTurnFeedback && !sessionReport) {
      setElapsedTime(0)
      timerRef.current = setInterval(() => {
        setElapsedTime((prev) => prev + 1)
      }, 1000)
    } else {
      clearInterval(timerRef.current)
    }
    return () => clearInterval(timerRef.current)
  }, [currentTurn, lastTurnFeedback, sessionReport])

  function toggleRecording() {
    if (!recognitionRef.current) {
      alert('Speech recognition is not supported in this browser. Please type your answer or use Chrome/Edge.')
      return
    }

    if (isRecording) {
      recognitionRef.current.stop()
      setIsRecording(false)
      speechBaseTextRef.current = userAnswer.trim()
    } else {
      speechBaseTextRef.current = userAnswer.trim()
      try {
        recognitionRef.current.start()
        setIsRecording(true)
      } catch (err) {
        console.error(err)
      }
    }
  }

  async function handleStartInterview() {
    setError('')
    setSessionReport(null)
    setLastTurnFeedback(null)
    try {
      const created = await apiRequest(
        '/interview/sessions',
        {
          method: 'POST',
          body: JSON.stringify({
            round_type: roundType,
            target_role: targetRole,
            total_questions: Number(totalQuestions),
          }),
        },
        token
      )
      setActiveSession(created)
      await loadNextQuestion(created.id)
    } catch (err) {
      setError(err.message || 'Failed to start interview')
    }
  }

  async function loadNextQuestion(sessionId = activeSession?.id) {
    setUserAnswer('')
    setLastTurnFeedback(null)
    try {
      const next = await apiRequest(`/interview/sessions/${sessionId}/next`, { method: 'GET' }, token)
      if (next.is_complete) {
        await finishInterview(sessionId)
      } else {
        setCurrentTurn(next)
      }
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSubmitAnswer() {
    if (!userAnswer.trim()) {
      setError('Please provide an answer (speech or text) before submitting.')
      return
    }
    setError('')
    setSubmitting(true)
    if (isRecording && recognitionRef.current) {
      recognitionRef.current.stop()
      setIsRecording(false)
    }

    try {
      const evaluation = await apiRequest(
        `/interview/sessions/${activeSession.id}/answer`,
        {
          method: 'POST',
          body: JSON.stringify({
            turn_number: currentTurn.turn_number,
            answer_transcript: userAnswer,
            time_taken_s: elapsedTime,
          }),
        },
        token
      )
      setLastTurnFeedback(evaluation)
    } catch (err) {
      setError(err.message || 'Failed to evaluate answer')
    } finally {
      setSubmitting(false)
    }
  }

  async function finishInterview(sessionId = activeSession?.id) {
    try {
      const summary = await apiRequest(`/interview/sessions/${sessionId}/complete`, { method: 'POST' }, token)
      setSessionReport(summary)
      setCurrentTurn(null)
      setLastTurnFeedback(null)
    } catch (err) {
      setError(err.message)
    }
  }

  // Final Evaluation Report View
  if (sessionReport) {
    return (
      <div className="interview-panel">
        <div className="eyebrow">Interview Completed</div>
        <h2>{sessionReport.round_type.toUpperCase()} Round Performance</h2>
        <div className="score-summary-card">
          <div className="score-circle">
            <span className="big-number">{Math.round(sessionReport.overall_score)}</span>
            <span className="out-of">/ 100</span>
          </div>
          <p className="summary-desc">{sessionReport.summary_feedback}</p>
        </div>

        <div className="feedback-split">
          <div className="feedback-col strengths">
            <h4>Key Strengths</h4>
            <ul>
              {sessionReport.strengths.length > 0 ? (
                sessionReport.strengths.map((s, i) => <li key={i}>{s}</li>)
              ) : (
                <li>Foundational participation recorded.</li>
              )}
            </ul>
          </div>
          <div className="feedback-col improvements">
            <h4>Recommended Improvements</h4>
            <ul>
              {sessionReport.improvements.length > 0 ? (
                sessionReport.improvements.map((imp, i) => <li key={i}>{imp}</li>)
              ) : (
                <li>Continue practicing with harder multi-part scenarios.</li>
              )}
            </ul>
          </div>
        </div>

        <button className="primary" onClick={() => { setActiveSession(null); setSessionReport(null) }}>
          Start Another Mock Interview
        </button>
      </div>
    )
  }

  // Pre-interview Setup View
  if (!activeSession || !currentTurn) {
    return (
      <div className="interview-panel">
        <div className="eyebrow">AI Mock Interview Room</div>
        <h2>Practice Live Placement Rounds</h2>
        <p>Dynamic technical and HR interview rounds with speech-to-text input and instant rubric-based scoring.</p>

        {error && <p className="error">{error}</p>}

        <div className="setup-grid">
          <label>
            <span>Round Type</span>
            <select value={roundType} onChange={(e) => setRoundType(e.target.value)}>
              <option value="technical">Technical Round (DSA, System Design, Core CS)</option>
              <option value="hr">HR & Behavioral Round (STAR Method, Culture Fit)</option>
            </select>
          </label>

          <label>
            <span>Target Role</span>
            <input
              type="text"
              value={targetRole}
              onChange={(e) => setTargetRole(e.target.value)}
              placeholder="e.g. Full Stack Developer, ML Engineer"
            />
          </label>

          <label>
            <span>Question Count</span>
            <select value={totalQuestions} onChange={(e) => setTotalQuestions(Number(e.target.value))}>
              <option value={2}>2 Questions (Quick Sprint)</option>
              <option value={3}>3 Questions (Standard Mock)</option>
              <option value={5}>5 Questions (Comprehensive)</option>
            </select>
          </label>
        </div>

        <button className="primary-action" onClick={handleStartInterview}>
          Enter Interview Room
        </button>
      </div>
    )
  }

  // Active Question / Feedback Turn View
  return (
    <div className="interview-panel">
      <div className="interview-header">
        <div>
          <span className="eyebrow">{activeSession.round_type.toUpperCase()} ROUND</span>
          <span className="badge">{currentTurn.question?.topic}</span>
        </div>
        <div className="turn-indicator">
          Question {currentTurn.turn_number} of {currentTurn.total_questions}
          <span className="timer-badge">⏱ {elapsedTime}s</span>
        </div>
      </div>

      <div className="question-box">
        <h3>{currentTurn.question?.question}</h3>
        {currentTurn.question?.context_hint && (
          <p className="hint-text">💡 Hint: {currentTurn.question.context_hint}</p>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {!lastTurnFeedback ? (
        <div className="answer-section">
          <div className="voice-controls">
            <button
              type="button"
              className={`mic-button ${isRecording ? 'recording' : ''}`}
              onClick={toggleRecording}
            >
              {isRecording ? '⏹ Stop Speaking' : '🎤 Speak Answer (Live STT)'}
            </button>
            <span className="voice-note">
              {isRecording ? 'Listening... Speak clearly into your mic.' : 'Or type your answer below:'}
            </span>
          </div>

          <textarea
            className="answer-textarea"
            rows={5}
            value={userAnswer}
            onChange={(e) => setUserAnswer(e.target.value)}
            placeholder="Type or dictate your answer here..."
          />

          <div className="turn-actions">
            <button className="primary" onClick={handleSubmitAnswer} disabled={submitting}>
              {submitting ? 'Analyzing with Rubric AI...' : 'Submit Answer for Rubric Evaluation'}
            </button>
          </div>
        </div>
      ) : (
        <div className="turn-feedback-card">
          <h4>Turn {lastTurnFeedback.turn_number} Evaluation</h4>
          <div className="rubric-meters">
            <div className="meter-item">
              <span>{activeSession.round_type === 'technical' ? 'Technical Accuracy' : 'STAR / Context'}</span>
              <strong>{lastTurnFeedback.scores.accuracy}/10</strong>
            </div>
            <div className="meter-item">
              <span>{activeSession.round_type === 'technical' ? 'Structure & Trade-offs' : 'Ownership & Fit'}</span>
              <strong>{lastTurnFeedback.scores.structure}/10</strong>
            </div>
            <div className="meter-item">
              <span>Communication Clarity</span>
              <strong>{lastTurnFeedback.scores.communication}/10</strong>
            </div>
            <div className="meter-item total">
              <span>Turn Score</span>
              <strong className="high-score">{Math.round(lastTurnFeedback.scores.overall)}/100</strong>
            </div>
          </div>

          <div className="coach-feedback">
            <strong>AI Coach Feedback:</strong>
            <p>{lastTurnFeedback.feedback}</p>
          </div>

          <details className="model-answer-details">
            <summary>View Reference Model Answer</summary>
            <p>{lastTurnFeedback.model_answer}</p>
          </details>

          <div className="turn-actions">
            {lastTurnFeedback.is_complete ? (
              <button className="primary" onClick={() => finishInterview()}>
                View Final Placement Report
              </button>
            ) : (
              <button className="primary" onClick={() => loadNextQuestion()}>
                Next Question ({lastTurnFeedback.next_turn_number} of {activeSession.total_questions}) &rarr;
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
