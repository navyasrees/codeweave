from pathlib import Path
import json

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)

def extract_imports(source_code, root_node):
    imports = []
    for child in root_node.children:
        if child.type in ("import_statement", "import_from_statement"):
            imports.append(node_text(source_code, child).strip())
    return imports

def node_text(source_code, node):
    return source_code[node.start_byte:node.end_byte].decode("utf8")


def collect_calls(source_code, node):
    calls = []
    if node.type == "call":
        function_node = node.child_by_field_name("function")
        if function_node:
            calls.append(node_text(source_code, function_node))

    for child in node.children:
        calls.extend(collect_calls(source_code, child))
    return calls


def extract_docstring(source_code, function_node):
    body = function_node.child_by_field_name("body")
    if not body or body.child_count == 0:
        return None

    first_stmt = body.child(0)
    if not first_stmt or first_stmt.type != "expression_statement":
        return None

    if first_stmt.child_count == 0:
        return None

    expr = first_stmt.child(0)
    if expr and expr.type == "string":
        docstring = node_text(source_code, expr)
        return docstring.strip("\"'")
    return None


def extract_params(source_code, function_node):
    params_node = function_node.child_by_field_name("parameters")
    if not params_node:
        return []

    params = []
    for child in params_node.children:
        if child.type == "identifier":
            params.append(node_text(source_code, child))
    return params


def extract_decorators(source_code, node):
    decorators = []
    for child in node.children:
        if child.type == "decorator":
            decorators.append(node_text(source_code, child).strip())
    return decorators


def walk(source_code, node, functions, file_path, module_name, parent_class=None, decorators=None):
    if decorators is None:
        decorators = []

    if node.type == "decorated_definition":
        # collect decorators from this wrapper node
        node_decorators = [
            node_text(source_code, child).strip()
            for child in node.children
            if child.type == "decorator"
        ]
        # find the actual definition inside and walk it with decorators attached
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                walk(source_code, child, functions, file_path, module_name, parent_class, node_decorators)
        return  # don't fall through to generic recursion

    if node.type == "function_definition":
        name_node = node.child_by_field_name("name")
        function_info = {
            "type": "function",
            "name": node_text(source_code, name_node) if name_node else None,
            "file": file_path.as_posix(),
            "module": module_name,
            "parent_class": parent_class,
            "decorators": decorators,   # ← now populated correctly
            "params": extract_params(source_code, node),
            "docstring": extract_docstring(source_code, node),
            "calls": collect_calls(source_code, node),
            "line_range": [node.start_point[0] + 1, node.end_point[0] + 1],
        }
        functions.append(function_info)
        # recurse into body with parent_class set
        for child in node.children:
            walk(source_code, child, functions, file_path, module_name, parent_class)
        return

    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        class_info = {
            "type": "class",
            "name": node_text(source_code, name_node) if name_node else None,
            "file": file_path.as_posix(),
            "module": module_name,
            "parent_class": parent_class,
            "decorators": decorators,
            "methods": [
                node_text(source_code, child.child_by_field_name("name"))
                for child in (body_node.children if body_node else [])
                if child.type == "function_definition"
                and child.child_by_field_name("name")
            ],
            "docstring": extract_docstring(source_code, node),
            "line_range": [node.start_point[0] + 1, node.end_point[0] + 1],
        }
        functions.append(class_info)
        # recurse into class body passing parent_class
        for child in node.children:
            walk(source_code, child, functions, file_path, module_name,
                 parent_class=node_text(source_code, name_node) if name_node else None)
        return

    for child in node.children:
        walk(source_code, child, functions, file_path, module_name, parent_class)

def module_from_path(file_path):
    parts = list(file_path.parts)
    if parts and parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def index_fastapi(base_dir):
    functions = []
    import_records = []                          # ← add this
    for py_file in sorted(base_dir.rglob("*.py")):
        source_code = py_file.read_bytes()
        tree = parser.parse(source_code)
        module_name = module_from_path(py_file.relative_to(base_dir.parent))
        
        import_records.append({                  # ← add this
            "file": py_file.relative_to(base_dir.parent).as_posix(),
            "module": module_name,
            "imports": extract_imports(source_code, tree.root_node)
        })
        
        walk(
            source_code=source_code,
            node=tree.root_node,
            functions=functions,
            file_path=py_file.relative_to(base_dir.parent),
            module_name=module_name,
        )
    return functions, import_records             # ← return both

if __name__ == "__main__":
    fastapi_dir = Path("fastapi")
    indexed_functions, import_records = index_fastapi(fastapi_dir)
    output_file = Path("code-indexer/indexed_functions.json")
    output_file.write_text(json.dumps(indexed_functions, indent=2), encoding="utf-8")
    imports_file = Path("code-indexer/import_records.json")
    imports_file.write_text(json.dumps(import_records, indent=2), encoding="utf-8")
    print(f"Saved {len(import_records)} import records to {imports_file}")
    print(f"Saved {len(indexed_functions)} functions to {output_file}")

import json
import networkx as nx


def stable_node_id(record: dict) -> str:
    """Unique per definition site: same module+name in different files or lines stays distinct."""
    parent = record.get("parent_class")
    qual_name = f"{parent}.{record['name']}" if parent else record["name"]
    start_line = record["line_range"][0]
    return f"{record['file']}:{start_line}:{record['type']}:{qual_name}"


G = nx.DiGraph()

with open("code-indexer/indexed_functions.json") as f:
    records = json.load(f)

for record in records:
    G.add_node(stable_node_id(record), **record)

assert G.number_of_nodes() == len(records), (
    f"node id collision: {len(records)} records vs {G.number_of_nodes()} nodes"
)
print(G.number_of_nodes())

# name -> list of node_ids that have that name
# list because the same name can exist in multiple modules
name_index = {}
for record in records:
    name = record["name"]
    node_id = f"{record['module']}.{record['name']}"
    if name not in name_index:
        name_index[name] = []
    name_index[name].append(node_id)

for record in records:
    caller_id = f"{record['module']}.{record['name']}"
    for call_name in record.get("calls", []):
        # strip attribute chains — "self.validator.check" → "check"
        base_name = call_name.split(".")[-1]
        
        if base_name in name_index:
            candidates = name_index[base_name]
            
            if len(candidates) == 1:
                # unambiguous — draw the edge
                G.add_edge(caller_id, candidates[0], type="calls")
            else:
                # multiple matches — prefer same module
                same_module = [c for c in candidates if record["module"] in c]
                target = same_module[0] if same_module else candidates[0]
                G.add_edge(caller_id, target, type="calls")

for file_record in import_records:
    from_module = file_record["module"]
    for imp in file_record["imports"]:
        # "from fastapi.security import OAuth2" → "fastapi.security"
        if imp.startswith("from "):
            parts = imp.split()
            to_module = parts[1]
            G.add_edge(from_module, to_module, type="imports")

import pickle
import networkx as nx

with open("code-indexer/graph.pkl", "wb") as f:
    pickle.dump(G, f)
with open("code-indexer/graph.pkl", "rb") as f:
    G = pickle.load(f)

# basic stats
print(f"Nodes: {G.number_of_nodes()}")
print(f"Edges: {G.number_of_edges()}")

# look at a specific node and its attributes
node = "fastapi/fastapi/security/oauth2.py:433:class:OAuth2PasswordBearer"
print(G.nodes[node])

# what does it call?
print("Calls:", list(G.successors(node)))

# what calls it?
print("Called by:", list(G.predecessors(node)))