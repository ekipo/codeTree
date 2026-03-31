import sqlite3
import time
from pathlib import Path
from .models import SymbolNode, Edge

SCHEMA_VERSION = "1"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS files (
    file_path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    language TEXT,
    is_test INTEGER DEFAULT 0,
    indexed_at REAL
);

CREATE TABLE IF NOT EXISTS symbols (
    qualified_name TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    parent_qn TEXT,
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER,
    doc TEXT DEFAULT '',
    params TEXT DEFAULT '',
    is_test INTEGER DEFAULT 0,
    is_entry_point INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS edges (
    source_qn TEXT NOT NULL,
    target_qn TEXT NOT NULL,
    type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    PRIMARY KEY (source_qn, target_qn, type)
);

CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_qn);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_qn);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
"""


class GraphStore:
    def __init__(self, root: str):
        self._root = Path(root)
        self._db_path = self._root / ".codetree" / "graph.db"
        self._conn: sqlite3.Connection | None = None
        self._in_transaction = False

    def open(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA_SQL)
        # Set schema version if not exists
        cur = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'")
        if cur.fetchone() is None:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,),
            )
            self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def begin(self):
        """Begin a transaction. Commits are deferred until commit() is called."""
        self._in_transaction = True

    def commit(self):
        """Commit the current transaction."""
        if self._conn:
            self._conn.commit()
        self._in_transaction = False

    def _auto_commit(self):
        """Commit unless inside an explicit transaction."""
        if not self._in_transaction and self._conn:
            self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL query and return the cursor. Public API for queries."""
        if self._conn is None:
            self.open()
        return self._conn.execute(sql, params)

    # -- Meta --------------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        cur = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str):
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._auto_commit()

    # -- Files -------------------------------------------------------------

    def upsert_file(self, file_path: str, sha256: str, language: str, is_test: bool):
        self._conn.execute(
            "INSERT OR REPLACE INTO files (file_path, sha256, language, is_test, indexed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (file_path, sha256, language, int(is_test), time.time()),
        )
        self._auto_commit()

    def get_file(self, file_path: str) -> dict | None:
        cur = self._conn.execute(
            "SELECT file_path, sha256, language, is_test, indexed_at FROM files WHERE file_path=?",
            (file_path,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "file_path": row[0],
            "sha256": row[1],
            "language": row[2],
            "is_test": bool(row[3]),
            "indexed_at": row[4],
        }

    def delete_file(self, file_path: str):
        self._conn.execute("DELETE FROM files WHERE file_path=?", (file_path,))
        self._auto_commit()

    def all_files(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT file_path, sha256, language, is_test, indexed_at FROM files"
        )
        return [
            {"file_path": r[0], "sha256": r[1], "language": r[2], "is_test": bool(r[3]), "indexed_at": r[4]}
            for r in cur.fetchall()
        ]

    # -- Symbols -----------------------------------------------------------

    def upsert_symbol(self, sym: SymbolNode):
        self._conn.execute(
            "INSERT OR REPLACE INTO symbols "
            "(qualified_name, name, kind, parent_qn, file_path, start_line, end_line, "
            "doc, params, is_test, is_entry_point) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sym.qualified_name, sym.name, sym.kind, sym.parent_qn,
                sym.file_path, sym.start_line, sym.end_line,
                sym.doc, sym.params, int(sym.is_test), int(sym.is_entry_point),
            ),
        )
        self._auto_commit()

    def get_symbol(self, qualified_name: str) -> SymbolNode | None:
        cur = self._conn.execute(
            "SELECT qualified_name, name, kind, parent_qn, file_path, start_line, end_line, "
            "doc, params, is_test, is_entry_point FROM symbols WHERE qualified_name=?",
            (qualified_name,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return SymbolNode(
            qualified_name=row[0], name=row[1], kind=row[2], parent_qn=row[3],
            file_path=row[4], start_line=row[5], end_line=row[6],
            doc=row[7] or "", params=row[8] or "",
            is_test=bool(row[9]), is_entry_point=bool(row[10]),
        )

    def symbols_by_name(self, name: str) -> list[SymbolNode]:
        cur = self._conn.execute(
            "SELECT qualified_name, name, kind, parent_qn, file_path, start_line, end_line, "
            "doc, params, is_test, is_entry_point FROM symbols WHERE name=?",
            (name,),
        )
        return [
            SymbolNode(
                qualified_name=r[0], name=r[1], kind=r[2], parent_qn=r[3],
                file_path=r[4], start_line=r[5], end_line=r[6],
                doc=r[7] or "", params=r[8] or "",
                is_test=bool(r[9]), is_entry_point=bool(r[10]),
            )
            for r in cur.fetchall()
        ]

    def symbols_by_file(self, file_path: str) -> list[SymbolNode]:
        cur = self._conn.execute(
            "SELECT qualified_name, name, kind, parent_qn, file_path, start_line, end_line, "
            "doc, params, is_test, is_entry_point FROM symbols WHERE file_path=?",
            (file_path,),
        )
        return [
            SymbolNode(
                qualified_name=r[0], name=r[1], kind=r[2], parent_qn=r[3],
                file_path=r[4], start_line=r[5], end_line=r[6],
                doc=r[7] or "", params=r[8] or "",
                is_test=bool(r[9]), is_entry_point=bool(r[10]),
            )
            for r in cur.fetchall()
        ]

    def delete_symbols_for_file(self, file_path: str):
        self._conn.execute("DELETE FROM symbols WHERE file_path=?", (file_path,))
        self._auto_commit()

    # -- Edges -------------------------------------------------------------

    def upsert_edge(self, edge: Edge):
        self._conn.execute(
            "INSERT OR REPLACE INTO edges (source_qn, target_qn, type, weight) "
            "VALUES (?, ?, ?, ?)",
            (edge.source_qn, edge.target_qn, edge.type, edge.weight),
        )
        self._auto_commit()

    def edges_from(self, source_qn: str, edge_type: str | None = None) -> list[Edge]:
        if edge_type:
            cur = self._conn.execute(
                "SELECT source_qn, target_qn, type, weight FROM edges "
                "WHERE source_qn=? AND type=?",
                (source_qn, edge_type),
            )
        else:
            cur = self._conn.execute(
                "SELECT source_qn, target_qn, type, weight FROM edges WHERE source_qn=?",
                (source_qn,),
            )
        return [Edge(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]

    def edges_to(self, target_qn: str, edge_type: str | None = None) -> list[Edge]:
        if edge_type:
            cur = self._conn.execute(
                "SELECT source_qn, target_qn, type, weight FROM edges "
                "WHERE target_qn=? AND type=?",
                (target_qn, edge_type),
            )
        else:
            cur = self._conn.execute(
                "SELECT source_qn, target_qn, type, weight FROM edges WHERE target_qn=?",
                (target_qn,),
            )
        return [Edge(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]

    def delete_edges_for_file(self, file_path: str):
        prefix = file_path + "::"
        self._conn.execute(
            "DELETE FROM edges WHERE source_qn LIKE ? OR target_qn LIKE ?",
            (prefix + "%", prefix + "%"),
        )
        self._auto_commit()

    # -- Stats -------------------------------------------------------------

    def stats(self) -> dict:
        files = self._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        symbols = self._conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        edges = self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return {"files": files, "symbols": symbols, "edges": edges}
