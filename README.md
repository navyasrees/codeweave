---
title: Codeweave Backend
emoji: 🕸️
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# CodeWeave

A tool that parses a Python codebase into a structured context graph — extracting functions, classes, decorators, docstrings, call relationships, and imports, then connecting them into a traversable directed graph.

Built as the foundation for AI-powered code intelligence: ask "what breaks if I change this?" or "show me everything related to authentication."

---

## What this does

**Phase 1 — Parse**

Walks every `.py` file in a target repo and extracts:

- Functions and classes with name, type, file, and module
- Parameters and docstrings — including type-annotated parameters (`def f(x: int)`)
- Decorators (e.g. `@router.get("/users")`)
- All function calls made inside each function, with assignment-based resolution: if a function body does `adapter = HTTPAdapter()` then calls `adapter.send(...)`, the call is recorded as `HTTPAdapter.send` rather than the ambiguous bare name `send`
- Parent class for methods
- Line ranges and source snippets (capped at 30 lines)
- File-level imports

Output: `indexed_functions.json` and `import_records.json`

**Phase 2 — Build graph**

Takes the parsed JSON and builds a directed graph where:

- **Nodes** are functions and classes, each carrying all parsed metadata as attributes
- **Edges** carry type: `calls` (function → function) or `imports` (module → module)
- Call resolution uses a two-level lookup: qualified names (`ClassName.method`) are matched first using an exact index, plain names fall back to a base-name index with same-module preference — this ensures blast-radius traversal follows the correct method on the correct class rather than an unrelated function with the same name
- Import edges are drawn from raw `from X import Y` statements

Output: `graph.pkl` — a persistent NetworkX DiGraph, reloadable instantly without re-parsing

**Phase 3 — Enrich with docs**

Walks FastAPI markdown docs in `fastapi/docs/en/docs` and:

- Splits each `.md` by `#` headings into sections
- Matches headings to graph node names
- Attaches matched sections to node attribute `doc_sections`
- Saves the enriched graph back to `graph.pkl`

**Phase 4 — Enrich with GitHub issues**

Fetches issues from a target GitHub repo and:

- Matches issue titles to graph node names
- Attaches matched issues to node attribute `github_issues`
- Saves the enriched graph back to `graph.pkl`

**Phase 5 — Query engine**

Serves natural-language code queries using embeddings + graph traversal:

- Detects query intent (`semantic` vs `blast_radius`) from question keywords
- Rewrites the question into Python identifiers before embedding — "disable SSL globally" becomes `verify, session.verify, REQUESTS_CA_BUNDLE, cert_verify` — closing the vocabulary gap between natural language and source code
- Runs three query variants (natural language, identifiers only, combined) against the vector index and merges rankings with Reciprocal Rank Fusion — nodes that surface across multiple variants rank higher than nodes found by only one, making retrieval robust to vocabulary mismatch
- Applies a dynamic distance threshold (best match + 0.15) rather than a fixed cutoff, so the filter adapts to the actual embedding space
- Expands context with 1-hop graph neighbors/ancestors
- Builds compact node context including docs/issues metadata
- Sends context + question to an LLM and returns an answer
- Falls back across multiple configured Groq API keys when one hits its daily rate limit

**Phase 6 — Frontend chat UI**

Provides a React interface to query the backend:

- Simple chat-style input for natural language questions
- Sends requests to backend `/query` endpoint
- Renders answers and supporting context returned by the API

---

## Target repo

Built and tested against [FastAPI](https://github.com/fastapi/fastapi).

Clone it as a sibling directory before running:

```
your-workspace/
├── fastapi/          ← clone here
└── code-indexer/     ← this repo
```

```bash
git clone https://github.com/fastapi/fastapi.git
```

---

## Running Locally

### Prerequisites

- Python 3.9+
- Node.js 18+
- Git

---

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd code-weave
```

---

### 2. Set up the Python environment

```bash
cd code-indexer
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r ../requirements.txt
```

---

### 3. Create your `.env` file

Create a `.env` file inside `code-indexer/`:

```bash
# code-indexer/.env

GROQ_API_KEY=your_groq_api_key_here
GROQ_API_KEY_2=your_second_groq_key_here   # optional — used as fallback when primary key hits daily limit
VOYAGE_API_KEY=your_voyage_api_key_here
GITHUB_TOKEN=your_github_token_here        # optional — only needed for GitHub issues enrichment
```

- **GROQ_API_KEY** — get one free at [console.groq.com](https://console.groq.com)
- **GROQ_API_KEY_2** (and `_3`, `_4`, `_5`) — optional fallback keys from separate Groq accounts. When the primary key hits its daily token limit the system automatically retries with the next available key so queries keep working
- **VOYAGE_API_KEY** — get one at [dash.voyageai.com](https://dash.voyageai.com) (200M free tokens)
- **GITHUB_TOKEN** — a personal access token from [github.com/settings/tokens](https://github.com/settings/tokens) (read-only scope is enough)

---

### 4. Start the backend

From the **repo root** (`code-weave/`):

```bash
uvicorn backend.main:app --reload --app-dir code-indexer
```

The API will be running at **http://localhost:8000**.

To verify it's up:

```bash
curl http://localhost:8000/repos
```

> **First query on a repo?** The backend will run the full indexing pipeline on cold start (parse → graph → embed). This takes 5–10 minutes for FastAPI. Subsequent queries load from the cached `graph.pkl` and `chroma/` instantly.

---

### 5. Set up and start the frontend

In a **new terminal**:

```bash
cd code-indexer/frontend
npm install
npm run dev
```

The UI will be running at **http://localhost:5173**.

By default the frontend points to `http://localhost:8000`. If your backend is on a different port, create a `.env.local` file inside `code-indexer/frontend/`:

```bash
VITE_API_URL=http://localhost:8000
```

---

### Quick reference

| Service  | Command (from repo root)                                      | URL                    |
|----------|---------------------------------------------------------------|------------------------|
| Backend  | `uvicorn backend.main:app --reload --app-dir code-indexer`    | http://localhost:8000  |
| Frontend | `cd code-indexer/frontend && npm run dev`                     | http://localhost:5173  |

---

## Project structure

- `code-indexer/indexer.py` — AST parsing, typed parameter extraction, assignment-based call resolution
- `code-indexer/graph_builder.py` — graph node/edge construction with qualified name index for precise call resolution
- `code-indexer/enricher.py` — markdown doc ingestion and node enrichment
- `code-indexer/embedder.py` — LLM summary generation for nodes with weak docstrings, embedding generation, ChromaDB storage
- `code-indexer/main.py` — pipeline runner that ties indexing, graph building, and enrichment together
- `code-indexer/backend/query_engine.py` — query expansion, multi-query RRF retrieval, blast-radius traversal, LLM answering, multi-key rate limit fallback
- `code-indexer/backend/main.py` — FastAPI app exposing `/query` endpoint
- `code-indexer/frontend/` — Vite + React chat interface

---

## Output format

Each record in `indexed_functions.json`:

```json
{
  "type": "function",
  "name": "get_current_user",
  "file": "fastapi/security/oauth2.py",
  "module": "fastapi.security.oauth2",
  "parent_class": "OAuth2PasswordBearer",
  "decorators": ["@router.get(\"/users\")"],
  "params": ["token", "db"],
  "docstring": "Validate and return the current user.",
  "calls": ["decode_token", "HTTPException"],
  "line_range": [45, 60]
}
```

Classes additionally include `methods` (list of method names).

Enriched nodes may also include:
- `doc_sections` — matched docs sections with `source`, `heading`, `content`
- `github_issues` — matched issues with `number`, `title`, `url`, `state`

---

## Querying the graph

```python
import pickle

with open("code-indexer/graph.pkl", "rb") as f:
    G = pickle.load(f)

# what does this node call?
print(list(G.successors(node_id)))

# what calls this node? (blast radius)
print(list(G.predecessors(node_id)))
```

For natural-language querying via the query engine:

```bash
python3 code-indexer/backend/query_engine.py
```

The query engine:
- loads `graph.pkl`, Chroma collection, and `all-MiniLM-L6-v2`
- detects mode from keywords (impact-style questions trigger `blast_radius`)
- returns mode, node count, assembled context, and final LLM answer

For HTTP querying from the frontend (or curl):

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"show me all authentication related code"}'
```

---

## Project roadmap

| Phase | Description | Status |
|---|---|---|
| 1 | Parse codebase → structured JSON | ✅ Done |
| 2 | Build context graph (NetworkX) | ✅ Done |
| 3 | Enrich nodes with docs | ✅ Done |
| 4 | Enrich nodes with GitHub issues | ✅ Done |
| 5 | Embed nodes + store in vector DB | ✅ Done |
| 6 | Add query engine (semantic + blast radius) | ✅ Done |
| 7 | Add frontend chat interface | ✅ Done |
| 8 | Typed parameter extraction + assignment-based call resolution | ✅ Done |
| 9 | LLM-generated semantic summaries for nodes with weak docstrings | ✅ Done |
| 10 | Multi-query RRF retrieval + query expansion | ✅ Done |
| 11 | Multi-key Groq rate limit fallback | ✅ Done |
| 12 | Add test links to nodes | 🔜 Next |
| 13 | Improve chat workflows and evaluation | ⬜ Planned |

---

## Stack

- [`tree-sitter`](https://github.com/tree-sitter/tree-sitter) — AST parsing
- [`tree-sitter-python`](https://github.com/tree-sitter/tree-sitter-python) — Python grammar
- [`networkx`](https://networkx.org/) — directed graph construction and traversal
- [`chromadb`](https://github.com/chroma-core/chroma) — persistent vector store
- [`sentence-transformers`](https://www.sbert.net/) — embedding generation
- [`python-dotenv`](https://github.com/theskumar/python-dotenv) — environment variable loading
- [`PyGithub`](https://github.com/PyGithub/PyGithub) — GitHub API access for issue enrichment
- [`groq`](https://github.com/groq/groq-python) — LLM inference API client
- [`FastAPI`](https://fastapi.tiangolo.com/) — backend API layer
- [`uvicorn`](https://www.uvicorn.org/) — ASGI server for local backend
- [`React`](https://react.dev/) — frontend UI
- [`Vite`](https://vitejs.dev/) — frontend build/dev tooling
- `pickle` — graph persistence
