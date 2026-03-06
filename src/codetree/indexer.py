from pathlib import Path
from dataclasses import dataclass
from .languages.base import LanguagePlugin
from .registry import get_plugin


@dataclass
class FileEntry:
    path: Path
    source: bytes
    skeleton: list[dict]
    mtime: float
    language: str
    plugin: LanguagePlugin
    has_errors: bool = False


class Indexer:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._index: dict[str, FileEntry] = {}
        self._definitions: dict[str, list[tuple[str, int]]] = {}
        self._call_graph: dict[str, set[str]] = {}
        self._reverse_graph: dict[str, set[str]] = {}
        self._call_graph_built: bool = False

    @property
    def files(self) -> list[Path]:
        return [entry.path for entry in self._index.values()]

    SKIP_DIRS = {
        ".venv", "venv", "env", ".env",
        "__pycache__", ".git", ".hg", ".svn",
        "node_modules", ".tox", ".mypy_cache",
        ".pytest_cache", "dist", "build",
    }

    def _should_skip(self, path: Path) -> bool:
        for part in path.parts:
            if part in self.SKIP_DIRS:
                return True
            if part.endswith(".egg-info"):
                return True
        return False

    def build(self, cached_mtimes: dict[str, float] | None = None):
        """Index all supported files under root, skipping non-project dirs.

        Files whose path+mtime appear in cached_mtimes are skipped;
        the caller injects them via inject_cached().
        """
        cached_mtimes = cached_mtimes or {}
        for candidate in self.root.rglob("*"):
            if candidate.is_symlink():
                continue
            if not candidate.is_file():
                continue
            plugin = get_plugin(candidate)
            if plugin is None:
                continue
            if self._should_skip(candidate.relative_to(self.root)):
                continue
            rel = str(candidate.relative_to(self.root))
            mtime = candidate.stat().st_mtime
            if cached_mtimes.get(rel) == mtime:
                continue
            source = candidate.read_bytes()
            skeleton = plugin.extract_skeleton(source)
            has_errors = plugin.check_syntax(source)
            self._index[rel] = FileEntry(
                path=candidate,
                source=source,
                skeleton=skeleton,
                mtime=mtime,
                language=candidate.suffix.lstrip("."),
                plugin=plugin,
                has_errors=has_errors,
            )

        # Build definition index from skeleton data
        self._definitions = {}
        for rel_path, entry in self._index.items():
            for item in entry.skeleton:
                name = item["name"]
                if name not in self._definitions:
                    self._definitions[name] = []
                self._definitions[name].append((rel_path, item["line"]))

    def inject_cached(self, rel_path: str, py_file: Path, source: bytes,
                      skeleton: list[dict], mtime: float):
        """Inject a pre-computed entry (from cache) without re-parsing."""
        self._call_graph_built = False   # invalidate so graph is rebuilt with new entry
        plugin = get_plugin(py_file)
        if plugin is None:
            return
        self._index[rel_path] = FileEntry(
            path=py_file,
            source=source,
            skeleton=skeleton,
            mtime=mtime,
            language=py_file.suffix.lstrip("."),
            plugin=plugin,
        )
        # Update definition index
        for item in skeleton:
            name = item["name"]
            if name not in self._definitions:
                self._definitions[name] = []
            self._definitions[name].append((rel_path, item["line"]))

    def get_skeleton(self, rel_path: str) -> list[dict]:
        entry = self._index.get(rel_path)
        return entry.skeleton if entry else []

    def get_symbol(self, rel_path: str, symbol_name: str) -> tuple[str, int] | None:
        entry = self._index.get(rel_path)
        if entry is None:
            return None
        return entry.plugin.extract_symbol_source(entry.source, symbol_name)

    def find_references(self, symbol_name: str) -> list[dict]:
        results = []
        for rel_path, entry in self._index.items():
            for u in entry.plugin.extract_symbol_usages(entry.source, symbol_name):
                results.append({"file": rel_path, "line": u["line"], "col": u["col"]})
        return results

    def get_call_graph(self, rel_path: str, function_name: str) -> dict:
        entry = self._index.get(rel_path)
        calls = entry.plugin.extract_calls_in_function(entry.source, function_name) if entry else []
        callers = []
        for rp, e in self._index.items():
            for u in e.plugin.extract_symbol_usages(e.source, function_name):
                callers.append({"file": rp, "line": u["line"]})
        return {"calls": calls, "callers": callers}

    def _ensure_call_graph(self):
        """Build repo-wide call graph lazily on first use."""
        if self._call_graph_built:
            return
        self._call_graph = {}
        self._reverse_graph = {}
        for rel_path, entry in self._index.items():
            for item in entry.skeleton:
                if item["type"] in ("function", "method"):
                    caller_key = f"{rel_path}::{item['name']}"
                    callees = entry.plugin.extract_calls_in_function(
                        entry.source, item["name"]
                    )
                    callee_keys = set()
                    for callee_name in callees:
                        # Resolve callee to its definition location(s)
                        if callee_name in self._definitions:
                            for def_file, _ in self._definitions[callee_name]:
                                callee_keys.add(f"{def_file}::{callee_name}")
                        else:
                            # External/unresolved — keep as bare name
                            callee_keys.add(f"?::{callee_name}")
                    self._call_graph[caller_key] = callee_keys
                    for ck in callee_keys:
                        if ck not in self._reverse_graph:
                            self._reverse_graph[ck] = set()
                        self._reverse_graph[ck].add(caller_key)
        self._call_graph_built = True
