from tree_sitter import Language, Parser, Query
import tree_sitter_c as tsc
from .base import LanguagePlugin, _matches, _fill_docs_from_siblings

_LANGUAGE = Language(tsc.language())
_PARSER = Parser(_LANGUAGE)


def _parse(source: bytes):
    return _PARSER.parse(source)


class CPlugin(LanguagePlugin):
    extensions = (".c", ".h")

    def _get_language(self):
        return _LANGUAGE

    def _get_parser(self):
        return _PARSER

    def extract_skeleton(self, source: bytes) -> list[dict]:
        tree = _parse(source)
        results = []

        # Named structs with body (struct Foo { ... })
        q = Query(_LANGUAGE, "(struct_specifier name: (type_identifier) @name body: (field_declaration_list)) @def")
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "struct",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": "",
            })

        # Typedef structs: typedef struct { ... } Name;
        q = Query(_LANGUAGE, "(type_definition declarator: (type_identifier) @name) @def")
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "struct",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": "",
            })

        # Functions
        q = Query(_LANGUAGE, """
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

        # Fill doc fields
        for item in results:
            item.setdefault("doc", "")
        _fill_docs_from_siblings(results, tree.root_node, _LANGUAGE, [
            "(function_definition declarator: (function_declarator declarator: (identifier) @name)) @def",
            "(struct_specifier name: (type_identifier) @name) @def",
            "(type_definition declarator: (type_identifier) @name) @def",
        ])

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
        tree = _parse(source)

        # Functions
        q = Query(_LANGUAGE, "(function_definition declarator: (function_declarator declarator: (identifier) @name)) @def")
        for _, m in _matches(q, tree.root_node):
            if m["name"].text.decode("utf-8", errors="replace") == name:
                node = m["def"]
                return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"), node.start_point[0] + 1

        # Structs
        q = Query(_LANGUAGE, "(struct_specifier name: (type_identifier) @name body: (field_declaration_list)) @def")
        for _, m in _matches(q, tree.root_node):
            if m["name"].text.decode("utf-8", errors="replace") == name:
                node = m["def"]
                return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"), node.start_point[0] + 1

        # Typedef structs
        q = Query(_LANGUAGE, "(type_definition declarator: (type_identifier) @name) @def")
        for _, m in _matches(q, tree.root_node):
            if m["name"].text.decode("utf-8", errors="replace") == name:
                node = m["def"]
                return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"), node.start_point[0] + 1

        return None

    def extract_calls_in_function(self, source: bytes, fn_name: str) -> list[str]:
        tree = _parse(source)
        fn_node = None
        q = Query(_LANGUAGE, "(function_definition declarator: (function_declarator declarator: (identifier) @name)) @def")
        for _, m in _matches(q, tree.root_node):
            if m["name"].text.decode("utf-8", errors="replace") == fn_name:
                fn_node = m["def"]
                break
        if fn_node is None:
            return []
        q = Query(_LANGUAGE, """
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

    def extract_imports(self, source: bytes) -> list[dict]:
        tree = _parse(source)
        results = []
        q = Query(_LANGUAGE, "(translation_unit (preproc_include) @imp)")
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
