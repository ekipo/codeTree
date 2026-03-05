from abc import ABC, abstractmethod

from tree_sitter import Query, QueryCursor


def _clean_doc(text: str) -> str:
    """Extract the first meaningful line from a doc comment."""
    lines = text.strip().splitlines()
    for line in lines:
        stripped = line.strip().lstrip("/*#!> ").rstrip("*/").strip()
        if stripped:
            return stripped
    return ""


def _fill_docs_from_siblings(results: list[dict], tree_root, lang, queries: list[str]) -> None:
    """Fill 'doc' field in skeleton items by checking prev_named_sibling of definition nodes.

    For multi-line doc comments (Go //, Rust ///), walks back through consecutive
    comment siblings with no blank lines between them to find the first line.
    For block comments (Java/JS /** */), the whole comment is a single node.
    """
    comment_types = ("comment", "line_comment", "block_comment")
    for q_str in queries:
        for _, m in _matches(Query(lang, q_str), tree_root):
            node = m["def"]
            name = m["name"].text.decode("utf-8", errors="replace")
            line = m["name"].start_point[0] + 1
            prev = node.prev_named_sibling
            doc = ""
            if prev and prev.type in comment_types:
                # Walk back through consecutive comment siblings to find the first one
                first_comment = prev
                while True:
                    pp = first_comment.prev_named_sibling
                    if pp and pp.type in comment_types:
                        # Consecutive = no blank lines between them
                        if pp.end_point[0] + 1 >= first_comment.start_point[0]:
                            first_comment = pp
                            continue
                    break
                doc = _clean_doc(first_comment.text.decode("utf-8", errors="replace"))
            for item in results:
                if item["name"] == name and item["line"] == line:
                    item["doc"] = doc
                    break


def _matches(query: Query, node) -> list[tuple[int, dict]]:
    """Run a query and return matches with captures unwrapped to single nodes.

    In tree-sitter 0.25.x, each capture value is a list of nodes.
    This helper unwraps to a single node (first element) for convenience.
    """
    cursor = QueryCursor(query)
    result = []
    for pattern_idx, match in cursor.matches(node):
        unwrapped = {
            name: nodes[0] if isinstance(nodes, list) and nodes else nodes
            for name, nodes in match.items()
        }
        result.append((pattern_idx, unwrapped))
    return result


class LanguagePlugin(ABC):
    """Abstract base class for all language plugins.

    To add a new language, copy `languages/_template.py`, implement all
    4 abstract methods, and register your plugin in `registry.py`.
    """

    extensions: tuple[str, ...]  # e.g. (".py",) or (".js", ".jsx")

    @abstractmethod
    def extract_skeleton(self, source: bytes) -> list[dict]:
        """Return top-level symbols in the file.

        Each dict must have keys:
          - type: "class" | "function" | "method" | "struct" | "interface" | "trait" | "enum" | "type"
          - name: str
          - line: int (1-based)
          - parent: str | None  (class name for methods, None for top-level)
          - params: str  (parameter list as string, e.g. "(a, b)" or "")
        """

    @abstractmethod
    def extract_symbol_source(self, source: bytes, name: str) -> tuple[str, int] | None:
        """Return (source_text, start_line) for a named function/class.

        Returns None if the symbol is not found.
        start_line is 1-based.
        """

    @abstractmethod
    def extract_calls_in_function(self, source: bytes, fn_name: str) -> list[str]:
        """Return sorted list of function/method names called inside fn_name.

        Returns empty list if fn_name is not found.
        """

    @abstractmethod
    def extract_symbol_usages(self, source: bytes, name: str) -> list[dict]:
        """Return all occurrences of name as an identifier.

        Each dict has keys:
          - line: int (1-based)
          - col: int (0-based)

        Includes definition sites. Use find_references in the indexer for
        cross-file usage.
        """

    @abstractmethod
    def extract_imports(self, source: bytes) -> list[dict]:
        """Return import/use statements in the file.

        Each dict has keys:
          - line: int (1-based)
          - text: str (raw import statement text, stripped of trailing newline)
        """

    def compute_complexity(self, source: bytes, fn_name: str) -> dict | None:
        """Return cyclomatic complexity breakdown for a function.

        Returns None if function not found.
        Returns dict with keys:
          - total: int (cyclomatic complexity)
          - breakdown: dict[str, int] (readable_type -> count)
        """
        return None

    def check_syntax(self, source: bytes) -> bool:
        """Return True if the source has syntax errors."""
        return False
