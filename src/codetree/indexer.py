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
    _EXCLUDED_NAMES = {
        "main", "__init__", "__main__", "__new__", "__del__",
        "__str__", "__repr__", "__eq__", "__ne__", "__lt__",
        "__le__", "__gt__", "__ge__", "__hash__", "__bool__",
        "__len__", "__getitem__", "__setitem__", "__delitem__",
        "__iter__", "__next__", "__contains__", "__enter__",
        "__exit__", "__call__", "__get__", "__set__", "__delete__",
        "__add__", "__sub__", "__mul__", "__truediv__", "__floordiv__",
        "__mod__", "__pow__", "__and__", "__or__", "__xor__",
        "__lshift__", "__rshift__", "__neg__", "__pos__", "__abs__",
        "__invert__", "__iadd__", "__isub__", "__imul__",
        "__getattr__", "__setattr__", "__delattr__",
        "__class_getitem__", "__init_subclass__",
        "setup", "teardown", "setUp", "tearDown",
    }

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

    def find_dead_code(self, file_path: str | None = None) -> list[dict]:
        """Find symbols that are defined but never referenced elsewhere.

        Args:
            file_path: if given, only report dead symbols in this file.
        Returns:
            list of {"file": str, "name": str, "type": str, "line": int, "parent": str | None}
        """
        dead = []
        if file_path:
            files_to_check = {file_path: self._index[file_path]} if file_path in self._index else {}
        else:
            files_to_check = self._index

        for rel_path, entry in files_to_check.items():
            for item in entry.skeleton:
                name = item["name"]

                if name in self._EXCLUDED_NAMES:
                    continue
                if name.startswith("test_") or name.startswith("Test"):
                    continue
                if rel_path.endswith("__init__.py"):
                    continue

                refs = self.find_references(name)
                def_line = item["line"]
                external_refs = [
                    r for r in refs
                    if not (r["file"] == rel_path and r["line"] == def_line)
                ]

                if not external_refs:
                    dead.append({
                        "file": rel_path,
                        "name": name,
                        "type": item["type"],
                        "line": def_line,
                        "parent": item.get("parent"),
                    })
        return dead

    def get_blast_radius(self, file_path: str, symbol_name: str) -> dict:
        """Find all functions transitively affected by changes to a symbol.

        Returns:
            {"callers": [{"file", "name", "line", "depth"}, ...],
             "calls":   [{"file", "name", "line", "depth"}, ...]}
        """
        self._ensure_call_graph()

        target_key = f"{file_path}::{symbol_name}"

        def _bfs(graph: dict[str, set[str]], start: str) -> list[dict]:
            """BFS through graph, returning nodes with depth."""
            visited = {start}
            queue = [(start, 0)]
            results = []
            while queue:
                current, depth = queue.pop(0)
                neighbors = graph.get(current, set())
                for neighbor in neighbors:
                    if neighbor not in visited and not neighbor.startswith("?::"):
                        visited.add(neighbor)
                        parts = neighbor.split("::", 1)
                        n_file = parts[0]
                        n_name = parts[1] if len(parts) > 1 else neighbor
                        n_line = 0
                        if n_name in self._definitions:
                            for def_file, def_line in self._definitions[n_name]:
                                if def_file == n_file:
                                    n_line = def_line
                                    break
                        results.append({
                            "file": n_file,
                            "name": n_name,
                            "line": n_line,
                            "depth": depth + 1,
                        })
                        queue.append((neighbor, depth + 1))
            return results

        callers = _bfs(self._reverse_graph, target_key)
        calls = _bfs(self._call_graph, target_key)
        return {"callers": callers, "calls": calls}

    def get_ast(self, rel_path: str, symbol_name: str | None = None, max_depth: int = -1) -> str | None:
        """Return AST S-expression for a file or symbol.

        Returns None if file not found.
        """
        entry = self._index.get(rel_path)
        if entry is None:
            return None
        return entry.plugin.get_ast_sexp(
            entry.source, symbol_name=symbol_name, max_depth=max_depth
        )

    def search_symbols(self, query: str | None = None, type: str | None = None,
                       parent: str | None = None, has_doc: bool | None = None,
                       min_complexity: int | None = None,
                       language: str | None = None) -> list[dict]:
        """Search symbols across the repo with flexible filters.

        All parameters optional; combine for powerful filtering.
        Returns list of {"file", "name", "type", "line", "parent", "doc"}.
        """
        results = []
        for rel_path, entry in self._index.items():
            if language and entry.language != language:
                continue
            for item in entry.skeleton:
                if query and query.lower() not in item["name"].lower():
                    continue
                if type and item["type"] != type:
                    continue
                if parent:
                    item_parent = item.get("parent") or ""
                    if parent.lower() not in item_parent.lower():
                        continue
                if has_doc is not None:
                    doc = item.get("doc", "")
                    if has_doc and not doc:
                        continue
                    if not has_doc and doc:
                        continue
                if min_complexity is not None:
                    if item["type"] not in ("function", "method"):
                        continue
                    cx = entry.plugin.compute_complexity(entry.source, item["name"])
                    if cx is None or cx["total"] < min_complexity:
                        continue
                results.append({
                    "file": rel_path,
                    "name": item["name"],
                    "type": item["type"],
                    "line": item["line"],
                    "parent": item.get("parent"),
                    "doc": item.get("doc", ""),
                })
        return results

    def rank_symbols(self, top_n: int = 20, file_path: str | None = None) -> list[dict]:
        """Rank symbols by importance using PageRank on the reference graph.

        Args:
            top_n: number of top symbols to return (default 20)
            file_path: if given, only rank symbols in this file
        Returns:
            list of {"file", "name", "type", "line", "score"}, sorted by score descending.
        """
        # Collect all symbols as nodes
        nodes: list[tuple[str, str, str, int]] = []  # (file, name, type, line)
        for rel_path, entry in self._index.items():
            for item in entry.skeleton:
                nodes.append((rel_path, item["name"], item["type"], item["line"]))

        if not nodes:
            return []

        # Build symbol → index mapping
        node_keys = [(f, n) for f, n, _, _ in nodes]
        key_to_idx = {k: i for i, k in enumerate(node_keys)}
        n = len(nodes)

        # Build adjacency: for each symbol, find what references it
        # inbound[target_idx] = list of source_idx
        inbound: dict[int, list[int]] = {i: [] for i in range(n)}
        outbound_count: dict[int, int] = {i: 0 for i in range(n)}

        for target_idx, (t_file, t_name, t_type, t_line) in enumerate(nodes):
            refs = self.find_references(t_name)
            for ref in refs:
                # Skip self-references (definition site)
                if ref["file"] == t_file and ref["line"] == t_line:
                    continue
                # Find which symbol contains this reference
                ref_file = ref["file"]
                ref_line = ref["line"]
                entry = self._index.get(ref_file)
                if not entry:
                    continue
                # Find the enclosing symbol by checking skeleton items
                containing = None
                for item in reversed(entry.skeleton):
                    if item["line"] <= ref_line:
                        containing = (ref_file, item["name"])
                        break
                if containing and containing in key_to_idx:
                    src_idx = key_to_idx[containing]
                    inbound[target_idx].append(src_idx)
                    outbound_count[src_idx] = outbound_count.get(src_idx, 0) + 1

        # Run PageRank with dangling-node handling so scores sum to ~1.0
        d = 0.85
        rank = [1.0 / n] * n
        dangling = {i for i in range(n) if outbound_count[i] == 0}
        for _ in range(25):
            # Redistribute rank from dangling nodes uniformly
            dangling_sum = sum(rank[i] for i in dangling)
            new_rank = [(1.0 - d) / n + d * dangling_sum / n] * n
            for target_idx in range(n):
                for src_idx in inbound[target_idx]:
                    out = outbound_count[src_idx]
                    if out > 0:
                        new_rank[target_idx] += d * rank[src_idx] / out
            rank = new_rank

        # Build results
        results = []
        for i, (f, name, typ, line) in enumerate(nodes):
            if file_path and f != file_path:
                continue
            results.append({
                "file": f,
                "name": name,
                "type": typ,
                "line": line,
                "score": round(rank[i], 6),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_n]

    def detect_clones(self, file_path: str | None = None, min_lines: int = 5) -> list[dict]:
        """Find duplicate/near-duplicate functions across the repo.

        Uses AST normalization to detect Type 1 (exact) and Type 2 (renamed) clones.

        Args:
            file_path: if given, find clones of functions in this file.
            min_lines: minimum line count for a function to be considered.
        Returns:
            list of clone groups, each with "hash", "line_count", "functions".
        """
        import hashlib

        function_hashes: dict[str, list[dict]] = {}

        for rel_path, entry in self._index.items():
            for item in entry.skeleton:
                if item["type"] not in ("function", "method"):
                    continue
                result = entry.plugin.extract_symbol_source(entry.source, item["name"])
                if result is None:
                    continue
                src_text, src_line = result
                line_count = src_text.count("\n") + (0 if src_text.endswith("\n") else 1)
                if line_count < min_lines:
                    continue
                normalized = entry.plugin.normalize_source_for_clones(src_text.encode("utf-8"))
                h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                if h not in function_hashes:
                    function_hashes[h] = []
                function_hashes[h].append({
                    "file": rel_path,
                    "name": item["name"],
                    "line": item["line"],
                    "line_count": line_count,
                })

        clone_groups = []
        for h, functions in function_hashes.items():
            if len(functions) < 2:
                continue
            if file_path:
                if not any(f["file"] == file_path for f in functions):
                    continue
            clone_groups.append({
                "hash": h,
                "line_count": functions[0]["line_count"],
                "functions": functions,
            })

        return clone_groups
