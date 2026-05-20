from pathlib import Path

# pyrefly: ignore [missing-import]
import tree_sitter_python as tspython
# pyrefly: ignore [missing-import]
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())
PARSER = Parser(PY_LANGUAGE)


def node_text(source_code, node):
    return source_code[node.start_byte:node.end_byte].decode("utf8")


def extract_imports(source_code, root_node):
    imports = []
    for child in root_node.children:
        if child.type in ("import_statement", "import_from_statement"):
            imports.append(node_text(source_code, child).strip())
    return imports


def collect_assignments(source_code, node):
    """Return {var_name: class_name} for all `var = ClassName()` assignments in the subtree.

    Handles patterns like:
        adapter = HTTPAdapter()
        self.session = Session()

    Used so collect_calls can resolve `adapter.send(...)` → `HTTPAdapter.send`
    instead of the ambiguous bare name `send`.
    Only the immediate constructed class is tracked (no alias chains).
    """
    assignments = {}
    _collect_assignments_rec(source_code, node, assignments)
    return assignments


def _collect_assignments_rec(source_code, node, assignments):
    if node.type == "assignment":
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left and right and right.type == "call":
            func = right.child_by_field_name("function")
            if func:
                # module.ClassName() → ClassName
                class_name = node_text(source_code, func).split(".")[-1]
                # self.adapter → adapter
                var_name = node_text(source_code, left).split(".")[-1]
                assignments[var_name] = class_name
    for child in node.children:
        _collect_assignments_rec(source_code, child, assignments)


def collect_calls(source_code, node, assignments=None):
    """Collect all call expressions in the subtree.

    When `assignments` is provided, attribute calls like `adapter.send(...)`
    are resolved to `HTTPAdapter.send` if `adapter` appears as a key in
    assignments (i.e. was constructed via `adapter = HTTPAdapter()`).
    This makes blast-radius graph edges accurate for polymorphic dispatch.
    """
    if assignments is None:
        assignments = {}

    calls = []
    if node.type == "call":
        function_node = node.child_by_field_name("function")
        if function_node:
            call_text = node_text(source_code, function_node)
            # Try to resolve var.method() → ClassName.method
            if "." in call_text:
                var_part, _, method_part = call_text.partition(".")
                if var_part in assignments:
                    call_text = f"{assignments[var_part]}.{method_part}"
            calls.append(call_text)

    for child in node.children:
        calls.extend(collect_calls(source_code, child, assignments))
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
            # plain param: def f(x)
            params.append(node_text(source_code, child))
        elif child.type in ("typed_parameter", "typed_default_parameter"):
            # annotated param: def f(x: int) or def f(x: int = 0)
            # tree-sitter Python uses positional children for typed_parameter,
            # not named fields — the identifier is always the first child
            name_node = next(
                (c for c in child.children if c.type == "identifier"), None
            )
            type_node = child.child_by_field_name("type")
            if name_node:
                name = node_text(source_code, name_node)
                if type_node:
                    params.append(f"{name}: {node_text(source_code, type_node)}")
                else:
                    params.append(name)
        elif child.type == "default_parameter":
            # param with default but no annotation: def f(x=None)
            name_node = child.child_by_field_name("name")
            if name_node:
                params.append(node_text(source_code, name_node))
    return params


def walk(
    source_code,
    node,
    functions,
    file_path,
    module_name,
    parent_class=None,
    decorators=None,
):
    if decorators is None:
        decorators = []

    if node.type == "decorated_definition":
        node_decorators = [
            node_text(source_code, child).strip()
            for child in node.children
            if child.type == "decorator"
        ]
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                walk(
                    source_code,
                    child,
                    functions,
                    file_path,
                    module_name,
                    parent_class,
                    node_decorators,
                )
        return

    if node.type == "function_definition":
        name_node = node.child_by_field_name("name")
        # extract source snippet — cap at 30 lines
        start = node.start_point[0]
        end = node.end_point[0]
        source_lines = source_code.decode("utf8").splitlines()
        snippet = "\n".join(source_lines[start:min(end+1, start+30)])

        # Build a local var→class map for this function body so that calls like
        # `adapter.send(...)` resolve to `HTTPAdapter.send` rather than bare `send`.
        assignments = collect_assignments(source_code, node)

        function_info = {
            "type": "function",
            "name": node_text(source_code, name_node) if name_node else None,
            "file": file_path.as_posix(),
            "module": module_name,
            "parent_class": parent_class,
            "decorators": decorators,
            "params": extract_params(source_code, node),
            "docstring": extract_docstring(source_code, node),
            "calls": collect_calls(source_code, node, assignments),
            "line_range": [node.start_point[0] + 1, node.end_point[0] + 1],
            "snippet": snippet,
        }
        functions.append(function_info)
        for child in node.children:
            walk(source_code, child, functions, file_path, module_name, parent_class)
        return

    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        class_name = node_text(source_code, name_node) if name_node else None
        class_info = {
            "type": "class",
            "name": class_name,
            "file": file_path.as_posix(),
            "module": module_name,
            "parent_class": parent_class,
            "decorators": decorators,
            "methods": [
                node_text(source_code, child.child_by_field_name("name"))
                for child in (body_node.children if body_node else [])
                if child.type == "function_definition" and child.child_by_field_name("name")
            ],
            "docstring": extract_docstring(source_code, node),
            "line_range": [node.start_point[0] + 1, node.end_point[0] + 1],
        }
        functions.append(class_info)
        for child in node.children:
            walk(
                source_code,
                child,
                functions,
                file_path,
                module_name,
                parent_class=class_name,
            )
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


_TEST_DIRS = {"tests", "t", "test"}


def _is_test_file(py_file: Path, base_dir: Path) -> bool:
    """Return True if this file lives under a test directory.

    Checks each path component between base_dir and the file so that
    deeply nested test trees (e.g. t/unit/tasks/test_tasks.py) are caught
    regardless of how many subdirectory levels separate them from the root.
    This is a defence-in-depth guard — detector.py should already exclude
    test roots from source_dir, but this catches any edge cases.
    """
    try:
        relative = py_file.relative_to(base_dir)
    except ValueError:
        return False
    parts = relative.parts[:-1]   # directory components only, not the filename
    for part in parts:
        if part in _TEST_DIRS:
            return True
    filename = py_file.name
    return filename.startswith("test_") or filename.endswith("_test.py")


def index_repo(base_dir: Path):
    functions = []
    import_records = []

    for py_file in sorted(base_dir.rglob("*.py")):
        if _is_test_file(py_file, base_dir):
            continue
        source_code = py_file.read_bytes()
        tree = PARSER.parse(source_code)
        rel_file = py_file.relative_to(base_dir.parent)
        module_name = module_from_path(rel_file)

        import_records.append(
            {
                "file": rel_file.as_posix(),
                "module": module_name,
                "imports": extract_imports(source_code, tree.root_node),
            }
        )

        walk(
            source_code=source_code,
            node=tree.root_node,
            functions=functions,
            file_path=rel_file,
            module_name=module_name,
        )

    return functions, import_records
