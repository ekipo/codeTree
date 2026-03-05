from abc import ABC, abstractmethod

from tree_sitter import Query, QueryCursor


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
          - type: "class" | "function" | "method" | "struct" | "interface"
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
