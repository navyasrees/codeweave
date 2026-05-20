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
    # Qualified name index: "ClassName.method" → [node_id, ...]
    # Used to resolve calls that were upgraded by collect_assignments, e.g.
    # `adapter = HTTPAdapter(); adapter.send(...)` → call stored as "HTTPAdapter.send"
    # which we can now match precisely to the HTTPAdapter.send node.
    qualified_name_index = {}

    for record in records:
        name = record["name"]
        node_id = stable_node_id(record)

        if name not in name_index:
            name_index[name] = []
        name_index[name].append(node_id)

        parent = record.get("parent_class")
        if parent:
            qual = f"{parent}.{name}"
            if qual not in qualified_name_index:
                qualified_name_index[qual] = []
            qualified_name_index[qual].append(node_id)

    for record in records:
        caller_id = stable_node_id(record)
        for call_name in record.get("calls", []):
            # 1. Exact qualified match: "HTTPAdapter.send" → right node directly
            if "." in call_name and call_name in qualified_name_index:
                for target_id in qualified_name_index[call_name]:
                    graph.add_edge(caller_id, target_id, type="calls")
                continue

            # 2. Fallback: strip to base name, prefer same-module candidate
            base_name = call_name.split(".")[-1]
            if base_name in name_index:
                candidates = name_index[base_name]
                if len(candidates) == 1:
                    graph.add_edge(caller_id, candidates[0], type="calls")
                else:
                    same_module = [c for c in candidates if record["module"] in c]
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

    return graph, name_index, qualified_name_index


def save_graph(graph, output_path):
    with open(output_path, "wb") as f:
        pickle.dump(graph, f)


def load_graph(graph_path):
    with open(graph_path, "rb") as f:
        return pickle.load(f)
