import pickle
from pathlib import Path

import os
from dotenv import load_dotenv
from github import Github

from indexer import PARSER, extract_imports

def enrich_with_issues(G, github_repo, name_index):
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    gh = Github(token)
    repo = gh.get_repo(github_repo)

    def normalize(text):
        cleaned = text.strip().lower()
        for ch in ("`", "*", "_", ":", "(", ")", "[", "]", "{", "}", ",", ".", "!", "?", "/"):
            cleaned = cleaned.replace(ch, " ")
        return " ".join(cleaned.split())

    for issue in repo.get_issues(state="all"):
        normalized_title = normalize(issue.title)
        matched_nodes = []

        for name, node_ids in name_index.items():
            if len(name) < 5:
                continue
            if normalize(name) in normalized_title:
                matched_nodes.extend(node_ids)

        for node_id in set(matched_nodes):
            if node_id not in G.nodes:
                continue
            G.nodes[node_id].setdefault("github_issues", []).append({
                "number": issue.number,
                "title": issue.title,
                "url": issue.html_url,
                "state": issue.state,
            })

    return G


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


def enrich_with_tests(G, tests_dir, name_index):
    tests_root = Path(tests_dir)
    if not tests_root.exists():
        print(f"Tests dir not found: {tests_root}")
        return G

    def normalize(name):
        return name.strip().lower()

    for test_file in tests_root.rglob("test_*.py"):
        source_code = test_file.read_bytes()
        tree = PARSER.parse(source_code)
        imports = extract_imports(source_code, tree.root_node)
        test_node_id = test_file.as_posix()

        if test_node_id not in G.nodes:
            G.add_node(test_node_id, type="test", file=test_node_id)

        for imp in imports:
            if not imp.startswith("from fastapi"):
                continue
            parts = imp.split("import")
            if len(parts) < 2:
                continue
            imported_names = [n.strip() for n in parts[1].split(",")]
            for name in imported_names:
                if len(name) < 5:
                    continue
                if name in name_index:
                    for node_id in name_index[name]:
                        if node_id in G.nodes:
                            G.add_edge(node_id, test_node_id, type="tested_by")

    return G