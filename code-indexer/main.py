import json
from pathlib import Path

from graph_builder import build_graph, load_graph, save_graph, stable_node_id
from indexer import index_fastapi
from enricher import enrich_with_docs, enrich_with_issues


def main():
    fastapi_dir = Path("fastapi")
    indexed_functions, import_records = index_fastapi(fastapi_dir)

    output_file = Path("code-indexer/indexed_functions.json")
    output_file.write_text(json.dumps(indexed_functions, indent=2), encoding="utf-8")

    imports_file = Path("code-indexer/import_records.json")
    imports_file.write_text(json.dumps(import_records, indent=2), encoding="utf-8")

    print(f"Saved {len(import_records)} import records to {imports_file}")
    print(f"Saved {len(indexed_functions)} functions to {output_file}")

    graph, name_index = build_graph(indexed_functions, import_records)
    graph_file = Path("code-indexer/graph.pkl")
    save_graph(graph, graph_file)
    print(f"Nodes: {graph.number_of_nodes()}")
    print(f"Edges: {graph.number_of_edges()}")

    graph = enrich_with_docs(graph, "fastapi/docs/en/docs", name_index)
    save_graph(graph, graph_file)
    print("Enrichment with docs complete.")

    graph = enrich_with_issues(graph, "fastapi/fastapi", name_index)
    save_graph(graph, graph_file)
    print("Enrichment with issues complete.")


if __name__ == "__main__":
    main()