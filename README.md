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
- Parameters and docstrings
- Decorators (e.g. `@router.get("/users")`)
- All function calls made inside each function
- Parent class for methods
- Line ranges
- File-level imports

Output: `indexed_functions.json` and `import_records.json`

**Phase 2 — Build graph**

Takes the parsed JSON and builds a directed graph where:

- **Nodes** are functions and classes, each carrying all parsed metadata as attributes
- **Edges** carry type: `calls` (function → function) or `imports` (module → module)
- Call names are resolved to real nodes using a name index with same-module preference
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

- Detects query intent (`semantic` vs `blast_radius`)
- Runs vector retrieval from Chroma using sentence embeddings
- Expands context with graph neighbors/ancestors
- Builds compact node context including docs/issues metadata
- Sends context + question to an LLM and returns an answer

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

## Setup

```bash
cd code-indexer
python3 -m venv venv
source venv/bin/activate
pip install tree-sitter tree-sitter-python networkx python-dotenv PyGithub
```

Create a `.env` file in the repo root:

```bash
GITHUB_TOKEN=your_github_token_here
GROQ_API_KEY=your_groq_api_key_here
```

---

## Run

```bash
python3 code-indexer/main.py
```

Outputs written to `code-indexer/`:
- `indexed_functions.json` — all parsed records
- `import_records.json` — file-level import data
- `graph.pkl` — the full context graph (including `doc_sections` and `github_issues` after enrichment)
- `chroma/` — persistent vector index used by the query engine

Run backend API:

```bash
uvicorn backend.main:app --reload --app-dir code-indexer
```

Run frontend:

```bash
cd code-indexer/frontend
npm install
npm run dev
```

---

## Project structure

- `code-indexer/indexer.py` — AST parsing and JSON record extraction
- `code-indexer/graph_builder.py` — graph node/edge construction and pickle save/load
- `code-indexer/enricher.py` — markdown doc ingestion and node enrichment
- `code-indexer/embedder.py` — generates embeddings and stores them in Chroma
- `code-indexer/main.py` — pipeline runner that ties indexing, graph building, and enrichment together
- `code-indexer/backend/query_engine.py` — semantic search + blast-radius traversal + LLM answering
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
| 8 | Add test links to nodes | 🔜 Next |
| 9 | Improve chat workflows and evaluation | ⬜ Planned |

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
