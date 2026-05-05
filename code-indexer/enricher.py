import pickle
from pathlib import Path


def enrich_with_docs(G, docs_dir, name_index):
    docs_root = Path(docs_dir)

    if not docs_root.exists():
        docs_root = Path("fastapi/docs/en/docs")

    def normalize(text):
        cleaned = text.strip().lower()
        for ch in ("`", "*", "_", ":", "(", ")", "[", "]", "{", "}", ",", ".", "!", "?", "/"):
            cleaned = cleaned.replace(ch, " ")
        return " ".join(cleaned.split())

    normalized_index = {}
    for name, node_ids in name_index.items():
        normalized_index.setdefault(normalize(name), []).extend(node_ids)

    for md_path in docs_root.rglob("*.md"):
        rel_path = md_path.as_posix()
        lines = md_path.read_text(encoding="utf-8").splitlines()

        sections = []
        current_heading = None
        current_content = []

        for line in lines:
            if line.startswith("#"):
                if current_heading is not None:
                    sections.append((current_heading, "\n".join(current_content).strip()))
                current_heading = line.lstrip("#").strip()
                current_content = []
            elif current_heading is not None:
                current_content.append(line)

        if current_heading is not None:
            sections.append((current_heading, "\n".join(current_content).strip()))

        for heading, content in sections:
            matched_nodes = []
            normalized_heading = normalize(heading)

            for name, node_ids in name_index.items():
                if normalize(name) in normalized_heading:
                    matched_nodes.extend(node_ids)

            for node_id in set(matched_nodes):
                if node_id not in G.nodes:
                    continue
                G.nodes[node_id].setdefault("doc_sections", []).append({
                    "source": rel_path,
                    "heading": heading,
                    "content": content,
                })

    return G
