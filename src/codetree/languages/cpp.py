from tree_sitter import Language, Parser, Query
import tree_sitter_cpp as tscpp
from .c import CPlugin
from .base import _matches, _fill_docs_from_siblings

_LANGUAGE = Language(tscpp.language())
_PARSER = Parser(_LANGUAGE)


def _parse(source: bytes):
    return _PARSER.parse(source)


class CppPlugin(CPlugin):
    """C++ plugin — inherits C functionality, adds classes, namespaces, methods."""

    extensions = (".cpp", ".cc", ".cxx", ".hpp", ".hh")

    def _get_language(self):
        return _LANGUAGE

    def _get_parser(self):
        return _PARSER

    def extract_skeleton(self, source: bytes) -> list[dict]:
        lang = _LANGUAGE
        tree = _parse(source)
        results = []

        # Classes
        q = Query(lang, "(class_specifier name: (type_identifier) @name) @def")
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "class",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": "",
            })

        # Methods inside classes (function_definition in field_declaration_list)
        q = Query(lang, """
            (class_specifier
                name: (type_identifier) @class_name
                body: (field_declaration_list
                    (function_definition
                        declarator: (function_declarator
                            declarator: (field_identifier) @method_name
                            parameters: (parameter_list) @params))))
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "method",
                "name": m["method_name"].text.decode("utf-8", errors="replace"),
                "line": m["method_name"].start_point[0] + 1,
                "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        # Structs (C++ uses same struct_specifier as C)
        q = Query(lang, "(struct_specifier name: (type_identifier) @name body: (field_declaration_list)) @def")
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "struct",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": "",
            })

        # Top-level functions (translation_unit direct children)
        q = Query(lang, """
            (translation_unit
                (function_definition
                    declarator: (function_declarator
                        declarator: (identifier) @name
                        parameters: (parameter_list) @params)) @def)
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "function",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        # Functions inside namespaces
        q = Query(lang, """
            (namespace_definition
                body: (declaration_list
                    (function_definition
                        declarator: (function_declarator
                            declarator: (identifier) @name
                            parameters: (parameter_list) @params)) @def))
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "function",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        # Fill doc fields
        for item in results:
            item.setdefault("doc", "")
        _fill_docs_from_siblings(results, tree.root_node, lang, [
            "(class_specifier name: (type_identifier) @name) @def",
            "(struct_specifier name: (type_identifier) @name) @def",
            "(function_definition declarator: (function_declarator declarator: (identifier) @name)) @def",
        ])

        # Deduplicate
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
        lang = _LANGUAGE
        tree = _parse(source)

        # Functions (including namespace-scoped)
        q = Query(lang, "(function_definition declarator: (function_declarator declarator: (identifier) @name)) @def")
        for _, m in _matches(q, tree.root_node):
            if m["name"].text.decode("utf-8", errors="replace") == name:
                node = m["def"]
                return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"), node.start_point[0] + 1

        # Classes
        q = Query(lang, "(class_specifier name: (type_identifier) @name) @def")
        for _, m in _matches(q, tree.root_node):
            if m["name"].text.decode("utf-8", errors="replace") == name:
                node = m["def"]
                return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"), node.start_point[0] + 1

        # Structs
        q = Query(lang, "(struct_specifier name: (type_identifier) @name body: (field_declaration_list)) @def")
        for _, m in _matches(q, tree.root_node):
            if m["name"].text.decode("utf-8", errors="replace") == name:
                node = m["def"]
                return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"), node.start_point[0] + 1

        return None

    def extract_calls_in_function(self, source: bytes, fn_name: str) -> list[str]:
        lang = _LANGUAGE
        tree = _parse(source)
        fn_node = None
        q = Query(lang, "(function_definition declarator: (function_declarator declarator: [(identifier) @name (field_identifier) @name])) @def")
        for _, m in _matches(q, tree.root_node):
            if m["name"].text.decode("utf-8", errors="replace") == fn_name:
                fn_node = m["def"]
                break
        if fn_node is None:
            return []
        q = Query(lang, """
            (call_expression function: [
                (identifier) @called
                (field_expression field: (field_identifier) @called)
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
        for node_type in ("identifier", "type_identifier", "field_identifier", "namespace_identifier"):
            q = Query(_LANGUAGE, f'(({node_type}) @name (#eq? @name "{name}"))')
            for _, m in _matches(q, tree.root_node):
                node = m["name"]
                key = (node.start_point[0], node.start_point[1])
                if key not in seen:
                    seen.add(key)
                    usages.append({"line": node.start_point[0] + 1, "col": node.start_point[1]})
        usages.sort(key=lambda x: (x["line"], x["col"]))
        return usages

    def extract_imports(self, source: bytes) -> list[dict]:
        tree = _parse(source)
        results = []
        # #include statements
        q = Query(_LANGUAGE, "(translation_unit (preproc_include) @imp)")
        for _, m in _matches(q, tree.root_node):
            node = m["imp"]
            results.append({
                "line": node.start_point[0] + 1,
                "text": node.text.decode("utf-8", errors="replace").strip(),
            })
        # using declarations
        q = Query(_LANGUAGE, "(translation_unit (using_declaration) @imp)")
        for _, m in _matches(q, tree.root_node):
            node = m["imp"]
            results.append({
                "line": node.start_point[0] + 1,
                "text": node.text.decode("utf-8", errors="replace").strip(),
            })
        results.sort(key=lambda x: x["line"])
        return results

    def check_syntax(self, source: bytes) -> bool:
        return _parse(source).root_node.has_error
