import { useEffect, useRef, useState } from "react"
import "./App.css"
const API_URL = import.meta.env.VITE_API_URL || "https://navyasrees-codeweave-backend.hf.space"

const EXAMPLES = [
  "what breaks if I change OAuth2PasswordBearer?",
  "show me all code related to authentication",
  "where is dependency injection resolved?",
  "explain how routing works in fastapi",
]

/* tiny inline icons (no external deps) */
const Icon = {
  Search: (props) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
    </svg>
  ),
  Sparkle: (props) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6 5.6 18.4" />
    </svg>
  ),
  ArrowRight: (props) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M5 12h14M13 5l7 7-7 7" />
    </svg>
  ),
  Code: (props) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="m18 16 4-4-4-4M6 8l-4 4 4 4M14.5 4l-5 16" />
    </svg>
  ),
  Graph: (props) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" />
      <circle cx="6" cy="18" r="2.5" /><circle cx="18" cy="18" r="2.5" />
      <path d="M8 7l8 9M8 17l8-9M6 8.5v7M18 8.5v7" />
    </svg>
  ),
  Brain: (props) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 5a3 3 0 0 0-3-3 3 3 0 0 0-3 3v0a3 3 0 0 0-3 3 3 3 0 0 0 1 2.2v.8a3 3 0 0 0 1 2.2v.8a3 3 0 0 0 3 3 3 3 0 0 0 3-3M12 5a3 3 0 0 1 3-3 3 3 0 0 1 3 3v0a3 3 0 0 1 3 3 3 3 0 0 1-1 2.2v.8a3 3 0 0 1-1 2.2v.8a3 3 0 0 1-3 3 3 3 0 0 1-3-3M12 5v14" />
    </svg>
  ),
  Layers: (props) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="m12 2 9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 17l9 5 9-5" />
    </svg>
  ),
  Copy: (props) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  ),
  Check: (props) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  ),
  Alert: (props) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01" />
    </svg>
  ),
  Clock: (props) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" />
    </svg>
  ),
}

export default function App() {
  const [question, setQuestion] = useState("")
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [focused, setFocused] = useState(false)
  const [copied, setCopied] = useState(false)
  const [elapsed, setElapsed] = useState(null)
  const inputRef = useRef(null)

  /* Cmd/Ctrl+K to focus the search */
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        inputRef.current?.focus()
      }
      if (e.key === "Escape" && document.activeElement === inputRef.current) {
        inputRef.current?.blur()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const handleQuery = async (q) => {
    const text = (q ?? question).trim()
    if (!text) return
    setQuestion(text)
    setLoading(true)
    setResult(null)
    setError(null)
    setElapsed(null)
    const t0 = performance.now()
    try {
      const res = await fetch(`${API_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      })
      if (!res.ok) throw new Error(`Server returned ${res.status}`)
      const data = await res.json()
      setResult(data)
      setElapsed(Math.round(performance.now() - t0))
    } catch (err) {
      setError(err.message || "Failed to reach the indexer at localhost:8000")
    } finally {
      setLoading(false)
    }
  }

  const copyAnswer = async () => {
    if (!result?.answer) return
    try {
      await navigator.clipboard.writeText(result.answer)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch { /* clipboard blocked */ }
  }

  return (
    <div className="app">
      {/* ============ NAV ============ */}
      <nav className="nav">
        <div className="container nav-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden>
              <Icon.Layers />
            </span>
            <span className="brand-name">Code<span>Weave</span></span>
          </div>
          <div className="nav-actions">
            <span className="pill" title="Indexed codebase">
              <Icon.Code style={{ width: 13, height: 13, color: "var(--accent-2)" }} />
              fastapi
            </span>
            <span className="pill">
              <span className={`pill-dot ${error ? "err" : ""}`} />
              {error ? "offline" : "live"}
            </span>
          </div>
        </div>
      </nav>

      {/* ============ HERO ============ */}
      <section className="container hero">
        <span className="hero-eyebrow">
          <Icon.Sparkle />
          Context graph · semantic search · AI answers
        </span>
        <h1 className="hero-title">
          Ask your codebase. <br />
          <span className="grad">Get the full picture.</span>
        </h1>
        <p className="hero-sub">
          CodeWeave indexes functions, calls, modules, docs, and issues into a context graph —
          so you can ask what breaks, what depends on what, and what a piece of code actually does.
        </p>

        {/* ============ SEARCH ============ */}
        <div className={`search-wrap ${focused ? "focused" : ""}`}>
          <div className="search-glow" aria-hidden />
          <div className="search">
            <Icon.Search className="search-icon" />
            <input
              ref={inputRef}
              className="search-input"
              placeholder='Ask anything — "what breaks if I change OAuth2PasswordBearer?"'
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={(e) => e.key === "Enter" && handleQuery()}
              aria-label="Ask the codebase"
            />
            <span className="search-kbd">
              <span className="kbd">⌘</span><span className="kbd">K</span>
            </span>
            <button
              className="btn-ask"
              onClick={() => handleQuery()}
              disabled={loading || !question.trim()}
            >
              {loading ? (<><span className="spinner" /> Thinking…</>) : (<>Ask <Icon.ArrowRight /></>)}
            </button>
          </div>
        </div>

        {/* ============ EXAMPLE CHIPS ============ */}
        {!result && !loading && !error && (
          <div className="examples">
            <div className="examples-label">Try one of these</div>
            {EXAMPLES.map((ex) => (
              <button key={ex} className="chip" onClick={() => handleQuery(ex)}>
                <Icon.Sparkle />
                {ex}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* ============ RESULT / LOADING / ERROR / EMPTY ============ */}
      <section className="container" style={{ flex: 1 }}>
        {loading && (
          <div className="skeleton">
            <div className="skeleton-meta">
              <div className="skeleton-bar" />
              <div className="skeleton-bar" />
              <div className="skeleton-bar" />
            </div>
            <div className="skeleton-card">
              <div className="skeleton-line w-90" />
              <div className="skeleton-line w-75" />
              <div className="skeleton-line w-90" />
              <div className="skeleton-line w-60" />
              <div className="skeleton-line w-40" />
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="error-card">
            <span className="icon"><Icon.Alert /></span>
            <div>
              <h4>Couldn't reach the indexer</h4>
              <p>{error}. Make sure the FastAPI backend is running on <span className="kbd">localhost:8000</span>.</p>
            </div>
          </div>
        )}

        {result && !loading && (
          <div className="result">
            <div className="result-meta">
              <span className="badge accent">
                <span className="badge-label">mode</span>
                <span className="badge-value">{result.mode}</span>
              </span>
              <span className="badge cyan">
                <span className="badge-label">nodes</span>
                <span className="badge-value">{result.node_count}</span>
              </span>
              {elapsed != null && (
                <span className="badge">
                  <Icon.Clock style={{ width: 12, height: 12 }} />
                  <span className="badge-value">{elapsed} ms</span>
                </span>
              )}
              <span className="result-spacer" />
              <button className="btn-ghost" onClick={copyAnswer} aria-label="Copy answer">
                {copied ? <><Icon.Check /> copied</> : <><Icon.Copy /> copy</>}
              </button>
            </div>

            <div className="answer-card">
              <div className="answer-head">
                <span className="dots">
                  <span className="dot r" /><span className="dot y" /><span className="dot g" />
                </span>
                <span className="title">answer · {result.mode}</span>
              </div>
              <div className="answer-body">{result.answer}</div>
            </div>
          </div>
        )}

        {!result && !loading && !error && (
          <div className="features">
            <div className="feature">
              <span className="icon"><Icon.Graph /></span>
              <h3>Context graph</h3>
              <p>Functions, calls, modules, docs and issues stitched together so you can trace impact across the whole repo.</p>
            </div>
            <div className="feature">
              <span className="icon"><Icon.Brain /></span>
              <h3>Semantic search</h3>
              <p>Embedding-backed lookup means you don't need to remember the exact name — describe the behavior you want.</p>
            </div>
            <div className="feature">
              <span className="icon"><Icon.Code /></span>
              <h3>Plain-English answers</h3>
              <p>Ask "what breaks if I change X?" and get a grounded summary backed by real nodes from the indexed graph.</p>
            </div>
          </div>
        )}
      </section>

      {/* ============ FOOTER ============ */}
      <footer className="footer">
        <div className="footer-line" />
        <div className="footer-text">
          CodeWeave <span className="dot">·</span> indexed graph of fastapi <span className="dot">·</span> press <span className="kbd">⌘</span> <span className="kbd">K</span> to search
        </div>
      </footer>
    </div>
  )
}
