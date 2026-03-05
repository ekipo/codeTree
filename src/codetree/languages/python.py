from tree_sitter import Language, Parser, Query
import tree_sitter_python as tspython
from .base import LanguagePlugin, _matches

_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_LANGUAGE)


def _parse(source: bytes):
    return _PARSER.parse(source)


def _fn_params(fn_node) -> str:
    """Extract params text from a function_definition node."""
    for child in fn_node.children:
        if child.type == "parameters":
            return child.text.decode("utf-8", errors="replace")
    return "()"


class PythonPlugin(LanguagePlugin):
    extensions = (".py",)

    def extract_skeleton(self, source: bytes) -> list[dict]:
        tree = _parse(source)
        results = []

        # Top-level classes — plain and decorated
        for q_str in [
            "(module (class_definition name: (identifier) @name) @def)",
            "(module (decorated_definition (class_definition name: (identifier) @name)) @def)",
        ]:
            for _, m in _matches(Query(_LANGUAGE, q_str), tree.root_node):
                results.append({
                    "type": "class",
                    "name": m["name"].text.decode("utf-8", errors="replace"),
                    "line": m["name"].start_point[0] + 1,
                    "parent": None,
                    "params": "",
                })

        # Methods inside classes — plain and decorated
        for q_str in [
            """(class_definition
                name: (identifier) @class_name
                body: (block
                    (function_definition
                        name: (identifier) @method_name
                        parameters: (parameters) @params)))""",
            """(class_definition
                name: (identifier) @class_name
                body: (block
                    (decorated_definition
                        (function_definition
                            name: (identifier) @method_name
                            parameters: (parameters) @params))))""",
        ]:
            for _, m in _matches(Query(_LANGUAGE, q_str), tree.root_node):
                results.append({
                    "type": "method",
                    "name": m["method_name"].text.decode("utf-8", errors="replace"),
                    "line": m["method_name"].start_point[0] + 1,
                    "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                    "params": m["params"].text.decode("utf-8", errors="replace"),
                })

        # Top-level functions — plain and decorated
        for q_str in [
            """(module (function_definition
                name: (identifier) @name
                parameters: (parameters) @params))""",
            """(module (decorated_definition
                (function_definition
                    name: (identifier) @name
                    parameters: (parameters) @params)) @def)""",
        ]:
            for _, m in _matches(Query(_LANGUAGE, q_str), tree.root_node):
                results.append({
                    "type": "function",
                    "name": m["name"].text.decode("utf-8", errors="replace"),
                    "line": m["name"].start_point[0] + 1,
                    "parent": None,
                    "params": m["params"].text.decode("utf-8", errors="replace"),
                })

        # Deduplicate by (name, line) — queries can overlap on edge cases
        seen = set()
        deduped = []
        for item in results:
            key = (item["name"], item["line"])
            if key not in seen:
                seen.add(key)
                deduped.append(item)

        deduped.sort(key=lambda x: x["line"])
        return deduped

    def extract_symbol_source(self, source: bytes, name: str) -> tuple[str, int] | None:
        tree = _parse(source)
        for node_type in ("function_definition", "class_definition"):
            # Decorated definition first — return full decorated_definition (includes decorator)
            q = Query(_LANGUAGE, f"(decorated_definition ({node_type} name: (identifier) @name)) @def")
            for _, m in _matches(q, tree.root_node):
                if m["name"].text.decode("utf-8", errors="replace") == name:
                    node = m["def"]
                    return (
                        source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
                        node.start_point[0] + 1,
                    )
            # Plain definition (not decorated)
            q = Query(_LANGUAGE, f"({node_type} name: (identifier) @name) @def")
            for _, m in _matches(q, tree.root_node):
                if m["name"].text.decode("utf-8", errors="replace") == name:
                    node = m["def"]
                    return (
                        source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
                        node.start_point[0] + 1,
                    )
        return None

    def extract_calls_in_function(self, source: bytes, fn_name: str) -> list[str]:
        tree = _parse(source)
        fn_node = None
        # Search plain and decorated function definitions
        for q_str in [
            "(function_definition name: (identifier) @name) @def",
            "(decorated_definition (function_definition name: (identifier) @name)) @def",
        ]:
            for _, m in _matches(Query(_LANGUAGE, q_str), tree.root_node):
                if m["name"].text.decode("utf-8", errors="replace") == fn_name:
                    fn_node = m["def"]
                    break
            if fn_node is not None:
                break
        if fn_node is None:
            return []
        q = Query(_LANGUAGE, """
            (call function: [
                (identifier) @called
                (attribute attribute: (identifier) @called)
            ])
        """)
        calls = set()
        for _, m in _matches(q, fn_node):
            calls.add(m["called"].text.decode("utf-8", errors="replace"))
        return sorted(calls)

    def extract_symbol_usages(self, source: bytes, name: str) -> list[dict]:
        tree = _parse(source)
        q = Query(_LANGUAGE, f'((identifier) @name (#eq? @name "{name}"))')
        usages = []
        for _, m in _matches(q, tree.root_node):
            node = m["name"]
            usages.append({"line": node.start_point[0] + 1, "col": node.start_point[1]})
        return usages
