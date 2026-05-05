import json
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CODE_DIR = BASE_DIR / "code-indexer"

# Ensure local modules (`code-indexer/indexer.py`, ...) are importable.
sys.path.insert(0, str(CODE_DIR))

def needs_rebuild():
    return (
        not (CODE_DIR / "graph.pkl").exists() or
        not (CODE_DIR / "chroma").exists()
    )

def run_pipeline():
    from indexer import index_fastapi
    from graph_builder import build_graph, save_graph
    from enricher import enrich_with_docs, enrich_with_tests
    from embedder import embed_and_store
    import json

    print("Starting pipeline rebuild...")

    fastapi_dir = CODE_DIR / "fastapi"
    graph_file = CODE_DIR / "graph.pkl"
    chroma_dir = CODE_DIR / "chroma"

    # clone if not present
    if not fastapi_dir.exists():
        print("Cloning FastAPI repo...")
        subprocess.run([
            "git", "clone",
            "https://github.com/fastapi/fastapi.git",
            str(fastapi_dir)
        ], check=True)

    indexed_functions, import_records = index_fastapi(fastapi_dir)

    (CODE_DIR / "indexed_functions.json").write_text(
        json.dumps(indexed_functions, indent=2)
    )
    (CODE_DIR / "import_records.json").write_text(
        json.dumps(import_records, indent=2)
    )

    graph, name_index = build_graph(indexed_functions, import_records)
    save_graph(graph, graph_file)

    graph = enrich_with_docs(graph, str(fastapi_dir / "docs/en/docs"), name_index)
    save_graph(graph, graph_file)

    graph = enrich_with_tests(graph, str(fastapi_dir / "tests"), name_index)
    save_graph(graph, graph_file)

    embed_and_store(graph_file, chroma_path=str(chroma_dir))
    print("Pipeline complete.")

if needs_rebuild():
    run_pipeline()
else:
    print("Artifacts already exist, skipping rebuild.")