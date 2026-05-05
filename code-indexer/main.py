import json
from pathlib import Path

from graph_builder import build_graph, load_graph, save_graph, stable_node_id
from indexer import index_fastapi


def main():
    fastapi_dir = Path("fastapi")
    indexed_functions, import_records = index_fastapi(fastapi_dir)

    output_file = Path("code-indexer/indexed_functions.json")
    output_file.write_text(json.dumps(indexed_functions, indent=2), encoding="utf-8")

    imports_file = Path("code-indexer/import_records.json")
    imports_file.write_text(json.dumps(import_records, indent=2), encoding="utf-8")

    print(f"Saved {len(import_records)} import records to {imports_file}")
    print(f"Saved {len(indexed_functions)} functions to {output_file}")

    graph = build_graph(indexed_functions, import_records)
    print(graph.number_of_nodes())
    print(f"Nodes: {graph.number_of_nodes()}")
    print(f"Edges: {graph.number_of_edges()}")

    graph_file = Path("code-indexer/graph.pkl")
    save_graph(graph, graph_file)
    graph = load_graph(graph_file)

    target_record = next(
        (record for record in indexed_functions if record["name"] == "OAuth2PasswordBearer"),
        None,
    )
    if target_record:
        node = stable_node_id(target_record)
        print(graph.nodes[node])
        print("Calls:", list(graph.successors(node)))
        print("Called by:", list(graph.predecessors(node)))


if __name__ == "__main__":
    main()