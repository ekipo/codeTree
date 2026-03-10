from pathlib import Path
from .store import GraphStore
from .models import SymbolNode


class GraphQueries:
    def __init__(self, store: GraphStore):
        self._store = store

    def repository_map(self, include: list[str] | None = None, max_items: int = 5) -> dict:
        """Return a compact repo overview for agent onboarding."""
        conn = self._store._conn

        # Languages
        cur = conn.execute("SELECT language, COUNT(*) FROM files GROUP BY language ORDER BY COUNT(*) DESC")
        languages = {r[0]: r[1] for r in cur.fetchall() if r[0]}

        # Major paths (most common directory prefixes)
        cur = conn.execute("SELECT file_path FROM files")
        all_paths = [r[0] for r in cur.fetchall()]
        dir_counts: dict[str, int] = {}
        for fp in all_paths:
            parts = Path(fp).parts
            if len(parts) > 1:
                d = str(Path(*parts[:-1])) + "/"
                dir_counts[d] = dir_counts.get(d, 0) + 1
        major_paths = sorted(dir_counts, key=dir_counts.get, reverse=True)[:max_items]

        # Entry points
        cur = conn.execute(
            "SELECT qualified_name, file_path, start_line FROM symbols "
            "WHERE is_entry_point=1 LIMIT ?",
            (max_items,),
        )
        entry_points = [r[0] for r in cur.fetchall()]

        # Hotspots (most connected symbols)
        cur = conn.execute(
            "SELECT s.qualified_name, s.name, s.kind, s.file_path, s.start_line, "
            "COALESCE(ein.cnt, 0) + COALESCE(eout.cnt, 0) as degree "
            "FROM symbols s "
            "LEFT JOIN (SELECT target_qn, COUNT(*) as cnt FROM edges GROUP BY target_qn) ein "
            "ON s.qualified_name = ein.target_qn "
            "LEFT JOIN (SELECT source_qn, COUNT(*) as cnt FROM edges GROUP BY source_qn) eout "
            "ON s.qualified_name = eout.source_qn "
            "WHERE s.is_test = 0 "
            "ORDER BY degree DESC LIMIT ?",
            (max_items,),
        )
        hotspots = [
            {"qualified_name": r[0], "name": r[1], "kind": r[2], "file": r[3], "line": r[4], "degree": r[5]}
            for r in cur.fetchall()
        ]

        # Start here: entry points first, then hotspots, non-test only
        start_here = entry_points[:max_items]
        if len(start_here) < max_items:
            for h in hotspots:
                if h["qualified_name"] not in start_here and len(start_here) < max_items:
                    start_here.append(h["qualified_name"])

        # Test roots
        cur = conn.execute("SELECT DISTINCT file_path FROM files WHERE is_test=1")
        test_files = [r[0] for r in cur.fetchall()]
        test_dirs = set()
        for tf in test_files:
            parts = Path(tf).parts
            if len(parts) > 1:
                test_dirs.add(str(Path(*parts[:-1])) + "/")
            else:
                test_dirs.add("./")
        test_roots = sorted(test_dirs)[:max_items]

        stats = self._store.stats()

        return {
            "languages": languages,
            "major_paths": major_paths,
            "entry_points": entry_points,
            "hotspots": hotspots,
            "start_here": start_here,
            "test_roots": test_roots,
            "stats": stats,
        }

    def resolve_symbol(self, query: str, kind: str | None = None,
                       path_hint: str | None = None, limit: int = 10) -> list[SymbolNode]:
        """Disambiguate a short symbol name into ranked qualified matches."""
        conn = self._store._conn

        # Find all symbols matching the name (case-insensitive)
        cur = conn.execute(
            "SELECT qualified_name, name, kind, parent_qn, file_path, start_line, end_line, "
            "doc, params, is_test, is_entry_point FROM symbols WHERE name = ? COLLATE NOCASE",
            (query,),
        )
        candidates = [
            SymbolNode(
                qualified_name=r[0], name=r[1], kind=r[2], parent_qn=r[3],
                file_path=r[4], start_line=r[5], end_line=r[6],
                doc=r[7] or "", params=r[8] or "",
                is_test=bool(r[9]), is_entry_point=bool(r[10]),
            )
            for r in cur.fetchall()
        ]

        # Apply kind filter
        if kind:
            candidates = [c for c in candidates if c.kind == kind]

        # Rank candidates
        def score(sym: SymbolNode) -> tuple:
            # Higher is better for each component
            path_match = 1 if path_hint and path_hint in sym.file_path else 0
            not_test = 0 if sym.is_test else 1
            is_entry = 1 if sym.is_entry_point else 0
            # Count inbound edges as centrality proxy
            inbound = len(self._store.edges_to(sym.qualified_name))
            return (path_match, not_test, is_entry, inbound, sym.qualified_name)

        candidates.sort(key=score, reverse=True)
        return candidates[:limit]

    def search_graph(self, query: str | None = None, kind: str | None = None,
                     file_pattern: str | None = None, relationship: str | None = None,
                     direction: str | None = None, min_degree: int | None = None,
                     max_degree: int | None = None, limit: int = 10, offset: int = 0) -> dict:
        """Structured graph search with filters and pagination."""
        conn = self._store._conn

        # Build WHERE clause
        conditions = []
        params = []

        if query:
            conditions.append("s.name LIKE ?")
            params.append(f"%{query}%")
        if kind:
            conditions.append("s.kind = ?")
            params.append(kind)
        if file_pattern:
            conditions.append("s.file_path LIKE ?")
            params.append(f"%{file_pattern}%")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Get symbols with degree info
        sql = (
            "SELECT s.qualified_name, s.name, s.kind, s.file_path, s.start_line, s.end_line, "
            "COALESCE(ein.cnt, 0) as in_degree, COALESCE(eout.cnt, 0) as out_degree "
            "FROM symbols s "
            "LEFT JOIN (SELECT target_qn, COUNT(*) as cnt FROM edges GROUP BY target_qn) ein "
            "ON s.qualified_name = ein.target_qn "
            "LEFT JOIN (SELECT source_qn, COUNT(*) as cnt FROM edges GROUP BY source_qn) eout "
            "ON s.qualified_name = eout.source_qn "
            f"{where} "
            "ORDER BY (COALESCE(ein.cnt, 0) + COALESCE(eout.cnt, 0)) DESC"
        )

        cur = conn.execute(sql, params)
        all_results = cur.fetchall()

        # Apply degree filters in Python (simpler than SQL)
        filtered = []
        for r in all_results:
            in_deg, out_deg = r[6], r[7]
            total_deg = in_deg + out_deg
            if min_degree is not None and total_deg < min_degree:
                continue
            if max_degree is not None and total_deg > max_degree:
                continue
            if relationship and direction:
                # Check if symbol has specific relationship in given direction
                if direction == "inbound":
                    edges = self._store.edges_to(r[0], edge_type=relationship)
                else:
                    edges = self._store.edges_from(r[0], edge_type=relationship)
                if not edges:
                    continue
            filtered.append({
                "qualified_name": r[0],
                "name": r[1],
                "kind": r[2],
                "file_path": r[3],
                "start_line": r[4],
                "end_line": r[5],
                "in_degree": in_deg,
                "out_degree": out_deg,
            })

        total = len(filtered)
        page = filtered[offset:offset + limit]

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
            "results": page,
        }
