from sentence_transformers import SentenceTransformer
import chromadb
import pickle

def node_to_text(node_id, data):
    parts = []
    
    parts.append(f"name: {data.get('name', '')}")
    parts.append(f"type: {data.get('type', '')}")
    parts.append(f"module: {data.get('module', '')}")
    
    if data.get("parent_class"):
        parts.append(f"class: {data.get('parent_class')}")
    
    if data.get("docstring"):
        parts.append(f"docstring: {data.get('docstring')}")
    
    if data.get("calls"):
        parts.append(f"calls: {', '.join(data.get('calls', []))}")
    
    if data.get("decorators"):
        parts.append(f"decorators: {', '.join(data.get('decorators', []))}")
    
    if data.get("doc_sections"):
        for section in data["doc_sections"][:2]:  # limit to 2 sections
            parts.append(f"doc: {section['heading']}. {section['content'][:300]}")
    
    if data.get("github_issues"):
        for issue in data["github_issues"][:3]:  # limit to 3 issues
            parts.append(f"issue: {issue['title']}")
    
    return " | ".join(parts)


def embed_and_store(graph_path, chroma_path="code-indexer/chroma"):
    with open(graph_path, "rb") as f:
        G = pickle.load(f)
    
    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=chroma_path)
    
    # delete collection if exists to avoid duplicates on re-run
    try:
        client.delete_collection("codebase")
    except:
        pass
    
    collection = client.create_collection("codebase")
    
    ids = []
    texts = []
    metadatas = []
    
    for node_id, data in G.nodes(data=True):
        text = node_to_text(node_id, data)
        ids.append(node_id)
        texts.append(text)
        metadatas.append({
            "name": str(data.get("name", "")),
            "type": str(data.get("type", "")),
            "file": str(data.get("file", "")),
            "module": str(data.get("module", "")),
        })
    
    # embed and store in batches
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i:i+batch_size]
        batch_texts = texts[i:i+batch_size]
        batch_meta = metadatas[i:i+batch_size]
        embeddings = model.encode(batch_texts).tolist()
        collection.add(
            ids=batch_ids,
            embeddings=embeddings,
            documents=batch_texts,
            metadatas=batch_meta,
        )
        print(f"Embedded {min(i+batch_size, len(ids))}/{len(ids)} nodes")
    
    print(f"Done. {collection.count()} nodes stored in ChromaDB.")
    return collection