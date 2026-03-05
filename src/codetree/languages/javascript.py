from tree_sitter import Language, Parser, Query
import tree_sitter_javascript as tsjs
from .base import LanguagePlugin, _matches

_LANGUAGE = Language(tsjs.language())
_PARSER = Parser(_LANGUAGE)


def _parse(source: bytes):
    return _PARSER.parse(source)


def _arrow_params(fn_node) -> str:
    """Extract params text from an arrow_function or function_expression node.

    Handles three forms:
      (a, b) => ...  →  formal_parameters node  →  "(a, b)"
      a => ...       →  bare identifier          →  "(a)"
      () => ...      →  formal_parameters node   →  "()"
    """
    for child in fn_node.children:
        if child.type == "formal_parameters":
            return child.text.decode("utf-8", errors="replace")
        if child.type == "identifier":
            return f"({child.text.decode('utf-8', errors='replace')})"
    return "()"


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

        # Methods inside classes
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

        # Top-level function declarations: function foo() {}
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

        # export default function foo() {}
        q = Query(lang, """
            (program (export_statement
                (function_declaration
                    name: (identifier) @name
                    parameters: (formal_parameters) @params) @def))
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "function",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        # const/let foo = () => {} and const/let foo = function() {}
        # Both at module level and exported (export const foo = ...)
        for q_str in [
            """(program (lexical_declaration
                (variable_declarator
                    name: (identifier) @name
                    value: [(arrow_function) @fn (function_expression) @fn])))""",
            """(program (export_statement (lexical_declaration
                (variable_declarator
                    name: (identifier) @name
                    value: [(arrow_function) @fn (function_expression) @fn]))))""",
        ]:
            for _, m in _matches(Query(lang, q_str), tree.root_node):
                fn_node = m.get("fn")
                results.append({
                    "type": "function",
                    "name": m["name"].text.decode("utf-8", errors="replace"),
                    "line": m["name"].start_point[0] + 1,
                    "parent": None,
                    "params": _arrow_params(fn_node) if fn_node else "()",
                })

        # Deduplicate by (name, line)
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
        lang = self._get_language()
        tree = self._get_parser().parse(source)

        # function_declaration and class_declaration (plain and export default)
        for q_str in [
            "(function_declaration name: (identifier) @name) @def",
            "(class_declaration name: (identifier) @name) @def",
            "(export_statement (function_declaration name: (identifier) @name) @def)",
            "(export_statement (class_declaration name: (identifier) @name) @def)",
        ]:
            for _, m in _matches(Query(lang, q_str), tree.root_node):
                if m["name"].text.decode("utf-8", errors="replace") == name:
                    node = m["def"]
                    return (
                        source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
                        node.start_point[0] + 1,
                    )

        # const/let foo = () => {} (plain and exported) — return full lexical_declaration
        for q_str in [
            """(lexical_declaration
                (variable_declarator
                    name: (identifier) @name
                    value: [(arrow_function) (function_expression)])) @def""",
            """(export_statement (lexical_declaration
                (variable_declarator
                    name: (identifier) @name
                    value: [(arrow_function) (function_expression)])) @def)""",
        ]:
            for _, m in _matches(Query(lang, q_str), tree.root_node):
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

        # function_declaration (plain and export default)
        for q_str in [
            "(function_declaration name: (identifier) @name) @def",
            "(export_statement (function_declaration name: (identifier) @name) @def)",
        ]:
            for _, m in _matches(Query(lang, q_str), tree.root_node):
                if m["name"].text.decode("utf-8", errors="replace") == fn_name:
                    fn_node = m["def"]
                    break
            if fn_node:
                break

        # const/let foo = () => {} (plain and exported)
        if fn_node is None:
            for q_str in [
                """(variable_declarator
                    name: (identifier) @name
                    value: [(arrow_function) @def (function_expression) @def])""",
            ]:
                for _, m in _matches(Query(lang, q_str), tree.root_node):
                    if m["name"].text.decode("utf-8", errors="replace") == fn_name:
                        fn_node = m["def"]
                        break
                if fn_node:
                    break

        if fn_node is None:
            return []

        q_call = Query(lang, """
            (call_expression function: [
                (identifier) @called
                (member_expression property: (property_identifier) @called)
            ])
        """)
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
