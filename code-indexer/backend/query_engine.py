import pickle
import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path
import networkx as nx
import os
from dotenv import load_dotenv
from groq import Groq

BASE_DIR = Path(__file__).resolve().parents[1]

# Load persisted artifacts from a stable absolute path (not CWD-dependent).
GRAPH_PATH = BASE_DIR / "graph.pkl"
CHROMA_PATH = str(BASE_DIR / "chroma")
BLAST_RADIUS_KEYWORDS = [
    "breaks", "break", "change", "affect", "affects",
    "depends", "impact", "impacts", "what happens if"
]


def ask_llm(question: str, context: str, mode: str) -> str:
    load_dotenv()
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    mode_hint = (
        "The user wants to know the blast radius — what breaks if something changes."
        if mode == "blast_radius"
        else "The user wants to find code related to a concept."
    )
    
    prompt = f"""You are a code intelligence assistant for a Python codebase.

    {mode_hint}

    Here is the relevant code context retrieved from the codebase graph:

    {context}

    User question: {question}

    Answer clearly and specifically based on the context above. Reference function names, modules, and files where relevant.
    If the context provided is not relevant to the question, say "I don't have enough information in the codebase to answer that" instead of making something up."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
    )
    
    return response.choices[0].message.content

def load_resources():
    with open(GRAPH_PATH, "rb") as f:
        G = pickle.load(f)
    
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection("codebase")
    
    model = SentenceTransformer("all-MiniLM-L6-v2")
    
    return G, collection, model

def guardrail(results, mode):
    distances = results["distances"][0]
    if min(distances) > 0.8:  # tune this threshold
        return {
            "answer": "I couldn't find anything relevant in the codebase for that question.",
            "mode": mode,
            "node_count": 0,
        }


def detect_mode(question: str) -> str:
    q = question.lower()
    for keyword in BLAST_RADIUS_KEYWORDS:
        if keyword in q:
            return "blast_radius"
    return "semantic"

def semantic_search(question, collection, G, model, top_k=10):
    embedding = model.encode([question]).tolist()[0]
    
    results = collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
    )

    guardrail(results, 'semantic_search')
    
    node_ids = results["ids"][0]
    context_nodes = {}
    
    for node_id in node_ids:
        if node_id in G.nodes:
            context_nodes[node_id] = G.nodes[node_id]
            # 1-hop expansion — pull in neighbors
            for neighbor in list(G.successors(node_id)) + list(G.predecessors(node_id)):
                if neighbor in G.nodes:
                    context_nodes[neighbor] = G.nodes[neighbor]
    
    return context_nodes

def blast_radius(question, collection, G, model, top_k=5):
    # find the most relevant node first
    embedding = model.encode([question]).tolist()[0]
    results = collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
    )

    guardrail(results, 'blast_radius')
    
    node_ids = results["ids"][0]
    context_nodes = {}
    
    for start_node in node_ids:
        if start_node not in G.nodes:
            continue
        
        # reverse BFS — find everything that reaches this node
        ancestors = nx.ancestors(G, start_node)
        
        # include the start node itself
        context_nodes[start_node] = G.nodes[start_node]
        
        # include all ancestors (callers, importers)
        for ancestor in ancestors:
            if ancestor in G.nodes:
                context_nodes[ancestor] = G.nodes[ancestor]
    
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
        
        lines.append("\n".join(parts))
    
    return "\n\n".join(lines)

def query(question: str, G, collection, model) -> dict:
    mode = detect_mode(question)
    
    if mode == "blast_radius":
        context_nodes = blast_radius(question, collection, G, model)
    else:
        context_nodes = semantic_search(question, collection, G, model)
    
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