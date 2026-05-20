import chromadb
import pickle
import voyageai
import os
import json
import time
from dotenv import load_dotenv
from groq import Groq

def is_test_node(data):
    """Return True if this node lives in a test file and should be excluded from embeddings.

    Handles both absolute-style paths (/project/tests/foo.py) and repo-relative
    paths (t/unit/foo.py, tests/foo.py) which have no leading slash.
    """
    file_path = str(data.get("file", "")).replace("\\", "/")
    # Normalise: split into directory components + filename
    parts = file_path.split("/")
    # Any directory component that is a canonical test directory
    # Universal test directory names used across the Python ecosystem.
    # Do NOT add subdirectory names like "integration", "unit", "smoke" — those are
    # only meaningful as children of a test root (e.g. t/integration/) and will
    # false-positive on repos that have production modules like src/integration/
    # or lib/unit/. The parent "t" or "tests" already catches those subtrees.
    test_dirs = {"tests", "t", "test"}
    for component in parts[:-1]:   # exclude the filename itself
        if component in test_dirs:
            return True
    # Filename-level patterns
    filename = parts[-1] if parts else ""
    if filename.startswith("test_") or filename.endswith("_test.py"):
        return True
    return False


def _needs_summary(data: dict) -> bool:
    """Return True if this node still needs an LLM-generated semantic summary.

    Skip nodes that already have a summary (cached from a previous index run).
    For new nodes: generate if docstring is missing or under 80 chars.
    This keeps token usage low on re-indexes — only new/changed nodes get summarised.
    """
    if data.get("llm_summary"):
        return False  # already done, don't burn tokens again
    docstring = (data.get("docstring") or "").strip()
    return len(docstring) < 80


def generate_summaries(nodes: list[tuple], groq_client: Groq) -> dict:
    """Batch-generate semantic summaries for nodes with weak docstrings.

    Sends up to 20 nodes per LLM call to stay within token limits.
    Returns a dict of node_id -> summary string.
    """
    summaries = {}
    batch_size = 20

    for i in range(0, len(nodes), batch_size):
        batch = nodes[i:i + batch_size]

        descriptions = []
        for idx, (node_id, data) in enumerate(batch):
            snippet = (data.get("snippet") or "")[:400]
            docstring = (data.get("docstring") or "").strip()
            descriptions.append(
                f"[{idx}] name={data.get('name')} file={data.get('file')}\n"
                f"docstring: {docstring or '(none)'}\n"
                f"code:\n{snippet}"
            )

        prompt = (
            "For each Python function below, write ONE sentence describing:\n"
            "1. What it does\n"
            "2. What user-facing concepts it relates to — include terms a developer\n"
            "   would search for, e.g. 'disable SSL', 'skip cert verification',\n"
            "   'set timeout globally', 'retry on failure', etc. where applicable\n"
            "3. When a developer would use or change it\n\n"
            "Output ONLY a JSON object mapping each index to its summary string.\n"
            "Use the [N] index prefix as the key (as a string).\n"
            'Example: {"0": "Verifies SSL certificates by checking the CA bundle path.", '
            '"1": "Sends an HTTP request with optional retry logic.", ...}\n\n'
            + "\n\n".join(descriptions)
        )

        try:
            # Use the small fast model for summaries — 8b is plenty for
            # one-sentence descriptions and uses ~10x fewer tokens than 70b.
            response = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.0,
            )
            raw = response.choices[0].message.content.strip()
            # Extract the JSON object robustly — keyed by index so a missing
            # entry causes a lookup miss, not a silent index shift.
            start = raw.find("{")
            end = raw.rfind("}") + 1
            parsed = json.loads(raw[start:end]) if start != -1 else {}
            for j, (node_id, _) in enumerate(batch):
                summary = parsed.get(str(j))
                if summary:
                    summaries[node_id] = summary
            # Small delay to stay within RPM limits on the free tier
            time.sleep(1)
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                print(f"  Rate limit hit at batch {i//batch_size} — stopping summary generation. Remaining nodes will use docstrings only.")
                break
            print(f"  Summary generation failed for batch {i//batch_size}: {e}")

    return summaries


def node_to_text(node_id, data):
    parts = []

    parts.append(f"name: {data.get('name', '')}")
    parts.append(f"type: {data.get('type', '')}")
    parts.append(f"module: {data.get('module', '')}")
    parts.append(f"file: {data.get('file', '')}")

    if data.get("parent_class"):
        parts.append(f"class: {data.get('parent_class')}")

    # Prefer LLM-generated summary over raw docstring when available
    if data.get("llm_summary"):
        parts.append(f"summary: {data['llm_summary']}")
    elif data.get("docstring"):
        parts.append(f"docstring: {data.get('docstring')}")

    if data.get("params"):
        parts.append(f"params: {', '.join(data.get('params', []))}")

    if data.get("calls"):
        parts.append(f"calls: {', '.join(data.get('calls', []))}")

    if data.get("decorators"):
        parts.append(f"decorators: {', '.join(data.get('decorators', []))}")

    if data.get("doc_sections"):
        for section in data["doc_sections"][:2]:
            parts.append(f"doc: {section['heading']}. {section['content'][:300]}")

    if data.get("github_issues"):
        for issue in data["github_issues"][:3]:
            parts.append(f"issue: {issue['title']}")

    # Always include the code snippet — function signatures contain param names
    # and type annotations that are critical for semantic matching
    if data.get("snippet"):
        parts.append(f"code: {data['snippet'][:600]}")

    return " | ".join(parts)


def embed_and_store(graph_path, chroma_path="code-indexer/chroma", collection_name="codebase"):
    with open(graph_path, "rb") as f:
        G = pickle.load(f)

    load_dotenv()
    vo = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # --- Step 1: Generate LLM summaries for nodes with weak docstrings ---
    nodes_needing_summary = [
        (node_id, data)
        for node_id, data in G.nodes(data=True)
        if data.get("type") in ("function", "class")
        and data.get("name")
        and not is_test_node(data)
        and _needs_summary(data)
    ]

    print(f"Generating semantic summaries for {len(nodes_needing_summary)} nodes with weak docstrings...")
    summaries = generate_summaries(nodes_needing_summary, groq_client)

    # Write summaries back onto the graph nodes so they persist in graph.pkl
    for node_id, summary in summaries.items():
        G.nodes[node_id]["llm_summary"] = summary

    # Persist the enriched graph so summaries are available at query time too
    with open(graph_path, "wb") as f:
        pickle.dump(G, f)
    print(f"Summaries written to {len(summaries)} nodes and saved to graph.")

    # --- Step 2: Build ChromaDB collection ---
    client = chromadb.PersistentClient(path=chroma_path)

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(collection_name)

    ids = []
    texts = []
    metadatas = []

    for node_id, data in G.nodes(data=True):
        if data.get("type") == "test":
            continue
        if not data.get("type"):
            continue
        if not data.get("name"):
            continue
        if is_test_node(data):
            continue
        text = node_to_text(node_id, data)
        ids.append(node_id)
        texts.append(text)
        metadatas.append({
            "name": str(data.get("name", "")),
            "type": str(data.get("type", "")),
            "file": str(data.get("file", "")),
            "module": str(data.get("module", "")),
        })

    # Voyage has a limit of 128 texts per batch
    batch_size = 128
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i:i + batch_size]
        batch_texts = texts[i:i + batch_size]
        batch_meta = metadatas[i:i + batch_size]

        result = vo.embed(batch_texts, model="voyage-code-2", input_type="document")
        embeddings = result.embeddings

        collection.add(
            ids=batch_ids,
            embeddings=embeddings,
            documents=batch_texts,
            metadatas=batch_meta,
        )
        print(f"Embedded {min(i + batch_size, len(ids))}/{len(ids)} nodes")

    print(f"Done. {collection.count()} nodes stored in ChromaDB.")
    return collection