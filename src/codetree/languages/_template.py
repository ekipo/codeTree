# ============================================================
# HOW TO ADD A NEW LANGUAGE TO CODETREE
# ============================================================
#
# CHECKLIST — follow in order:
#
# 1. Install the grammar:
#       pip install tree-sitter-LANG
#    Add to pyproject.toml dependencies:
#       "tree-sitter-LANG>=0.23.0",
#
# 2. Copy this file:
#       cp src/codetree/languages/_template.py src/codetree/languages/LANG.py
#
# 3. Fill in every section marked TODO below
#
# 4. Register in src/codetree/registry.py:
#       from .languages.LANG import LANGPlugin
#       PLUGINS[".ext"] = LANGPlugin()
#
# 5. Copy and adapt tests:
#       cp tests/languages/test_python.py tests/languages/test_LANG.py
#    Replace the SAMPLE source with idiomatic code in your language.
#    Run: pytest tests/languages/test_LANG.py -v
#
# TIP: To see a file's node types, run:
#       python -c "
#       from tree_sitter import Language, Parser
#       import tree_sitter_LANG as tslang
#       L = Language(tslang.language())
#       p = Parser(L)
#       tree = p.parse(open('yourfile.ext','rb').read())
#       def show(n, i=0):
#           print(' '*i + n.type + ((' -> ' + repr(n.text.decode())) if not n.children else ''))
#           [show(c, i+2) for c in n.children]
#       show(tree.root_node)
#       "
#
# See docs/language-nodes.md for a cheatsheet of node types per language.
# ============================================================

from tree_sitter import Language, Parser, Query

# TODO: replace with your grammar import
# import tree_sitter_LANG as tslang
# _LANGUAGE = Language(tslang.language())
# _PARSER = Parser(_LANGUAGE)

from .base import LanguagePlugin, _matches
# Import this from base — do not copy


class TemplateLangPlugin(LanguagePlugin):
    # TODO: set your file extensions
    extensions = (".ext",)

    def extract_skeleton(self, source: bytes) -> list[dict]:
        """Return top-level symbols.

        Each result dict MUST have: type, name, line, parent, params.
        type values: "class" | "function" | "method" | "struct" | "interface"
        parent: class name for methods, None for top-level symbols
        params: parameter list as string e.g. "(a, b)" or ""

        TODO: write 2-3 tree-sitter queries:
          1. Top-level class/struct declarations
          2. Methods inside classes (capture class name as parent)
          3. Top-level functions

        Example (Python):
            q = Query(_LANGUAGE, "(module (class_definition name: (identifier) @name) @def)")
        """
        # tree = _PARSER.parse(source)
        results = []
        # TODO: add your queries
        results.sort(key=lambda x: x["line"])
        return results

    def extract_symbol_source(self, source: bytes, name: str) -> tuple[str, int] | None:
        """Return (source_text, start_line) for a named symbol.

        TODO: write queries for function/class node types,
        match against `name`, return the node's text and start line.

        The node's byte range gives you the exact source:
            text = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            line = node.start_point[0] + 1  # convert 0-based to 1-based
        """
        # tree = _PARSER.parse(source)
        return None

    def extract_calls_in_function(self, source: bytes, fn_name: str) -> list[str]:
        """Return sorted list of function/method names called inside fn_name.

        TODO:
          Step 1 — Find the function node by name (same query as extract_symbol_source)
          Step 2 — Query call_expression nodes inside that function node
          Step 3 — Capture called function names (usually (identifier) or method name)

        Example (JavaScript):
            q = Query(_LANGUAGE, '''
                (call_expression function: [
                    (identifier) @called
                    (member_expression property: (property_identifier) @called)
                ])
            ''')
        """
        # tree = _PARSER.parse(source)
        return []

    def extract_symbol_usages(self, source: bytes, name: str) -> list[dict]:
        """Return all occurrences of name as an identifier.

        In most languages, identifiers are simply `(identifier)` nodes.
        Use the #eq? predicate to filter by name at the query level (faster
        than Python-level filtering for large files).

        This query works for Python, JavaScript, Go, Rust, Java:
            q = Query(_LANGUAGE, f'((identifier) @name (#eq? @name "{name}"))')

        Each result dict: {"line": int, "col": int}  (both 1-based and 0-based respectively)
        """
        # tree = _PARSER.parse(source)
        return []
