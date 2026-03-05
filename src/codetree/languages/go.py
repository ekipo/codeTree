from tree_sitter import Language, Parser, Query
import tree_sitter_go as tsgo
from .base import LanguagePlugin, _matches

_LANGUAGE = Language(tsgo.language())
_PARSER = Parser(_LANGUAGE)


def _parse(source: bytes):
    return _PARSER.parse(source)


class GoPlugin(LanguagePlugin):
    extensions = (".go",)

    def extract_skeleton(self, source: bytes) -> list[dict]:
        tree = _parse(source)
        results = []

        # Structs (Go's equivalent of classes)
        q = Query(_LANGUAGE, """
            (source_file
                (type_declaration
                    (type_spec name: (type_identifier) @name
                               type: (struct_type))) @def)
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "struct",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": "",
            })

        # Methods (receiver functions)
        q = Query(_LANGUAGE, """
            (method_declaration
                receiver: (parameter_list
                    (parameter_declaration
                        type: [(type_identifier) @class_name
                               (pointer_type (type_identifier) @class_name)]))
                name: (field_identifier) @method_name
                parameters: (parameter_list) @params) @def
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "method",
                "name": m["method_name"].text.decode("utf-8", errors="replace"),
                "line": m["method_name"].start_point[0] + 1,
                "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        # Top-level functions
        q = Query(_LANGUAGE, """
            (source_file
                (function_declaration
                    name: (identifier) @name
                    parameters: (parameter_list) @params) @def)
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "function",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        results.sort(key=lambda x: x["line"])
        return results

    def extract_symbol_source(self, source: bytes, name: str) -> tuple[str, int] | None:
        tree = _parse(source)

        # Functions
        q = Query(_LANGUAGE, "(function_declaration name: (identifier) @name) @def")
        for _, m in _matches(q, tree.root_node):
            if m["name"].text.decode("utf-8", errors="replace") == name:
                node = m["def"]
                return (
                    source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
                    node.start_point[0] + 1,
                )

        # Struct types
        q = Query(_LANGUAGE, "(type_declaration (type_spec name: (type_identifier) @name)) @def")
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
        q = Query(_LANGUAGE, "(function_declaration name: (identifier) @name) @def")
        for _, m in _matches(q, tree.root_node):
            if m["name"].text.decode("utf-8", errors="replace") == fn_name:
                fn_node = m["def"]
                break
        if fn_node is None:
            return []
        q = Query(_LANGUAGE, """
            (call_expression function: [
                (identifier) @called
                (selector_expression field: (field_identifier) @called)
            ])
        """)
        calls = set()
        for _, m in _matches(q, fn_node):
            calls.add(m["called"].text.decode("utf-8", errors="replace"))
        return sorted(calls)

    def extract_symbol_usages(self, source: bytes, name: str) -> list[dict]:
        tree = _parse(source)
        usages = []
        seen = set()
        for node_type in ("identifier", "type_identifier", "field_identifier"):
            q = Query(_LANGUAGE, f'(({node_type}) @name (#eq? @name "{name}"))')
            for _, m in _matches(q, tree.root_node):
                node = m["name"]
                key = (node.start_point[0], node.start_point[1])
                if key not in seen:
                    seen.add(key)
                    usages.append({"line": node.start_point[0] + 1, "col": node.start_point[1]})
        usages.sort(key=lambda x: (x["line"], x["col"]))
        return usages
