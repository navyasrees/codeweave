from pathlib import Path
import json

def needs_rebuild():
    return (
        not Path("code-indexer/graph.pkl").exists() or
        not Path("code-indexer/chroma").exists()
    )

def run_pipeline():
    from indexer import index_fastapi
    from graph_builder import build_graph, save_graph
    from enricher import enrich_with_docs, enrich_with_tests
    from embedder import embed_and_store
    import json

    print("Starting pipeline rebuild...")

    fastapi_dir = Path("fastapi")

    # clone if not present
    if not fastapi_dir.exists():
        import subprocess
        print("Cloning FastAPI repo...")
        subprocess.run([
            "git", "clone",
            "https://github.com/fastapi/fastapi.git",
            "fastapi"
        ], check=True)

    indexed_functions, import_records = index_fastapi(fastapi_dir)

    Path("code-indexer/indexed_functions.json").write_text(
        json.dumps(indexed_functions, indent=2)
    )
    Path("code-indexer/import_records.json").write_text(
        json.dumps(import_records, indent=2)
    )

    graph, name_index = build_graph(indexed_functions, import_records)
    graph_file = Path("code-indexer/graph.pkl")
    save_graph(graph, graph_file)

    graph = enrich_with_docs(graph, "fastapi/docs/en/docs", name_index)
    save_graph(graph, graph_file)

    graph = enrich_with_tests(graph, "fastapi/tests", name_index)
    save_graph(graph, graph_file)

    embed_and_store(graph_file)
    print("Pipeline complete.")

if needs_rebuild():
    run_pipeline()
else:
    print("Artifacts already exist, skipping rebuild.")