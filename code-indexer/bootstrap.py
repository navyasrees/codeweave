import json
import os
import subprocess
import sys
from pathlib import Path

# Make sure local modules (`indexer.py`, `graph_builder.py`, ...) are importable.
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))


def needs_rebuild() -> bool:
    graph_file = BASE_DIR / "graph.pkl"
    chroma_dir = BASE_DIR / "chroma"
    return (not graph_file.exists()) or (not chroma_dir.exists())


def run_pipeline() -> None:
    from embedder import embed_and_store
    from enricher import enrich_with_docs, enrich_with_tests
    from graph_builder import build_graph, save_graph
    from indexer import index_fastapi

    print("Starting pipeline rebuild...")

    fastapi_dir = BASE_DIR / "fastapi"
    graph_file = BASE_DIR / "graph.pkl"
    chroma_dir = BASE_DIR / "chroma"

    # clone if not present
    if not fastapi_dir.exists():
        print("Cloning FastAPI repo...")
        subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/fastapi/fastapi.git",
                str(fastapi_dir),
            ],
            check=True,
        )

    indexed_functions, import_records = index_fastapi(fastapi_dir)

    (BASE_DIR / "indexed_functions.json").write_text(
        json.dumps(indexed_functions, indent=2), encoding="utf-8"
    )
    (BASE_DIR / "import_records.json").write_text(
        json.dumps(import_records, indent=2), encoding="utf-8"
    )

    graph, name_index = build_graph(indexed_functions, import_records)
    save_graph(graph, graph_file)

    docs_dir = fastapi_dir / "docs/en/docs"
    graph = enrich_with_docs(graph, str(docs_dir), name_index)
    save_graph(graph, graph_file)

    tests_dir = fastapi_dir / "tests"
    graph = enrich_with_tests(graph, str(tests_dir), name_index)
    save_graph(graph, graph_file)

    # Store Chroma under a stable absolute directory.
    embed_and_store(graph_file, chroma_path=str(chroma_dir))
    print("Pipeline complete.")


if needs_rebuild():
    run_pipeline()
else:
    print("Artifacts already exist, skipping rebuild.")