import { useState } from "react"

export default function App() {
  const [question, setQuestion] = useState("")
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleQuery = async () => {
    if (!question.trim()) return
    setLoading(true)
    setResult(null)

    const res = await fetch("http://localhost:8000/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    })
    const data = await res.json()
    setResult(data)
    setLoading(false)
  }

  return (
    <div style={{ maxWidth: 800, margin: "60px auto", fontFamily: "sans-serif", padding: "0 20px" }}>
      <h1>CodeWeave</h1>
      <p style={{ color: "#666" }}>Ask anything about the FastAPI codebase</p>

      <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        <input
          style={{ flex: 1, padding: "10px 14px", fontSize: 16, borderRadius: 6, border: "1px solid #ccc" }}
          placeholder='e.g. "what breaks if I change OAuth2PasswordBearer?"'
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleQuery()}
        />
        <button
          style={{ padding: "10px 20px", fontSize: 16, borderRadius: 6, background: "#111", color: "#fff", border: "none", cursor: "pointer" }}
          onClick={handleQuery}
          disabled={loading}
        >
          {loading ? "Thinking..." : "Ask"}
        </button>
      </div>

      {result && (
        <div>
          <div style={{ marginBottom: 12, color: "#888", fontSize: 13 }}>
            Mode: <strong>{result.mode}</strong> · Nodes found: <strong>{result.node_count}</strong>
          </div>
          <div style={{ background: "#f9f9f9", borderRadius: 8, padding: 20, whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
            {result.answer}
          </div>
        </div>
      )}
    </div>
  )
}