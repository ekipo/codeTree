from tree_sitter import Language, Parser, Query, QueryCursor
import tree_sitter_javascript as tsjs
from .base import LanguagePlugin

_LANGUAGE = Language(tsjs.language())
_PARSER = Parser(_LANGUAGE)


def _parse(source: bytes):
    return _PARSER.parse(source)


def _matches(query: Query, node) -> list[tuple[int, dict]]:
    cursor = QueryCursor(query)
    result = []
    for pattern_idx, match in cursor.matches(node):
        unwrapped = {
            name: nodes[0] if isinstance(nodes, list) and nodes else nodes
            for name, nodes in match.items()
        }
        result.append((pattern_idx, unwrapped))
    return result


class JavaScriptPlugin(LanguagePlugin):
    extensions = (".js", ".jsx")
    _lang = _LANGUAGE
    _parser = _PARSER

    def _get_language(self):
        return self._lang

    def _get_parser(self):
        return self._parser

    def extract_skeleton(self, source: bytes) -> list[dict]:
        lang = self._get_language()
        tree = self._get_parser().parse(source)
        results = []

        # Top-level classes
        q = Query(lang, "(program (class_declaration name: (identifier) @name) @def)")
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "class",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": "",
            })

        # Methods inside classes (JS uses property_identifier for method names)
        q = Query(lang, """
            (class_declaration
                name: (identifier) @class_name
                body: (class_body
                    (method_definition
                        name: (property_identifier) @method_name
                        parameters: (formal_parameters) @params)))
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "method",
                "name": m["method_name"].text.decode("utf-8", errors="replace"),
                "line": m["method_name"].start_point[0] + 1,
                "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        # Top-level function declarations
        q = Query(lang, """
            (program (function_declaration
                name: (identifier) @name
                parameters: (formal_parameters) @params))
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
        lang = self._get_language()
        tree = self._get_parser().parse(source)
        for node_type, name_field in [
            ("function_declaration", "identifier"),
            ("class_declaration", "identifier"),
        ]:
            q = Query(lang, f"({node_type} name: ({name_field}) @name) @def")
            for _, m in _matches(q, tree.root_node):
                if m["name"].text.decode("utf-8", errors="replace") == name:
                    node = m["def"]
                    return (
                        source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
                        node.start_point[0] + 1,
                    )
        return None

    def extract_calls_in_function(self, source: bytes, fn_name: str) -> list[str]:
        lang = self._get_language()
        tree = self._get_parser().parse(source)
        fn_node = None
        q = Query(lang, "(function_declaration name: (identifier) @name) @def")
        for _, m in _matches(q, tree.root_node):
            if m["name"].text.decode("utf-8", errors="replace") == fn_name:
                fn_node = m["def"]
                break
        if fn_node is None:
            return []
        # Regular calls: foo() and obj.method()
        q_call = Query(lang, """
            (call_expression function: [
                (identifier) @called
                (member_expression property: (property_identifier) @called)
            ])
        """)
        # Constructor calls: new Foo()
        q_new = Query(lang, "(new_expression constructor: (identifier) @called)")
        calls = set()
        for _, m in _matches(q_call, fn_node):
            calls.add(m["called"].text.decode("utf-8", errors="replace"))
        for _, m in _matches(q_new, fn_node):
            calls.add(m["called"].text.decode("utf-8", errors="replace"))
        return sorted(calls)

    def extract_symbol_usages(self, source: bytes, name: str) -> list[dict]:
        lang = self._get_language()
        tree = self._get_parser().parse(source)
        q = Query(lang, f'((identifier) @name (#eq? @name "{name}"))')
        usages = []
        for _, m in _matches(q, tree.root_node):
            node = m["name"]
            usages.append({"line": node.start_point[0] + 1, "col": node.start_point[1]})
        return usages
