import { createElement, useEffect, useRef, useState, useCallback } from "react"
import "./App.css"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

/* ------------------------------ constants ------------------------------ */

const DEFAULT_REPO = "fastapi"

const EXAMPLES_BY_REPO = {
  fastapi: [
    "what breaks if I change OAuth2PasswordBearer?",
    "show me all code related to authentication",
    "where is dependency injection resolved?",
    "explain how routing works in fastapi",
  ],
  __default: [
    "give me a high-level overview of this codebase",
    "what are the main entry points?",
    "how is configuration loaded?",
    "where is the most complex logic?",
  ],
}

const STAGES = [
  { key: "pending",        label: "Queued" },
  { key: "cloning",        label: "Cloning repo" },
  { key: "detecting",      label: "Detecting structure" },
  { key: "parsing",        label: "Parsing code" },
  { key: "building_graph", label: "Building context graph" },
  { key: "enriching",      label: "Enriching with docs and tests" },
  { key: "embedding",      label: "Embedding into vector store" },
  { key: "done",           label: "Ready to query" },
]

const STAGE_INDEX = Object.fromEntries(STAGES.map((s, i) => [s.key, i]))

/* ------------------------------ tiny localStorage helpers ------------------------------ */

const LS = {
  repos:   "cw.repos",
  active:  "cw.activeRepo",
  job:     "cw.activeJob",
}
const lsGet = (k, fallback) => {
  try { const v = localStorage.getItem(k); return v == null ? fallback : JSON.parse(v) }
  catch { return fallback }
}
const lsSet = (k, v) => {
  try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* quota / disabled */ }
}
const lsDel = (k) => { try { localStorage.removeItem(k) } catch { /* ignore */ } }

/* ------------------------------ icons ------------------------------ */

const Icon = {
  Search:    p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></svg>,
  Sparkle:   p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6 5.6 18.4" /></svg>,
  ArrowRight: p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M5 12h14M13 5l7 7-7 7" /></svg>,
  Code:      p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m18 16 4-4-4-4M6 8l-4 4 4 4M14.5 4l-5 16" /></svg>,
  Layers:    p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m12 2 9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 17l9 5 9-5" /></svg>,
  Github:    p => <svg viewBox="0 0 24 24" fill="currentColor" {...p}><path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56v-2c-3.2.7-3.87-1.37-3.87-1.37-.52-1.32-1.27-1.67-1.27-1.67-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.02 1.75 2.68 1.24 3.34.95.1-.74.4-1.24.72-1.53-2.55-.29-5.24-1.28-5.24-5.7 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.46.11-3.05 0 0 .96-.31 3.15 1.18a10.92 10.92 0 0 1 5.74 0c2.19-1.49 3.15-1.18 3.15-1.18.62 1.59.23 2.76.11 3.05.74.81 1.18 1.84 1.18 3.1 0 4.43-2.69 5.41-5.25 5.69.41.36.78 1.06.78 2.13v3.16c0 .31.21.67.8.56C20.21 21.39 23.5 17.08 23.5 12 23.5 5.65 18.35.5 12 .5z" /></svg>,
  Plus:      p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M12 5v14M5 12h14" /></svg>,
  ChevronDown: p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m6 9 6 6 6-6" /></svg>,
  Check:     p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M20 6 9 17l-5-5" /></svg>,
  Copy:      p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>,
  Alert:     p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01" /></svg>,
  Clock:     p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></svg>,
  Graph:     p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" /><circle cx="6" cy="18" r="2.5" /><circle cx="18" cy="18" r="2.5" /><path d="M8 7l8 9M8 17l8-9M6 8.5v7M18 8.5v7" /></svg>,
  Brain:     p => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M12 5a3 3 0 0 0-6 0 3 3 0 0 0-3 3 3 3 0 0 0 1 2.2v.8a3 3 0 0 0 1 2.2v.8a3 3 0 0 0 6 0M12 5a3 3 0 0 1 6 0 3 3 0 0 1 3 3 3 3 0 0 1-1 2.2v.8a3 3 0 0 1-1 2.2v.8a3 3 0 0 1-6 0M12 5v14" /></svg>,
}

/* ------------------------------ helpers ------------------------------ */

function inferRepoNameFromUrl(url) {
  try {
    const clean = url.trim().replace(/\.git$/, "").replace(/\/+$/, "")
    const parts = clean.split("/")
    return parts[parts.length - 1] || ""
  } catch { return "" }
}

function isValidGithubUrl(url) {
  if (!url) return false
  return /^https?:\/\/(www\.)?github\.com\/[^/]+\/[^/]+/i.test(url.trim())
}

/* ------------------------------ tiny markdown renderer ------------------------------
   Handles the subset LLMs typically emit: headings (##, ###, ####),
   bold (**x**), inline code (`x`), fenced code blocks (```),
   ordered/unordered lists, paragraphs, and links [t](u).
*/

function renderInline(text) {
  // ordered: code spans, bold, links — first-match-wins
  const pattern = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\[([^\]]+)\]\(([^)]+)\))/
  const out = []
  let remaining = text
  let key = 0
  while (remaining.length) {
    const m = remaining.match(pattern)
    if (!m) { out.push(remaining); break }
    if (m.index > 0) out.push(remaining.slice(0, m.index))
    const matched = m[0]
    if (matched.startsWith("`")) {
      out.push(<code key={key++}>{matched.slice(1, -1)}</code>)
    } else if (matched.startsWith("**")) {
      out.push(<strong key={key++}>{matched.slice(2, -2)}</strong>)
    } else if (matched.startsWith("[")) {
      out.push(<a key={key++} href={m[5]} target="_blank" rel="noreferrer">{m[4]}</a>)
    }
    remaining = remaining.slice(m.index + matched.length)
  }
  return out
}

function renderMarkdown(text) {
  if (!text) return null
  const lines = text.split("\n")
  const out = []
  let i = 0
  let key = 0

  while (i < lines.length) {
    const line = lines[i]

    // fenced code block
    if (/^```/.test(line)) {
      const codeLines = []
      i++
      while (i < lines.length && !/^```/.test(lines[i])) { codeLines.push(lines[i]); i++ }
      i++ // closing fence
      out.push(<pre key={key++}><code>{codeLines.join("\n")}</code></pre>)
      continue
    }

    // heading
    const h = line.match(/^(#{1,4})\s+(.*)$/)
    if (h) {
      const level = h[1].length        // 1..4
      const tag = `h${Math.min(level + 1, 4)}`  // ## -> h3, ### -> h4, etc; # -> h2
      out.push(createElement(tag, { key: key++ }, renderInline(h[2])))
      i++; continue
    }

    // ordered list
    if (/^\s*\d+\.\s/.test(line)) {
      const items = []
      while (i < lines.length && /^\s*\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s/, ""))
        i++
      }
      out.push(<ol key={key++}>{items.map((it, j) => <li key={j}>{renderInline(it)}</li>)}</ol>)
      continue
    }

    // unordered list
    if (/^\s*[-*]\s/.test(line)) {
      const items = []
      while (i < lines.length && /^\s*[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s/, ""))
        i++
      }
      out.push(<ul key={key++}>{items.map((it, j) => <li key={j}>{renderInline(it)}</li>)}</ul>)
      continue
    }

    // blank line — skip
    if (line.trim() === "") { i++; continue }

    // paragraph — collect consecutive non-blank, non-special lines
    const paraLines = []
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#{1,4}\s|```|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])
    ) {
      paraLines.push(lines[i]); i++
    }
    out.push(<p key={key++}>{renderInline(paraLines.join(" "))}</p>)
  }

  return out
}

/* ============================================================================
   App
   ============================================================================ */

export default function App() {
  const [repos, setRepos] = useState(() => {
    const stored = lsGet(LS.repos, [DEFAULT_REPO])
    return Array.isArray(stored) && stored.includes(DEFAULT_REPO) ? stored : [DEFAULT_REPO, ...(stored || []).filter(r => r !== DEFAULT_REPO)]
  })
  const [activeRepo, setActiveRepo] = useState(() => lsGet(LS.active, DEFAULT_REPO))
  const [view, setView] = useState(() => {
    // resume an in-flight indexing job if we left one mid-run
    const job = lsGet(LS.job, null)
    return job?.jobId ? "progress" : "query"
  })

  // index form
  const [githubUrl, setGithubUrl] = useState("")
  const [indexing, setIndexing] = useState(false)
  const [indexError, setIndexError] = useState(null)

  // active job + polling
  const [job, setJob] = useState(() => lsGet(LS.job, null))
  const pollTimerRef = useRef(null)

  // query
  const [question, setQuestion] = useState("")
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [focused, setFocused] = useState(false)
  const [copied, setCopied] = useState(false)
  const [elapsed, setElapsed] = useState(null)
  const inputRef = useRef(null)

  /* --- persist whenever core state changes --- */
  useEffect(() => { lsSet(LS.repos, repos) }, [repos])
  useEffect(() => { lsSet(LS.active, activeRepo) }, [activeRepo])
  useEffect(() => {
    if (job?.jobId) lsSet(LS.job, job)
    else lsDel(LS.job)
  }, [job])

  /* --- Cmd/Ctrl+K to focus search --- */
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        if (view === "query") inputRef.current?.focus()
      }
      if (e.key === "Escape" && document.activeElement === inputRef.current) inputRef.current?.blur()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [view])

  /* --- when entering query view, reset stale results --- */
  useEffect(() => {
    if (view === "query") {
      setResult(null)
      setError(null)
      setQuestion("")
    }
  }, [view, activeRepo])

  /* --- polling /status/{job_id} every 3s while a job is in progress --- */
  const pollStatus = useCallback(async (jobId) => {
    try {
      const res = await fetch(`${API_URL}/status/${jobId}`)
      if (!res.ok) throw new Error(`status ${res.status}`)
      const data = await res.json()

      if (data.error && !data.status) {
        // backend "Job not found" shape
        setJob(j => j ? { ...j, status: "error", message: data.error } : j)
        return { status: "error" }
      }

      setJob(j => j ? { ...j, ...data } : j)

      if (data.status === "done") {
        const repoName = data.repo_name || inferRepoNameFromUrl(job?.githubUrl || "")
        if (repoName) {
          setRepos(prev => prev.includes(repoName) ? prev : [...prev, repoName])
          setActiveRepo(repoName)
        }
      }
      return data
    } catch (e) {
      // network blip — don't kill the poll, just record once
      setJob(j => j ? { ...j, _pollError: e.message } : j)
      return null
    }
  }, [job?.githubUrl])

  useEffect(() => {
    if (!job?.jobId) return
    if (job.status === "done" || job.status === "error") return

    // immediate first poll, then every 3s
    pollStatus(job.jobId)
    pollTimerRef.current = setInterval(() => pollStatus(job.jobId), 3000)
    return () => clearInterval(pollTimerRef.current)
  }, [job?.jobId, job?.status, pollStatus])

  /* --- actions --- */

  const startIndex = async () => {
    const url = githubUrl.trim()
    setIndexError(null)
    if (!isValidGithubUrl(url)) {
      setIndexError("Please paste a valid GitHub URL like https://github.com/owner/repo")
      return
    }
    setIndexing(true)
    try {
      const res = await fetch(`${API_URL}/index`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: url }),
      })
      if (!res.ok) throw new Error(`Server returned ${res.status}`)
      const data = await res.json()
      if (!data.job_id) throw new Error("Backend did not return a job_id")

      setJob({ jobId: data.job_id, githubUrl: url, status: "pending", message: "Job created" })
      setView("progress")
      setGithubUrl("")
    } catch (e) {
      setIndexError(e.message || "Failed to start indexing")
    } finally {
      setIndexing(false)
    }
  }

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
        body: JSON.stringify({ question: text, repo_name: activeRepo }),
      })
      if (!res.ok) throw new Error(`Server returned ${res.status}`)
      const data = await res.json()
      setResult(data)
      setElapsed(Math.round(performance.now() - t0))
    } catch (err) {
      setError(err.message || `Failed to reach the indexer at ${API_URL}`)
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

  const dismissJob = () => {
    setJob(null)
    setView("query")
  }

  const removeRepo = (repoName) => {
    if (repoName === DEFAULT_REPO) return // don't allow removing default
    setRepos(prev => prev.filter(r => r !== repoName))
    if (activeRepo === repoName) setActiveRepo(DEFAULT_REPO)
  }

  /* ------------------------------ render ------------------------------ */

  const examples = EXAMPLES_BY_REPO[activeRepo] || EXAMPLES_BY_REPO.__default

  return (
    <div className="app">
      <TopNav
        repos={repos}
        activeRepo={activeRepo}
        onSelectRepo={(r) => { setActiveRepo(r); setView("query") }}
        onAddRepo={() => setView("index")}
        onRemoveRepo={removeRepo}
        view={view}
        offline={!!error}
      />

      {view === "query" && (
        <QueryView
          activeRepo={activeRepo}
          examples={examples}
          question={question} setQuestion={setQuestion}
          focused={focused} setFocused={setFocused}
          loading={loading} error={error} result={result} elapsed={elapsed}
          copied={copied} copyAnswer={copyAnswer}
          onSubmit={handleQuery} inputRef={inputRef}
          onAddRepo={() => setView("index")}
        />
      )}

      {view === "index" && (
        <IndexView
          githubUrl={githubUrl} setGithubUrl={setGithubUrl}
          indexing={indexing} indexError={indexError}
          onSubmit={startIndex}
          onCancel={() => setView("query")}
          existingRepos={repos}
        />
      )}

      {view === "progress" && job && (
        <ProgressView
          job={job}
          onDone={() => setView("query")}
          onCancel={dismissJob}
        />
      )}

      <Footer />
    </div>
  )
}

/* ============================================================================
   TopNav (with repo selector dropdown)
   ============================================================================ */

function TopNav({ repos, activeRepo, onSelectRepo, onAddRepo, onRemoveRepo, view, offline }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [])

  return (
    <nav className="nav">
      <div className="container nav-inner">
        <div className="brand">
          <span className="brand-mark" aria-hidden><Icon.Layers /></span>
          <span className="brand-name">Code<span>Weave</span></span>
        </div>

        <div className="nav-actions">
          <div className="repo-select" ref={ref}>
            <button
              className="repo-trigger"
              onClick={() => setOpen(o => !o)}
              aria-haspopup="menu"
              aria-expanded={open}
              title="Switch repository"
            >
              <Icon.Github style={{ width: 13, height: 13, color: "var(--text-dim)" }} />
              <span className="repo-name">{activeRepo}</span>
              <Icon.ChevronDown style={{ width: 12, height: 12, color: "var(--text-muted)" }} />
            </button>
            {open && (
              <div className="repo-menu" role="menu">
                <div className="repo-menu-label">Indexed repos</div>
                {repos.map((r) => (
                  <div key={r} className={`repo-menu-item ${r === activeRepo ? "active" : ""}`}>
                    <button
                      className="repo-menu-pick"
                      onClick={() => { onSelectRepo(r); setOpen(false) }}
                      role="menuitemradio"
                      aria-checked={r === activeRepo}
                    >
                      <span className="repo-menu-tick">{r === activeRepo ? <Icon.Check /> : null}</span>
                      <Icon.Github style={{ width: 12, height: 12, opacity: 0.7 }} />
                      <span>{r}</span>
                    </button>
                    {r !== DEFAULT_REPO && (
                      <button
                        className="repo-menu-remove"
                        onClick={(e) => { e.stopPropagation(); onRemoveRepo(r) }}
                        title="Remove from list"
                        aria-label={`Remove ${r}`}
                      >×</button>
                    )}
                  </div>
                ))}
                <div className="repo-menu-divider" />
                <button
                  className="repo-menu-pick repo-menu-add"
                  onClick={() => { onAddRepo(); setOpen(false) }}
                  role="menuitem"
                >
                  <Icon.Plus style={{ width: 13, height: 13 }} />
                  <span>Index a new repo</span>
                </button>
              </div>
            )}
          </div>

          {view !== "index" && (
            <button className="btn-outline" onClick={onAddRepo} title="Index a new GitHub repo">
              <Icon.Plus style={{ width: 13, height: 13 }} />
              <span>Add repo</span>
            </button>
          )}

          <span className="pill">
            <span className={`pill-dot ${offline ? "err" : ""}`} />
            {offline ? "offline" : "live"}
          </span>
        </div>
      </div>
    </nav>
  )
}

/* ============================================================================
   QueryView
   ============================================================================ */

function QueryView({
  activeRepo, examples,
  question, setQuestion, focused, setFocused,
  loading, error, result, elapsed,
  copied, copyAnswer,
  onSubmit, inputRef, onAddRepo,
}) {
  return (
    <>
      <section className="container hero">
        <span className="hero-eyebrow">
          <Icon.Sparkle />
          Asking <span style={{ color: "var(--text-hi)", marginLeft: 4 }}>{activeRepo}</span>
        </span>
        <h1 className="hero-title">
          Ask your codebase. <br />
          <span className="grad">Get the full picture.</span>
        </h1>
        <p className="hero-sub">
          CodeWeave indexes functions, calls, modules, docs, and tests into a context graph —
          ask what breaks, what depends on what, and what a piece of code actually does.
        </p>

        <div className={`search-wrap ${focused ? "focused" : ""}`}>
          <div className="search-glow" aria-hidden />
          <div className="search">
            <Icon.Search className="search-icon" />
            <input
              ref={inputRef}
              className="search-input"
              placeholder={`Ask anything about ${activeRepo}…`}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={(e) => e.key === "Enter" && onSubmit()}
              aria-label="Ask the codebase"
            />
            <span className="search-kbd">
              <span className="kbd">⌘</span><span className="kbd">K</span>
            </span>
            <button
              className="btn-ask"
              onClick={() => onSubmit()}
              disabled={loading || !question.trim()}
            >
              {loading ? (<><span className="spinner" /> Thinking…</>) : (<>Ask <Icon.ArrowRight /></>)}
            </button>
          </div>
        </div>

        {!result && !loading && !error && (
          <div className="examples">
            <div className="examples-label">Try one of these</div>
            {examples.map((ex) => (
              <button key={ex} className="chip" onClick={() => onSubmit(ex)}>
                <Icon.Sparkle />
                {ex}
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="container" style={{ flex: 1 }}>
        {loading && <SkeletonResult />}

        {error && !loading && (
          <div className="error-card">
            <span className="icon"><Icon.Alert /></span>
            <div>
              <h4>Couldn't reach the indexer</h4>
              <p>{error}. Make sure the backend is running and reachable at <span className="kbd">{API_URL}</span>.</p>
            </div>
          </div>
        )}

        {result && !loading && (
          <ResultCard result={result} elapsed={elapsed} copied={copied} onCopy={copyAnswer} />
        )}

        {!result && !loading && !error && (
          <div className="features">
            <Feature icon={<Icon.Graph />} title="Context graph" desc="Functions, calls, modules, docs and tests stitched together — trace impact across the whole repo." />
            <Feature icon={<Icon.Brain />} title="Semantic search" desc="Embedding-backed lookup means you don't need exact names — describe the behavior you want." />
            <Feature icon={<Icon.Code />} title="Plain-English answers" desc='Ask "what breaks if I change X?" and get a grounded summary backed by real graph nodes.' />
            <Feature icon={<Icon.Plus />} title="Any GitHub repo" desc="Paste a URL and CodeWeave will clone, parse, embed, and serve it." onClick={onAddRepo} cta="Index one →" />
          </div>
        )}
      </section>
    </>
  )
}

function Feature({ icon, title, desc, onClick, cta }) {
  return (
    <div className={`feature ${onClick ? "feature-clickable" : ""}`} onClick={onClick} role={onClick ? "button" : undefined} tabIndex={onClick ? 0 : undefined}>
      <span className="icon">{icon}</span>
      <h3>{title}</h3>
      <p>{desc}</p>
      {cta && <span className="feature-cta">{cta}</span>}
    </div>
  )
}

function SkeletonResult() {
  return (
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
  )
}

function ResultCard({ result, elapsed, copied, onCopy }) {
  return (
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
        <button className="btn-ghost" onClick={onCopy} aria-label="Copy answer">
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
        <div className="answer-body markdown">{renderMarkdown(result.answer)}</div>
      </div>
    </div>
  )
}

/* ============================================================================
   IndexView — paste GitHub URL, click "Index"
   ============================================================================ */

function IndexView({ githubUrl, setGithubUrl, indexing, indexError, onSubmit, onCancel, existingRepos }) {
  const inferredName = inferRepoNameFromUrl(githubUrl)
  const alreadyIndexed = inferredName && existingRepos.includes(inferredName)

  return (
    <section className="container index-view">
      <div className="index-eyebrow">
        <button className="btn-link" onClick={onCancel}>← Back</button>
      </div>

      <h1 className="hero-title" style={{ textAlign: "center", fontSize: "clamp(28px, 5vw, 44px)" }}>
        Index a <span className="grad">GitHub repo</span>
      </h1>
      <p className="hero-sub" style={{ textAlign: "center", margin: "12px auto 28px" }}>
        Paste a public GitHub repository URL. CodeWeave will clone it, parse the source,
        build a context graph, and embed it for semantic search.
      </p>

      <div className="index-card">
        <label className="index-label" htmlFor="ghurl">GitHub URL</label>
        <div className={`search ${indexing ? "" : ""}`} style={{ marginTop: 6 }}>
          <Icon.Github className="search-icon" style={{ color: "var(--text-dim)" }} />
          <input
            id="ghurl"
            className="search-input"
            placeholder="https://github.com/owner/repo"
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSubmit()}
            disabled={indexing}
            autoFocus
          />
          <button
            className="btn-ask"
            onClick={onSubmit}
            disabled={indexing || !githubUrl.trim()}
          >
            {indexing ? (<><span className="spinner" /> Starting…</>) : (<>Index <Icon.ArrowRight /></>)}
          </button>
        </div>

        {inferredName && (
          <div className="index-meta">
            Will index as <span className="code">{inferredName}</span>
            {alreadyIndexed && <span className="index-warn"> · already in your list — re-indexing will refresh it</span>}
          </div>
        )}

        {indexError && (
          <div className="error-card" style={{ margin: "20px 0 0", maxWidth: "100%" }}>
            <span className="icon"><Icon.Alert /></span>
            <div>
              <h4>Could not start the job</h4>
              <p>{indexError}</p>
            </div>
          </div>
        )}

        <div className="index-tips">
          <div className="index-tip">
            <Icon.Clock style={{ width: 13, height: 13 }} />
            <span>Indexing takes 1–10 minutes depending on repo size.</span>
          </div>
          <div className="index-tip">
            <Icon.Github style={{ width: 13, height: 13 }} />
            <span>Public repositories only.</span>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ============================================================================
   ProgressView — polls /status/{job_id} every 3s
   ============================================================================ */

function ProgressView({ job, onDone, onCancel }) {
  const currentIdx = STAGE_INDEX[job.status] ?? 0
  const isError = job.status === "error"
  const isDone = job.status === "done"
  const repoLabel = job.repo_name || inferRepoNameFromUrl(job.githubUrl || "") || "repository"

  return (
    <section className="container progress-view">
      <h1 className="hero-title" style={{ textAlign: "center", fontSize: "clamp(28px, 5vw, 44px)" }}>
        {isError ? <>Indexing <span className="grad" style={{ background: "linear-gradient(135deg,#f87171,#fbbf24)", WebkitBackgroundClip: "text", backgroundClip: "text" }}>failed</span></>
         : isDone ? <>Indexed <span className="grad">{repoLabel}</span></>
         : <>Indexing <span className="grad">{repoLabel}</span></>}
      </h1>
      <p className="hero-sub" style={{ textAlign: "center", margin: "12px auto 28px" }}>
        {isError ? "Something went wrong. See the details below."
         : isDone ? "Your repository is ready to query."
         : "This usually takes a few minutes. You can close this tab — we'll resume polling when you come back."}
      </p>

      <div className="stepper">
        {STAGES.map((stage, i) => {
          let state = "future"
          if (isError && i === currentIdx) state = "error"
          else if (i < currentIdx) state = "done"
          else if (i === currentIdx) state = (isDone ? "done" : "active")

          return (
            <div key={stage.key} className={`step step-${state}`}>
              <div className="step-marker">
                {state === "done" && <Icon.Check />}
                {state === "active" && <span className="step-spinner" />}
                {state === "error" && <Icon.Alert />}
                {state === "future" && <span className="step-dot" />}
              </div>
              <div className="step-body">
                <div className="step-label">{stage.label}</div>
                {state === "active" && job.message && (
                  <div className="step-message">{job.message}</div>
                )}
                {state === "error" && (job.error || job.message) && (
                  <div className="step-message err">{job.error || job.message}</div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="progress-meta">
        <span className="badge"><span className="badge-label">job</span><span className="badge-value">{job.jobId?.slice(0, 8)}…</span></span>
        <span className="badge"><span className="badge-label">status</span><span className="badge-value">{job.status}</span></span>
        {job._pollError && <span className="badge" title="Last poll failed; will retry"><span className="badge-label">poll</span><span className="badge-value">retrying</span></span>}
        <span className="result-spacer" />
        {isDone && (
          <button className="btn-ask" onClick={onDone} style={{ padding: "8px 16px" }}>
            Open queries <Icon.ArrowRight />
          </button>
        )}
        {(isError || !isDone) && (
          <button className="btn-ghost" onClick={onCancel}>
            {isError ? "Dismiss" : "Hide and continue in background"}
          </button>
        )}
      </div>
    </section>
  )
}

/* ============================================================================
   Footer
   ============================================================================ */

function Footer() {
  return (
    <footer className="footer">
      <div className="footer-line" />
      <div className="footer-text">
        CodeWeave <span className="dot">·</span> any GitHub repo, queryable <span className="dot">·</span> press <span className="kbd">⌘</span> <span className="kbd">K</span> to search
      </div>
    </footer>
  )
}
