import pickle
import chromadb
from pathlib import Path
import networkx as nx
import os
from dotenv import load_dotenv
from groq import Groq
import voyageai


BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"


def is_test_node(data: dict) -> bool:
    """Return True if this node lives in a test file.

    Handles both absolute-style paths (/project/tests/foo.py) and repo-relative
    paths (t/unit/foo.py, tests/foo.py) which have no leading slash.
    Used to exclude test nodes from semantic context and 1-hop expansion,
    while leaving them in the graph so blast radius can still find them.
    """
    file_path = str(data.get("file", "")).replace("\\", "/")
    parts = file_path.split("/")
    # Universal test directory names used across the Python ecosystem.
    # Do NOT add subdirectory names like "integration", "unit", "smoke" — those are
    # only meaningful as children of a test root (e.g. t/integration/) and will
    # false-positive on repos that have production modules like src/integration/
    # or lib/unit/. The parent "t" or "tests" already catches those subtrees.
    test_dirs = {"tests", "t", "test"}
    for component in parts[:-1]:   # exclude the filename itself
        if component in test_dirs:
            return True
    filename = parts[-1] if parts else ""
    if filename.startswith("test_") or filename.endswith("_test.py"):
        return True
    return False

# Legacy single-repo paths (kept for backwards compatibility — actual per-repo
# resolution happens inside load_resources via ARTIFACTS_DIR / repo_name).
GRAPH_PATH = BASE_DIR / "graph.pkl"
CHROMA_PATH = str(BASE_DIR / "chroma")
BLAST_RADIUS_KEYWORDS = [
    "breaks", "break", "change", "affect", "affects",
    "depends", "impact", "impacts", "what happens if"
]


def _load_groq_clients() -> list:
    """Return a Groq client for every API key configured in the environment.

    Reads GROQ_API_KEY (primary) plus GROQ_API_KEY_2 … GROQ_API_KEY_5 (fallbacks).
    When one key hits its daily rate limit the caller can pop it and retry with
    the next one — queries keep working as long as at least one key has quota.

    To add a second key, add to .env:
        GROQ_API_KEY_2=gsk_...
    """
    load_dotenv()
    keys = []
    primary = os.getenv("GROQ_API_KEY")
    if primary:
        keys.append(primary)
    for i in range(2, 6):
        key = os.getenv(f"GROQ_API_KEY_{i}")
        if key:
            keys.append(key)
    return [Groq(api_key=k) for k in keys]


def ask_llm(question: str, context: str, mode: str) -> str:
    clients = _load_groq_clients()

    if mode == "blast_radius":
        mode_instruction = """The user wants to understand the blast radius of a change.
            Your job:
            - List every function and class that would be directly or indirectly affected
            - For each, explain WHY it would break — not just that it calls the changed thing
            - Group by: direct callers, indirect callers, modules affected
            - Be specific about what argument, return value, or behavior change would cause the break
            - If something would NOT break, say so clearly"""
    else:
        mode_instruction = """The user wants to find code related to a concept.
            Your job:
            - List the most relevant functions and classes, ranked by relevance
            - For each entry include: function name, file path, one-line description of what it does
            - Then explain how they relate to each other
            - End with: which file to start reading if you want to understand this concept"""

    # Prompt is built after the if/else so it is always defined for both modes.
    # Previously it was inside the else block, causing a NameError on blast_radius queries.
    prompt = f"""You are a senior engineer doing a code review on a Python codebase.
        You have been given a structured extract of the codebase as context.
        Answer only from what is in the context — do not hallucinate modules or functions that are not listed.
        If the context does not contain enough information to answer, say exactly: "The codebase context doesn't have enough information to answer this confidently."

        {mode_instruction}

        FORMAT RULES:
        - Use clear sections with headers
        - For each function/class: show name, file, and a one-line description
        - Be specific — name actual functions, files, line numbers if available
        - Do not repeat the same point twice
        - Do not hedge with phrases like "might be", "could be", "it's hard to say"

        CODEBASE CONTEXT:
        {context}

        QUESTION: {question}

        ANSWER:"""

    import re
    last_reset_str = None
    for client in clients:
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=0.1,
            )
            return response.choices[0].message.content
        except Exception as e:
            err = str(e)
            if "rate_limit" in err.lower() or "429" in err:
                # This key is exhausted — extract reset time and try the next one
                match = re.search(r"try again in ([0-9hms\. ]+)", err)
                last_reset_str = match.group(1).strip().rstrip(".") if match else None
                continue
            raise

    # All keys exhausted
    if last_reset_str:
        return f"⚠️ Daily limit reached. Queries will resume in **{last_reset_str}**."
    return "⚠️ Daily limit reached. Queries will resume shortly."

def load_resources(repo_name: str = "fastapi"):
    load_dotenv()
    vo = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
    # Anchor to ARTIFACTS_DIR (absolute, file-location-relative) so this works
    # regardless of where uvicorn is launched from. MUST stay in sync with
    # backend/main.py and backend/pipeline_runner.py — all three resolve to
    # <code-indexer>/artifacts/.
    artifact_dir = ARTIFACTS_DIR / repo_name
    graph_path = artifact_dir / "graph.pkl"
    chroma_path = str(artifact_dir / "chroma")

    with open(graph_path, "rb") as f:
        G = pickle.load(f)

    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_collection(repo_name)

    return G, collection, vo

class NotRelevantError(Exception):
    pass

def guardrail(results, mode):
    distances = results["distances"][0]
    if min(distances) > 0.8:
        raise NotRelevantError("I couldn't find anything relevant in the codebase for that question.")

def detect_mode(question: str) -> str:
    q = question.lower()
    for keyword in BLAST_RADIUS_KEYWORDS:
        if keyword in q:
            return "blast_radius"
    return "semantic"

def expand_query(question: str, clients: list = None) -> str:
    """Rewrite the question into Python identifiers and technical terms.

    Returns ONLY the identifier list (no original question prepended).
    Callers that need the combined string can do: f"{question} {terms}".

    Tries each configured Groq key in turn so a rate-limited key doesn't
    silently fall back to returning an empty string.
    If all keys are exhausted, returns an empty string — the caller still
    works, it just skips query expansion for that request.
    """
    if clients is None:
        clients = _load_groq_clients()

    prompt = f"""You are helping search a Python codebase.
Rewrite this question as a short list of Python identifiers, method names, variable names, and technical terms that are likely to appear in the source code that answers it.
Output ONLY a comma-separated list of terms. No explanation, no sentences.

Question: {question}
Terms:"""

    for client in clients:
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0.0,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            if "rate_limit" in err.lower() or "429" in err:
                continue  # try next key
            raise

    return ""  # all keys exhausted — caller proceeds without expansion


def _rrf_merge(ranked_lists: list[list[str]], k: int = 60) -> list[str]:
    """Merge multiple ranked node-ID lists using Reciprocal Rank Fusion.

    RRF score for a node = Σ 1 / (k + rank_i) across all lists where it appears.
    k=60 is the standard value from the original RRF paper — it dampens the
    advantage of very-high-rank documents without eliminating it entirely.

    Nodes that appear in multiple lists (i.e. matched by more than one query
    variant) get a boosted score, naturally surfacing robust matches.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, node_id in enumerate(ranked, start=1):
            scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda n: scores[n], reverse=True)


def semantic_search(question, collection, G, vo, top_k=30):
    """Retrieve relevant nodes using multi-query RRF.

    Runs three query variants against the embedding index:
      1. Natural-language question  — captures conceptual similarity
      2. Pure Python identifiers    — captures code-level token matches
      3. Combined (question + terms) — the original single-query approach

    Rankings from all three are merged with Reciprocal Rank Fusion so nodes
    that surface across multiple variants rank higher than nodes found by only
    one. This is especially effective when the question vocabulary doesn't
    overlap with source code identifiers (the "SSL globally" → verify=False gap).
    """
    clients = _load_groq_clients()
    terms = expand_query(question, clients)

    variants = [
        question,                   # 1. natural language
        terms,                      # 2. pure identifiers
        f"{question} {terms}",      # 3. combined (original approach)
    ]

    result = vo.embed(variants, model="voyage-code-2", input_type="query")
    embeddings = result.embeddings

    # Run each variant through ChromaDB separately.
    # Guardrail on the combined variant (index 2) — closest to original behaviour.
    ranked_lists = []
    guardrail_results = None
    for i, emb in enumerate(embeddings):
        res = collection.query(
            query_embeddings=[emb],
            n_results=top_k,
            include=["distances"]
        )
        ranked_lists.append(res["ids"][0])
        if i == 2:
            guardrail_results = res

    guardrail(guardrail_results, "semantic_search")

    # Merge rankings with RRF
    merged = _rrf_merge(ranked_lists)

    seen_names = set()
    context_nodes = {}

    for node_id in merged[:top_k]:
        if node_id not in G.nodes:
            continue
        data = G.nodes[node_id]
        if not data.get("type"):
            continue
        name = data.get("name", node_id)
        if name in seen_names:
            continue
        seen_names.add(name)
        context_nodes[node_id] = data

        # 1-hop graph expansion — same as before
        for neighbor in list(G.successors(node_id)) + list(G.predecessors(node_id)):
            if neighbor not in G.nodes:
                continue
            neighbor_data = G.nodes[neighbor]
            if not neighbor_data.get("type"):
                continue
            if is_test_node(neighbor_data):
                continue
            context_nodes[neighbor] = neighbor_data

    return context_nodes

def _blast_params(G, node_ids: list) -> tuple[int, int]:
    """Return (top_k, hop_depth) scaled to the connectivity of the seed nodes.

    High in-degree nodes (hub functions like Task.run, apply_async) are called
    from many places — they need wider retrieval to surface the full blast radius.
    Low in-degree leaf functions need tight retrieval to avoid noise.

    in-degree thresholds:
      >= 10  →  top_k=8, hops=3  (base classes, core primitives)
      >= 3   →  top_k=5, hops=2  (moderately connected)
      < 3    →  top_k=3, hops=2  (leaf / rarely-called functions)
    """
    max_degree = max(
        (G.in_degree(n) for n in node_ids if n in G.nodes),
        default=0,
    )
    if max_degree >= 10:
        return 8, 3
    elif max_degree >= 3:
        return 5, 2
    else:
        return 3, 2


def blast_radius(question, collection, G, vo, top_k=3):
    result = vo.embed([question], model="voyage-code-2", input_type="query")
    embedding = result.embeddings[0]

    # Initial retrieval uses the default top_k to find seed nodes.
    # We then re-scale based on how connected those seeds actually are.
    results = collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
    )

    node_ids = results["ids"][0]

    # Scale retrieval depth to the connectivity of the seed nodes.
    _, hop_depth = _blast_params(G, node_ids)

    context_nodes = {}

    for start_node in node_ids:
        if start_node not in G.nodes:
            continue

        start_data = G.nodes[start_node]
        # Skip ghost module-string nodes that have no meaningful attributes.
        if not start_data.get("type") or not start_data.get("name"):
            continue

        context_nodes[start_node] = start_data

        visited = {start_node}
        current_layer = {start_node}

        for _ in range(hop_depth):
            next_layer = set()
            for node in current_layer:
                for pred in G.predecessors(node):
                    if pred in visited or pred not in G.nodes:
                        continue

                    # Only follow calls edges — not imports edges.
                    # Imports edges connect bare module-string nodes and cause
                    # the BFS to explode across unrelated modules.
                    edge_data = G.get_edge_data(pred, node) or {}
                    if edge_data.get("type") != "calls":
                        continue

                    pred_data = G.nodes[pred]
                    # Skip ghost nodes and test nodes.
                    if not pred_data.get("type") or not pred_data.get("name"):
                        continue
                    if is_test_node(pred_data):
                        continue

                    next_layer.add(pred)
                    context_nodes[pred] = pred_data
                    visited.add(pred)

            current_layer = next_layer

    return context_nodes


def build_context(context_nodes: dict) -> str:
    lines = []
    
    for node_id, data in list(context_nodes.items())[:30]:  # cap at 30 nodes
        parts = [f"[{data.get('type', 'unknown')}] {data.get('name', node_id)}"]
        
        if data.get("module"):
            parts.append(f"  module: {data['module']}")
        if data.get("file"):
            parts.append(f"  file: {data['file']}")
        if data.get("docstring"):
            parts.append(f"  docstring: {data['docstring'][:200]}")
        if data.get("calls"):
            parts.append(f"  calls: {', '.join(data['calls'][:10])}")
        if data.get("doc_sections"):
            parts.append(f"  docs: {data['doc_sections'][0]['heading']}")
        if data.get("github_issues"):
            issues = [i["title"] for i in data["github_issues"][:2]]
            parts.append(f"  issues: {', '.join(issues)}")
        if data.get("snippet"):
            parts.append(f"  code:\n{data['snippet'][:500]}")
        
        lines.append("\n".join(parts))
    
    return "\n\n".join(lines)

def query(question: str, G, collection, vo) -> dict:
    mode = detect_mode(question)

    try:
        if mode == "blast_radius":
            context_nodes = blast_radius(question, collection, G, vo)
        else:
            context_nodes = semantic_search(question, collection, G, vo)
    except NotRelevantError as e:
        return {
            "mode": mode,
            "context": "",
            "node_count": 0,
            "answer": str(e),
        }

    context = build_context(context_nodes)
    answer = ask_llm(question, context, mode)

    return {
        "mode": mode,
        "context": context,
        "node_count": len(context_nodes),
        "answer": answer,
    }

if __name__ == "__main__":
    G, collection, model = load_resources()
    
    result = query("show me all authentication related code", G, collection, model)
    print(f"Mode: {result['mode']}")
    print(f"Nodes found: {result['node_count']}")
    print(f"\nAnswer:\n{result['answer']}")