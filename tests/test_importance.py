"""Tests for symbol importance ranking."""
import pytest
from codetree.indexer import Indexer
from codetree.server import create_server


def _tool(mcp, name):
    return mcp.local_provider._components[f"tool:{name}@"].fn


# ─── PageRank (indexer) ─────────────────────────────────────────────────────

class TestSymbolImportance:

    def test_heavily_used_ranks_higher(self, tmp_path):
        (tmp_path / "core.py").write_text("def base(): return 1\n")
        (tmp_path / "a.py").write_text("from core import base\ndef a(): return base()\n")
        (tmp_path / "b.py").write_text("from core import base\ndef b(): return base()\n")
        (tmp_path / "c.py").write_text("from core import base\ndef c(): return base()\n")
        (tmp_path / "leaf.py").write_text("def unused(): return 42\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        ranked = indexer.rank_symbols()
        names = [r["name"] for r in ranked]
        # base is referenced by 3 files, should rank higher than unused
        assert names.index("base") < names.index("unused")

    def test_returns_file_and_line(self, tmp_path):
        (tmp_path / "app.py").write_text("def foo(): pass\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        ranked = indexer.rank_symbols()
        assert len(ranked) >= 1
        item = ranked[0]
        assert "file" in item
        assert "name" in item
        assert "line" in item
        assert "type" in item
        assert "score" in item

    def test_top_n_parameter(self, tmp_path):
        (tmp_path / "app.py").write_text("def foo(): pass\ndef bar(): pass\ndef baz(): pass\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        ranked = indexer.rank_symbols(top_n=2)
        assert len(ranked) <= 2

    def test_file_scope(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo(): pass\n")
        (tmp_path / "b.py").write_text("def bar(): pass\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        ranked = indexer.rank_symbols(file_path="a.py")
        files = {r["file"] for r in ranked}
        assert files == {"a.py"}

    def test_empty_repo(self, tmp_path):
        (tmp_path / "empty.py").write_text("x = 1\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        ranked = indexer.rank_symbols()
        assert ranked == []

    def test_class_ranks_high_when_used(self, sample_repo):
        indexer = Indexer(str(sample_repo))
        indexer.build()
        ranked = indexer.rank_symbols()
        names = [r["name"] for r in ranked]
        # Calculator is used in both files, should be near top
        assert "Calculator" in names[:5]

    def test_scores_sum_roughly_to_one(self, sample_repo):
        indexer = Indexer(str(sample_repo))
        indexer.build()
        ranked = indexer.rank_symbols(top_n=100)
        total = sum(r["score"] for r in ranked)
        # PageRank scores should sum to ~1.0 (within rounding)
        assert abs(total - 1.0) < 0.1


# ─── MCP tool: rank_symbols ─────────────────────────────────────────────────

class TestRankSymbolsTool:

    def test_returns_ranked_list(self, sample_repo):
        fn = _tool(create_server(str(sample_repo)), "rank_symbols")
        result = fn()
        assert "Calculator" in result
        assert "score" in result.lower() or "importance" in result.lower()

    def test_top_n(self, sample_repo):
        fn = _tool(create_server(str(sample_repo)), "rank_symbols")
        result = fn(top_n=2)
        # Should have at most 2 entries
        lines = [l for l in result.strip().split("\n") if l.strip().startswith(("1.", "2.", "3."))]
        assert len(lines) <= 2

    def test_file_scope(self, sample_repo):
        fn = _tool(create_server(str(sample_repo)), "rank_symbols")
        result = fn(file_path="calculator.py")
        assert "calculator.py" in result
        assert "main.py" not in result

    def test_empty_repo(self, tmp_path):
        (tmp_path / "empty.py").write_text("x = 1\n")
        fn = _tool(create_server(str(tmp_path)), "rank_symbols")
        result = fn()
        assert "no symbols" in result.lower()

    def test_shows_file_and_line(self, sample_repo):
        fn = _tool(create_server(str(sample_repo)), "rank_symbols")
        result = fn()
        assert "line" in result.lower() or ":" in result
