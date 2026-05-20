"""
One-shot fix for merge_environment_settings.

The node got a wrong LLM summary ("Deserializes the Session object...") due to
a batch index misalignment during indexing. This script:
  1. Regenerates the correct summary using the actual code snippet
  2. Writes it back to artifacts/requests/graph.pkl
  3. Re-embeds just this one node in ChromaDB (upsert, no full re-index needed)

Run from the code-indexer/ directory:
    python3 fix_merge_env_summary.py
"""
import os, pickle, sys
import chromadb, voyageai
from dotenv import load_dotenv
from groq import Groq
from pathlib import Path

load_dotenv()

GROQ_KEY   = os.getenv("GROQ_API_KEY")
VOYAGE_KEY = os.getenv("VOYAGE_API_KEY")
if not GROQ_KEY or not VOYAGE_KEY:
    sys.exit("Missing GROQ_API_KEY or VOYAGE_API_KEY in .env")

ARTIFACT_DIR = Path("artifacts/requests")
GRAPH_PATH   = ARTIFACT_DIR / "graph.pkl"
CHROMA_PATH  = str(ARTIFACT_DIR / "chroma")

# ── 1. Load graph and find the node ─────────────────────────────────────────
with open(GRAPH_PATH, "rb") as f:
    G = pickle.load(f)

target_node = next(
    (n for n, d in G.nodes(data=True) if d.get("name") == "merge_environment_settings"),
    None
)
if not target_node:
    sys.exit("merge_environment_settings not found in graph")

data = G.nodes[target_node]
print("Node ID       :", target_node)
print("Bad summary   :", data.get("llm_summary"))
print("Docstring     :", (data.get("docstring") or "").strip()[:80])

# ── 2. Regenerate the summary with the right context ─────────────────────────
groq = Groq(api_key=GROQ_KEY)
response = groq.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[{"role": "user", "content": f"""Write ONE sentence describing this Python function:
1. What it does
2. What user-facing intents it serves — be explicit: mention "disable SSL globally",
   "skip certificate verification", "set verify=False session-wide", "REQUESTS_CA_BUNDLE"
3. When a developer would look for or change it

Output ONLY the sentence, nothing else.

name: merge_environment_settings
docstring: {(data.get("docstring") or "").strip()}
code:
{data.get("snippet", "")[:500]}
"""}],
    max_tokens=120,
    temperature=0.0,
)
new_summary = response.choices[0].message.content.strip()
print("\nNew summary   :", new_summary)

# ── 3. Write back to graph ────────────────────────────────────────────────────
G.nodes[target_node]["llm_summary"] = new_summary
with open(GRAPH_PATH, "wb") as f:
    pickle.dump(G, f)
print("Graph saved.")

# ── 4. Rebuild embedding text (mirrors embedder.node_to_text) ─────────────────
parts = [
    f"name: {data.get('name', '')}",
    f"type: {data.get('type', '')}",
    f"module: {data.get('module', '')}",
    f"file: {data.get('file', '')}",
]
if data.get("parent_class"):
    parts.append(f"class: {data['parent_class']}")
parts.append(f"summary: {new_summary}")
if data.get("params"):
    parts.append(f"params: {', '.join(data['params'])}")
if data.get("calls"):
    parts.append(f"calls: {', '.join(data['calls'][:10])}")
if data.get("snippet"):
    parts.append(f"code: {data['snippet'][:600]}")
text = " | ".join(parts)
print("\nEmbedding text (first 300 chars):", text[:300])

# ── 5. Upsert into ChromaDB ───────────────────────────────────────────────────
vo         = voyageai.Client(api_key=VOYAGE_KEY)
result     = vo.embed([text], model="voyage-code-2", input_type="document")
embedding  = result.embeddings[0]

chroma     = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma.get_collection("requests")
collection.upsert(
    ids        = [target_node],
    embeddings = [embedding],
    documents  = [text],
    metadatas  = [{
        "name":   str(data.get("name", "")),
        "type":   str(data.get("type", "")),
        "file":   str(data.get("file", "")),
        "module": str(data.get("module", "")),
    }]
)
print("\nChromaDB upserted successfully.")
print("Done — restart the backend and re-run the SSL queries.")
