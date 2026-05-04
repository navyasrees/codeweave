# Code Indexer

A tool that parses a Python codebase into structured JSON — extracting functions, classes, decorators, docstrings, call relationships, and imports. Built as Phase 1 of a larger project to index codebases into a context graph for AI-powered code intelligence.

---

## What this does

Walks every `.py` file in a target repo and extracts:

- Functions and classes with name, type, file, and module
- Parameters and docstrings
- Decorators (e.g. `@router.get("/users")`)
- All function calls made inside each function
- Parent class for methods
- Line ranges
- File-level imports

Output is a single `indexed_functions.json` file — one record per function or class.

---

## Target repo

This tool is built and tested against [FastAPI](https://github.com/fastapi/fastapi).

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
pip install tree-sitter tree-sitter-python
```

---

## Run

```bash
python3 main.py
```

Output is written to `indexed_functions.json` in the project root.

---

## Output format

Each record in the JSON looks like this:

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

Classes include a `bases` field (superclasses) and `methods` (list of method names).

---

## Project roadmap

| Phase | Description | Status |
|---|---|---|
| 1 | Parse codebase → structured JSON | ✅ Done |
| 2 | Build context graph (NetworkX) | 🔜 Next |
| 3 | Enrich nodes with docs, GitHub issues, tests | ⬜ Planned |
| 4 | Embed nodes + store in vector DB | ⬜ Planned |
| 5 | Chat interface — "what breaks if I change X?" | ⬜ Planned |

---

## Stack

- [`tree-sitter`](https://github.com/tree-sitter/tree-sitter) — AST parsing
- [`tree-sitter-python`](https://github.com/tree-sitter/tree-sitter-python) — Python grammar
