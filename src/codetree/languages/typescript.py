from tree_sitter import Language, Parser, Query
import tree_sitter_typescript as tsts
from .javascript import JavaScriptPlugin, _arrow_params
from .base import _matches

_TS_LANGUAGE = Language(tsts.language_typescript())
_TS_PARSER = Parser(_TS_LANGUAGE)
_TSX_LANGUAGE = Language(tsts.language_tsx())
_TSX_PARSER = Parser(_TSX_LANGUAGE)


class TypeScriptPlugin(JavaScriptPlugin):
    """TypeScript plugin — inherits JS logic, overrides queries for TS grammar differences.

    Key differences from JS grammar:
    - Class names are 'type_identifier' nodes (not 'identifier')
    - Interface declarations use 'type_identifier' for names
    - Symbol usages must match both 'identifier' and 'type_identifier'
    """

    extensions = (".ts",)
    _lang = _TS_LANGUAGE
    _parser = _TS_PARSER

    def extract_skeleton(self, source: bytes) -> list[dict]:
        lang = self._get_language()
        tree = self._get_parser().parse(source)
        results = []

        # Top-level classes (TS uses type_identifier for class names)
        q = Query(lang, "(program (class_declaration name: (type_identifier) @name) @def)")
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "class",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": "",
            })

        # Methods inside classes (TS still uses property_identifier for method names,
        # but type_identifier for the containing class name)
        q = Query(lang, """
            (class_declaration
                name: (type_identifier) @class_name
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

        # Top-level function declarations (same as JS — uses identifier)
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

        # TypeScript interfaces
        q = Query(lang, "(program (interface_declaration name: (type_identifier) @name) @def)")
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "interface",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": "",
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
            "(class_declaration name: (type_identifier) @name) @def",
            "(export_statement (function_declaration name: (identifier) @name) @def)",
            "(export_statement (class_declaration name: (type_identifier) @name) @def)",
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

    def extract_symbol_usages(self, source: bytes, name: str) -> list[dict]:
        lang = self._get_language()
        tree = self._get_parser().parse(source)

        usages = []
        seen = set()

        # Match both plain identifiers and type identifiers (class names appear as both)
        for node_kind in ("identifier", "type_identifier"):
            q = Query(lang, f'(({node_kind}) @name (#eq? @name "{name}"))')
            for _, m in _matches(q, tree.root_node):
                node = m["name"]
                key = (node.start_point[0], node.start_point[1])
                if key not in seen:
                    seen.add(key)
                    usages.append({"line": node.start_point[0] + 1, "col": node.start_point[1]})

        usages.sort(key=lambda x: (x["line"], x["col"]))
        return usages


class TSXPlugin(TypeScriptPlugin):
    """TSX plugin — same as TypeScript but uses the tsx grammar."""

    extensions = (".tsx",)
    _lang = _TSX_LANGUAGE
    _parser = _TSX_PARSER
