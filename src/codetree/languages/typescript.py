from tree_sitter import Language, Parser, Query
import tree_sitter_typescript as tsts
from .javascript import JavaScriptPlugin
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

        results.sort(key=lambda x: x["line"])
        return results

    def extract_symbol_source(self, source: bytes, name: str) -> tuple[str, int] | None:
        lang = self._get_language()
        tree = self._get_parser().parse(source)

        # Functions use identifier; classes use type_identifier in TS grammar
        for node_type, name_field in [
            ("function_declaration", "identifier"),
            ("class_declaration", "type_identifier"),
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
