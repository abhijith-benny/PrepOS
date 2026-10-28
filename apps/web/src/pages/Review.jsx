import { useEffect, useState, useRef } from 'react'
import { apiRequest } from '../apiClient'

export function Review() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [stats, setStats] = useState(null)
  const [dueCards, setDueCards] = useState([])
  const [currentIndex, setCurrentIndex] = useState(0)

  // Review interaction state
  const [selectedAnswer, setSelectedAnswer] = useState('')
  const [confidence, setConfidence] = useState('medium')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [reviewResult, setReviewResult] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [genMessage, setGenMessage] = useState('')

  // Timer
  const [seconds, setSeconds] = useState(0)
  const timerRef = useRef(null)

  // Session summary counters
  const [sessionCompleted, setSessionCompleted] = useState(false)
  const [sessionStats, setSessionStats] = useState({ total: 0, correct: 0 })

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [statsData, dueData] = await Promise.all([
        apiRequest('/srs/stats'),
        apiRequest('/srs/due?limit=20'),
      ])
      setStats(statsData)
      setDueCards(dueData || [])
      setCurrentIndex(0)
      setReviewResult(null)
      setSelectedAnswer('')
      setSessionCompleted(false)
      setSessionStats({ total: 0, correct: 0 })
    } catch (err) {
      setError(err.message || 'Failed to load review data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // Start timer on new question
  useEffect(() => {
    if (loading || sessionCompleted || reviewResult || dueCards.length === 0) {
      clearInterval(timerRef.current)
      return
    }
    setSeconds(0)
    timerRef.current = setInterval(() => {
      setSeconds((prev) => prev + 1)
    }, 1000)

    return () => clearInterval(timerRef.current)
  }, [currentIndex, reviewResult, loading, sessionCompleted, dueCards.length])

  async function handleGenerateCards() {
    setGenerating(true)
    setGenMessage('')
    setError('')
    try {
      const res = await apiRequest('/srs/generate', {
        method: 'POST',
        body: JSON.stringify({ count: 10 }),
      })
      const count = res.created_count || 0
      setGenMessage(
        count > 0
          ? `Generated ${count} new review card${count > 1 ? 's' : ''} from your weak topics!`
          : 'No new weak topics need cards right now.'
      )
      // Reload due cards
      const [newStats, newDue] = await Promise.all([
        apiRequest('/srs/stats'),
        apiRequest('/srs/due?limit=20'),
      ])
      setStats(newStats)
      setDueCards(newDue || [])
      setCurrentIndex(0)
    } catch (err) {
      setError(err.message || 'Failed to generate review cards')
    } finally {
      setGenerating(false)
    }
  }

  async function handleSubmitReview(e) {
    if (e) e.preventDefault()
    if (!selectedAnswer || submitting) return

    setSubmitting(true)
    setSubmitError('')

    const currentCard = dueCards[currentIndex]
    try {
      const result = await apiRequest(`/srs/cards/${currentCard.id}/review`, {
        method: 'POST',
        body: JSON.stringify({
          answer: selectedAnswer,
          time_taken_s: Math.max(1, seconds),
          confidence,
        }),
      })

      setReviewResult(result)
      setSessionStats((prev) => ({
        total: prev.total + 1,
        correct: prev.correct + (result.correct ? 1 : 0),
      }))

      // Update stats in background
      apiRequest('/srs/stats').then((s) => setStats(s)).catch(() => {})
    } catch (err) {
      setSubmitError(err.message || 'Submission failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  function handleNextCard() {
    if (currentIndex + 1 < dueCards.length) {
      setCurrentIndex((prev) => prev + 1)
      setSelectedAnswer('')
      setReviewResult(null)
      setSubmitError('')
    } else {
      setSessionCompleted(true)
    }
  }

  if (loading) {
    return (
      <div className="srs-page">
        <div className="page-heading">
          <div>
            <div className="eyebrow">Spaced Repetition</div>
            <h2>Memory Review</h2>
          </div>
        </div>
        <div className="empty-inline">Loading your review queue...</div>
      </div>
    )
  }

  const currentCard = dueCards[currentIndex]
  const question = currentCard?.question

  // Calculate forecast max for bar scaling
  const forecastData = stats?.forecast || [0, 0, 0, 0, 0, 0, 0]
  const maxForecast = Math.max(1, ...forecastData)
  const dayLabels = ['Today', '+1d', '+2d', '+3d', '+4d', '+5d', '+6d']

  return (
    <div className="srs-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">Spaced Repetition Review (M3)</div>
          <h2>Memory Review Workspace</h2>
          <p>
            Strengthen weak concepts and learn from past mistakes using adaptive spaced intervals.
          </p>
        </div>
        <div className="srs-actions">
          <button
            className="secondary"
            onClick={handleGenerateCards}
            disabled={generating}
          >
            {generating ? 'Generating...' : '+ Generate Cards'}
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {genMessage && <div className="info-banner">{genMessage}</div>}

      {/* STATS & FORECAST BANNER */}
      <div className="srs-stats-grid">
        <div className="stat-card">
          <span className="stat-label">Due Today</span>
          <strong>{stats?.due_today ?? 0}</strong>
          <span className="stat-note">{dueCards.length} in current queue</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Reviewed Today</span>
          <strong>{stats?.reviewed_today ?? 0}</strong>
          <span className="stat-note">Streak: {stats?.streak_days ?? 0} day{stats?.streak_days === 1 ? '' : 's'}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Estimated Retention</span>
          <strong>{Math.round((stats?.retention_estimate ?? 1.0) * 100)}%</strong>
          <span className="stat-note">Algorithm: {(stats?.algorithm || 'sm2').toUpperCase()}</span>
        </div>
        <div className="stat-card srs-forecast-card">
          <span className="stat-label">7-Day Review Forecast</span>
          <div className="srs-forecast-chart">
            {forecastData.map((count, idx) => {
              const heightPct = Math.round((count / maxForecast) * 100)
              const isToday = idx === 0
              return (
                <div key={idx} className="srs-bar-col" title={`${dayLabels[idx]}: ${count} cards`}>
                  <div className="srs-bar-track">
                    <div
                      className={`srs-bar-fill ${isToday ? 'today' : ''}`}
                      style={{ height: `${Math.max(8, heightPct)}%` }}
                    >
                      <span className="srs-bar-value">{count}</span>
                    </div>
                  </div>
                  <span className="srs-bar-label">{dayLabels[idx]}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* MAIN REVIEW INTERFACE */}
      {sessionCompleted ? (
        <div className="card srs-summary-card">
          <div className="srs-summary-badge">Session Complete!</div>
          <h3>Great work reinforcing your knowledge</h3>
          <p>
            You reviewed <strong>{sessionStats.total}</strong> card{sessionStats.total === 1 ? '' : 's'} with{' '}
            <strong>
              {sessionStats.total > 0
                ? Math.round((sessionStats.correct / sessionStats.total) * 100)
                : 0}%
            </strong>{' '}
            accuracy.
          </p>
          <div className="srs-summary-actions">
            <button onClick={loadData}>Start Another Deck</button>
            <a href="/" className="mock-test-action secondary">
              Back to Dashboard
            </a>
          </div>
        </div>
      ) : dueCards.length === 0 ? (
        <div className="card srs-empty-card">
          <div className="srs-empty-icon">&#10003;</div>
          <h3>You are all caught up for today!</h3>
          <p>
            There are no due cards in your review queue right now. You can generate new cards from your
            weak placement topics or check back tomorrow.
          </p>
          <div className="srs-empty-actions">
            <button onClick={handleGenerateCards} disabled={generating}>
              {generating ? 'Generating...' : 'Generate Cards from Weak Topics'}
            </button>
          </div>
        </div>
      ) : (
        <div className="card srs-card-container">
          {/* Progress bar */}
          <div className="srs-progress-header">
            <div className="srs-progress-meta">
              <span>
                Card <strong>{currentIndex + 1}</strong> of <strong>{dueCards.length}</strong>
              </span>
              <span className="srs-timer">&#9201; {seconds}s</span>
            </div>
            <div className="srs-progress-track">
              <div
                className="srs-progress-bar"
                style={{
                  width: `${Math.round(((currentIndex + (reviewResult ? 1 : 0)) / dueCards.length) * 100)}%`,
                }}
              />
            </div>
          </div>

          {/* Card meta badges */}
          <div className="srs-card-badges">
            <span className="status-pill">{currentCard.origin}</span>
            <span className="status-pill">{currentCard.state}</span>
            {currentCard.repetitions > 0 && (
              <span className="status-pill verified">
                Rep #{currentCard.repetitions}
              </span>
            )}
            {currentCard.lapses > 0 && (
              <span className="status-pill failed_to_verify">
                {currentCard.lapses} lapse{currentCard.lapses === 1 ? '' : 's'}
              </span>
            )}
          </div>

          {/* Question Body */}
          <div className="srs-question-body">
            <h3>{question?.body || 'Question prompt'}</h3>
          </div>

          {/* Option list */}
          <div className="srs-options-grid">
            {(question?.options && question.options.length > 0
              ? question.options
              : ['A', 'B', 'C', 'D']
            ).map((opt, i) => {
              const isSelected = selectedAnswer === opt
              let optClass = 'srs-option-btn'
              if (isSelected) optClass += ' selected'
              if (reviewResult) {
                if (opt.toLowerCase() === reviewResult.expected_answer?.toLowerCase()) {
                  optClass += ' correct-answer'
                } else if (isSelected && !reviewResult.correct) {
                  optClass += ' wrong-answer'
                }
              }

              return (
                <button
                  key={i}
                  type="button"
                  className={optClass}
                  onClick={() => !reviewResult && setSelectedAnswer(opt)}
                  disabled={reviewResult !== null}
                >
                  <span className="srs-option-key">
                    {String.fromCharCode(65 + i)}
                  </span>
                  <span className="srs-option-text">{opt}</span>
                </button>
              )
            })}
          </div>

          {/* Confidence Selector (before submission) */}
          {!reviewResult && (
            <div className="srs-confidence-row">
              <span className="srs-confidence-label">Confidence:</span>
              <div className="srs-confidence-pills">
                {[
                  { id: 'low', label: 'Hesitant / Hard' },
                  { id: 'medium', label: 'Normal / Good' },
                  { id: 'high', label: 'Confident / Easy' },
                ].map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    className={`srs-conf-pill ${confidence === c.id ? 'active' : ''}`}
                    onClick={() => setConfidence(c.id)}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {submitError && <div className="error-banner">{submitError}</div>}

          {/* Action Row */}
          {!reviewResult ? (
            <div className="srs-submit-row">
              <button
                type="button"
                onClick={handleSubmitReview}
                disabled={!selectedAnswer || submitting}
              >
                {submitting ? 'Checking answer...' : 'Submit Answer'}
              </button>
            </div>
          ) : (
            /* Post-Submission Result Feedback */
            <div className="srs-feedback-panel">
              <div
                className={`srs-feedback-status ${
                  reviewResult.correct ? 'status-correct' : 'status-incorrect'
                }`}
              >
                <div className="srs-status-icon">
                  {reviewResult.correct ? '\u2713 Correct!' : '\u2717 Incorrect'}
                </div>
                <div className="srs-status-details">
                  <span>Quality Grade: <strong>{reviewResult.quality} / 5</strong></span>
                  <span>
                    Next Review:{' '}
                    <strong>
                      {reviewResult.interval_days === 1
                        ? 'Tomorrow'
                        : `in ${reviewResult.interval_days} days`}
                    </strong>
                  </span>
                </div>
              </div>

              {reviewResult.explanation && (
                <div className="srs-explanation-box">
                  <strong>Explanation:</strong>
                  <p>{reviewResult.explanation}</p>
                </div>
              )}

              <div className="srs-next-row">
                <button type="button" onClick={handleNextCard}>
                  {currentIndex + 1 < dueCards.length ? 'Next Card \u2192' : 'Finish Session \u2192'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
