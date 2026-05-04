from pathlib import Path
import json

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)


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
    for py_file in sorted(base_dir.rglob("*.py")):
        source_code = py_file.read_bytes()
        tree = parser.parse(source_code)
        module_name = module_from_path(py_file.relative_to(base_dir.parent))
        walk(
            source_code=source_code,
            node=tree.root_node,
            functions=functions,
            file_path=py_file.relative_to(base_dir.parent),
            module_name=module_name,
        )
    return functions


if __name__ == "__main__":
    fastapi_dir = Path("fastapi")
    indexed_functions = index_fastapi(fastapi_dir)
    output_file = Path("code-indexer/indexed_functions.json")
    output_file.write_text(json.dumps(indexed_functions, indent=2), encoding="utf-8")
    print(f"Saved {len(indexed_functions)} functions to {output_file}")
