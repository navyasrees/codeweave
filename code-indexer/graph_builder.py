import pickle

import networkx as nx


def stable_node_id(record: dict) -> str:
    parent = record.get("parent_class")
    qual_name = f"{parent}.{record['name']}" if parent else record["name"]
    start_line = record["line_range"][0]
    return f"{record['file']}:{start_line}:{record['type']}:{qual_name}"


def build_graph(records, import_records):
    graph = nx.DiGraph()

    for record in records:
        graph.add_node(stable_node_id(record), **record)

    assert graph.number_of_nodes() == len(records), (
        f"node id collision: {len(records)} records vs {graph.number_of_nodes()} nodes"
    )

    name_index = {}
    for record in records:
        node_id = stable_node_id(record)
        name_index.setdefault(record["name"], []).append(node_id)

    for record in records:
        caller_id = stable_node_id(record)
        for call_name in record.get("calls", []):
            base_name = call_name.split(".")[-1]
            candidates = name_index.get(base_name, [])
            if not candidates:
                continue

            if len(candidates) == 1:
                graph.add_edge(caller_id, candidates[0], type="calls")
                continue

            preferred_prefix = f"{record['module']}."
            same_module = [cand for cand in candidates if cand.startswith(preferred_prefix)]
            target = same_module[0] if same_module else candidates[0]
            graph.add_edge(caller_id, target, type="calls")

    for file_record in import_records:
        from_module = file_record["module"]
        for imp in file_record.get("imports", []):
            if not imp.startswith("from "):
                continue
            parts = imp.split()
            if len(parts) < 2:
                continue
            to_module = parts[1]
            graph.add_edge(from_module, to_module, type="imports")

    return graph


def save_graph(graph, output_path):
    with open(output_path, "wb") as f:
        pickle.dump(graph, f)


def load_graph(graph_path):
    with open(graph_path, "rb") as f:
        return pickle.load(f)
