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
pip install tree-sitter tree-sitter-python networkx
```

---

## Run

```bash
python3 code-indexer/main.py
```

Outputs written to `code-indexer/`:
- `indexed_functions.json` — all parsed records
- `import_records.json` — file-level import data
- `graph.pkl` — the full context graph

---

## Project structure

- `code-indexer/indexer.py` — AST parsing and JSON record extraction
- `code-indexer/graph_builder.py` — graph node/edge construction and pickle save/load
- `code-indexer/main.py` — pipeline runner that ties indexing and graph building together

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

---

## Project roadmap

| Phase | Description | Status |
|---|---|---|
| 1 | Parse codebase → structured JSON | ✅ Done |
| 2 | Build context graph (NetworkX) | ✅ Done |
| 3 | Enrich nodes with docs, GitHub issues, tests | 🔜 Next |
| 4 | Embed nodes + store in vector DB | ⬜ Planned |
| 5 | Chat interface — "what breaks if I change X?" | ⬜ Planned |

---

## Stack

- [`tree-sitter`](https://github.com/tree-sitter/tree-sitter) — AST parsing
- [`tree-sitter-python`](https://github.com/tree-sitter/tree-sitter-python) — Python grammar
- [`networkx`](https://networkx.org/) — directed graph construction and traversal
- `pickle` — graph persistence
