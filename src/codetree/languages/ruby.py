from tree_sitter import Language, Parser, Query
import tree_sitter_ruby as tsruby
from .base import LanguagePlugin, _matches, _fill_docs_from_siblings

_LANGUAGE = Language(tsruby.language())
_PARSER = Parser(_LANGUAGE)


def _parse(source: bytes):
    return _PARSER.parse(source)


class RubyPlugin(LanguagePlugin):
    extensions = (".rb",)

    def extract_skeleton(self, source: bytes) -> list[dict]:
        tree = _parse(source)
        results = []

        # Classes
        q = Query(_LANGUAGE, "(program (class name: (constant) @name) @def)")
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "class",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": "",
            })

        # Modules (treated as class for skeleton purposes)
        q = Query(_LANGUAGE, "(program (module name: (constant) @name) @def)")
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "class",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": "",
            })

        # Instance methods inside classes (with params)
        q = Query(_LANGUAGE, """
            (class
                name: (constant) @class_name
                (body_statement
                    (method
                        name: (identifier) @method_name
                        parameters: (method_parameters) @params)))
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "method",
                "name": m["method_name"].text.decode("utf-8", errors="replace"),
                "line": m["method_name"].start_point[0] + 1,
                "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        # Instance methods inside classes (no params)
        q = Query(_LANGUAGE, """
            (class
                name: (constant) @class_name
                (body_statement
                    (method
                        name: (identifier) @method_name) @mdef))
        """)
        for _, m in _matches(q, tree.root_node):
            method_node = m["mdef"]
            # Skip if it has params (already matched above)
            if not any(child.type == "method_parameters" for child in method_node.children):
                results.append({
                    "type": "method",
                    "name": m["method_name"].text.decode("utf-8", errors="replace"),
                    "line": m["method_name"].start_point[0] + 1,
                    "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                    "params": "",
                })

        # Singleton methods in classes (def self.foo) — with params
        q = Query(_LANGUAGE, """
            (class
                name: (constant) @class_name
                (body_statement
                    (singleton_method
                        name: (identifier) @method_name
                        parameters: (method_parameters) @params)))
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "method",
                "name": m["method_name"].text.decode("utf-8", errors="replace"),
                "line": m["method_name"].start_point[0] + 1,
                "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        # Singleton methods in classes — no params
        q = Query(_LANGUAGE, """
            (class
                name: (constant) @class_name
                (body_statement
                    (singleton_method
                        name: (identifier) @method_name) @mdef))
        """)
        for _, m in _matches(q, tree.root_node):
            method_node = m["mdef"]
            if not any(child.type == "method_parameters" for child in method_node.children):
                results.append({
                    "type": "method",
                    "name": m["method_name"].text.decode("utf-8", errors="replace"),
                    "line": m["method_name"].start_point[0] + 1,
                    "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                    "params": "",
                })

        # Singleton methods in modules — with params
        q = Query(_LANGUAGE, """
            (module
                name: (constant) @class_name
                (body_statement
                    (singleton_method
                        name: (identifier) @method_name
                        parameters: (method_parameters) @params)))
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "method",
                "name": m["method_name"].text.decode("utf-8", errors="replace"),
                "line": m["method_name"].start_point[0] + 1,
                "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        # Singleton methods in modules — no params
        q = Query(_LANGUAGE, """
            (module
                name: (constant) @class_name
                (body_statement
                    (singleton_method
                        name: (identifier) @method_name) @mdef))
        """)
        for _, m in _matches(q, tree.root_node):
            method_node = m["mdef"]
            if not any(child.type == "method_parameters" for child in method_node.children):
                results.append({
                    "type": "method",
                    "name": m["method_name"].text.decode("utf-8", errors="replace"),
                    "line": m["method_name"].start_point[0] + 1,
                    "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                    "params": "",
                })

        # Instance methods in modules — with params
        q = Query(_LANGUAGE, """
            (module
                name: (constant) @class_name
                (body_statement
                    (method
                        name: (identifier) @method_name
                        parameters: (method_parameters) @params)))
        """)
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "method",
                "name": m["method_name"].text.decode("utf-8", errors="replace"),
                "line": m["method_name"].start_point[0] + 1,
                "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        # Instance methods in modules — no params
        q = Query(_LANGUAGE, """
            (module
                name: (constant) @class_name
                (body_statement
                    (method
                        name: (identifier) @method_name) @mdef))
        """)
        for _, m in _matches(q, tree.root_node):
            method_node = m["mdef"]
            if not any(child.type == "method_parameters" for child in method_node.children):
                results.append({
                    "type": "method",
                    "name": m["method_name"].text.decode("utf-8", errors="replace"),
                    "line": m["method_name"].start_point[0] + 1,
                    "parent": m["class_name"].text.decode("utf-8", errors="replace"),
                    "params": "",
                })

        # Top-level functions (method at program level) — with params
        q = Query(_LANGUAGE, "(program (method name: (identifier) @name parameters: (method_parameters) @params) @def)")
        for _, m in _matches(q, tree.root_node):
            results.append({
                "type": "function",
                "name": m["name"].text.decode("utf-8", errors="replace"),
                "line": m["name"].start_point[0] + 1,
                "parent": None,
                "params": m["params"].text.decode("utf-8", errors="replace"),
            })

        # Top-level functions — no params
        q = Query(_LANGUAGE, "(program (method name: (identifier) @name) @def)")
        for _, m in _matches(q, tree.root_node):
            method_node = m["def"]
            if not any(child.type == "method_parameters" for child in method_node.children):
                results.append({
                    "type": "function",
                    "name": m["name"].text.decode("utf-8", errors="replace"),
                    "line": m["name"].start_point[0] + 1,
                    "parent": None,
                    "params": "",
                })

        # Fill doc fields
        for item in results:
            item.setdefault("doc", "")
        _fill_docs_from_siblings(results, tree.root_node, _LANGUAGE, [
            "(program (class name: (constant) @name) @def)",
            "(program (module name: (constant) @name) @def)",
            "(program (method name: (identifier) @name) @def)",
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
        tree = _parse(source)

        # Classes and modules
        for q_str in [
            "(class name: (constant) @name) @def",
            "(module name: (constant) @name) @def",
        ]:
            for _, m in _matches(Query(_LANGUAGE, q_str), tree.root_node):
                if m["name"].text.decode("utf-8", errors="replace") == name:
                    node = m["def"]
                    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"), node.start_point[0] + 1

        # Methods (instance and singleton)
        for q_str in [
            "(method name: (identifier) @name) @def",
            "(singleton_method name: (identifier) @name) @def",
        ]:
            for _, m in _matches(Query(_LANGUAGE, q_str), tree.root_node):
                if m["name"].text.decode("utf-8", errors="replace") == name:
                    node = m["def"]
                    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"), node.start_point[0] + 1

        return None

    def extract_calls_in_function(self, source: bytes, fn_name: str) -> list[str]:
        tree = _parse(source)
        fn_node = None
        for q_str in [
            "(method name: (identifier) @name) @def",
            "(singleton_method name: (identifier) @name) @def",
        ]:
            for _, m in _matches(Query(_LANGUAGE, q_str), tree.root_node):
                if m["name"].text.decode("utf-8", errors="replace") == fn_name:
                    fn_node = m["def"]
                    break
            if fn_node:
                break
        if fn_node is None:
            return []

        q = Query(_LANGUAGE, "(call method: (identifier) @called)")
        calls = set()
        for _, m in _matches(q, fn_node):
            calls.add(m["called"].text.decode("utf-8", errors="replace"))
        return sorted(calls)

    def extract_symbol_usages(self, source: bytes, name: str) -> list[dict]:
        tree = _parse(source)
        usages = []
        seen = set()
        for node_type in ("identifier", "constant"):
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
        q = Query(_LANGUAGE, "(program (call method: (identifier) @method arguments: (argument_list (string) @path)) @imp)")
        for _, m in _matches(q, tree.root_node):
            method = m["method"].text.decode("utf-8", errors="replace")
            if method in ("require", "require_relative"):
                node = m["imp"]
                results.append({
                    "line": node.start_point[0] + 1,
                    "text": node.text.decode("utf-8", errors="replace").strip(),
                })
        results.sort(key=lambda x: x["line"])
        return results

    def check_syntax(self, source: bytes) -> bool:
        return _parse(source).root_node.has_error
