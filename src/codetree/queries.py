from tree_sitter import Language, Parser, Query, QueryCursor
import tree_sitter_python as tspython

PY_LANGUAGE = Language(tspython.language())
_parser = Parser(PY_LANGUAGE)


def _parse(source: bytes):
    return _parser.parse(source)


def _query_matches(query: Query, node) -> list[tuple[int, dict]]:
    """Execute a query against a node using QueryCursor and return matches.

    Each match is a tuple of (pattern_index, capture_dict) where capture_dict
    maps capture names to the first captured node (unwrapping the list).
    """
    cursor = QueryCursor(query)
    raw_matches = cursor.matches(node)
    result = []
    for pattern_idx, match in raw_matches:
        # In tree-sitter 0.25.x, each capture value is a list of nodes.
        # Unwrap to a single node (first element) for convenience.
        unwrapped = {
            name: nodes[0] if isinstance(nodes, list) and nodes else nodes
            for name, nodes in match.items()
        }
        result.append((pattern_idx, unwrapped))
    return result


def extract_skeleton(source: bytes) -> list[dict]:
    """Return top-level classes, their methods, and top-level functions with name, type, line, parent_class.

    Nested functions and nested classes are intentionally excluded; only the
    module-level constructs and one level of class body are captured.
    """
    tree = _parse(source)
    results = []

    # Top-level classes
    class_query = Query(PY_LANGUAGE, """
        (module (class_definition name: (identifier) @name) @def)
    """)
    for _, match in _query_matches(class_query, tree.root_node):
        name_node = match["name"]
        results.append({
            "type": "class",
            "name": name_node.text.decode("utf-8", errors="replace"),
            "line": name_node.start_point[0] + 1,
            "parent": None,
        })

    # Methods inside classes
    method_query = Query(PY_LANGUAGE, """
        (class_definition
            name: (identifier) @class_name
            body: (block
                (function_definition
                    name: (identifier) @method_name) @method_def))
    """)
    for _, match in _query_matches(method_query, tree.root_node):
        method_node = match["method_name"]
        class_node = match["class_name"]
        results.append({
            "type": "method",
            "name": method_node.text.decode("utf-8", errors="replace"),
            "line": method_node.start_point[0] + 1,
            "parent": class_node.text.decode("utf-8", errors="replace"),
        })

    # Top-level functions (not inside a class)
    fn_query = Query(PY_LANGUAGE, """
        (module (function_definition name: (identifier) @name) @def)
    """)
    for _, match in _query_matches(fn_query, tree.root_node):
        name_node = match["name"]
        results.append({
            "type": "function",
            "name": name_node.text.decode("utf-8", errors="replace"),
            "line": name_node.start_point[0] + 1,
            "parent": None,
        })

    results.sort(key=lambda x: x["line"])
    return results


def extract_symbol_source(source: bytes, symbol_name: str) -> tuple[str, int] | None:
    """Return (source_text, start_line) for a named function or class. None if not found."""
    tree = _parse(source)

    for node_type in ("function_definition", "class_definition"):
        query = Query(PY_LANGUAGE, f"""
            ({node_type} name: (identifier) @name) @def
        """)
        for _, match in _query_matches(query, tree.root_node):
            name_node = match["name"]
            if name_node.text.decode("utf-8", errors="replace") == symbol_name:
                def_node = match["def"]
                start_line = def_node.start_point[0] + 1
                text = source[def_node.start_byte:def_node.end_byte].decode("utf-8", errors="replace")
                return text, start_line

    return None


def extract_calls_in_function(source: bytes, function_name: str) -> list[str]:
    """Return all function/method names called inside a named function."""
    tree = _parse(source)

    fn_query = Query(PY_LANGUAGE, """
        (function_definition name: (identifier) @name) @def
    """)
    fn_node = None
    for _, match in _query_matches(fn_query, tree.root_node):
        if match["name"].text.decode("utf-8", errors="replace") == function_name:
            fn_node = match["def"]
            break

    if fn_node is None:
        return []

    call_query = Query(PY_LANGUAGE, """
        (call function: [
            (identifier) @called
            (attribute attribute: (identifier) @called)
        ])
    """)
    calls = set()
    for _, match in _query_matches(call_query, fn_node):
        calls.add(match["called"].text.decode("utf-8", errors="replace"))

    return sorted(calls)


def extract_symbol_usages(source: bytes, symbol_name: str) -> list[dict]:
    """Return all lines where symbol_name appears as an identifier."""
    tree = _parse(source)
    # Use the #eq? predicate to let the tree-sitter query engine filter by name,
    # avoiding a Python-level loop over every identifier in the file.
    query = Query(PY_LANGUAGE, f'((identifier) @name (#eq? @name "{symbol_name}"))')
    usages = []
    for _, match in _query_matches(query, tree.root_node):
        node = match["name"]
        usages.append({
            "line": node.start_point[0] + 1,
            "col": node.start_point[1],
        })
    return usages
