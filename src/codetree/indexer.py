from pathlib import Path
from dataclasses import dataclass
from .queries import (
    extract_skeleton,
    extract_symbol_source,
    extract_calls_in_function,
    extract_symbol_usages,
)


@dataclass
class FileEntry:
    path: Path
    source: bytes
    skeleton: list[dict]
    mtime: float


class Indexer:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._index: dict[str, FileEntry] = {}

    @property
    def files(self) -> list[Path]:
        return [entry.path for entry in self._index.values()]

    def build(self, cached_mtimes: dict[str, float] | None = None):
        """Parse all .py files under root and build the index."""
        cached_mtimes = cached_mtimes or {}
        for py_file in self.root.rglob("*.py"):
            rel = str(py_file.relative_to(self.root))
            mtime = py_file.stat().st_mtime
            source = py_file.read_bytes()
            skeleton = extract_skeleton(source)
            self._index[rel] = FileEntry(
                path=py_file,
                source=source,
                skeleton=skeleton,
                mtime=mtime,
            )

    def get_skeleton(self, rel_path: str) -> list[dict]:
        entry = self._index.get(rel_path)
        if entry is None:
            return []
        return entry.skeleton

    def get_symbol(self, rel_path: str, symbol_name: str) -> tuple[str, int] | None:
        entry = self._index.get(rel_path)
        if entry is None:
            return None
        return extract_symbol_source(entry.source, symbol_name)

    def find_references(self, symbol_name: str) -> list[dict]:
        """Find all usages of symbol_name across all indexed files."""
        results = []
        for rel_path, entry in self._index.items():
            usages = extract_symbol_usages(entry.source, symbol_name)
            for u in usages:
                results.append({
                    "file": rel_path,
                    "line": u["line"],
                    "col": u["col"],
                })
        return results

    def get_call_graph(self, rel_path: str, function_name: str) -> dict:
        """Return what function_name calls and what calls function_name across repo."""
        entry = self._index.get(rel_path)
        calls = []
        if entry:
            calls = extract_calls_in_function(entry.source, function_name)

        callers = []
        for rp, e in self._index.items():
            usages = extract_symbol_usages(e.source, function_name)
            for u in usages:
                callers.append({"file": rp, "line": u["line"]})

        return {"calls": calls, "callers": callers}
