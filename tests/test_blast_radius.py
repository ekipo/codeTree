"""Tests for blast radius / impact analysis."""
import pytest
from codetree.indexer import Indexer


# ─── Call graph infrastructure ────────────────────────────────────────────────

class TestCallGraph:

    def test_call_graph_built(self, sample_repo):
        indexer = Indexer(str(sample_repo))
        indexer.build()
        indexer._ensure_call_graph()
        assert indexer._call_graph_built is True

    def test_forward_graph_has_calls(self, sample_repo):
        indexer = Indexer(str(sample_repo))
        indexer.build()
        indexer._ensure_call_graph()
        # helper() calls Calculator() and calc.add()
        key = "calculator.py::helper"
        assert key in indexer._call_graph
        callees = indexer._call_graph[key]
        assert any("add" in c for c in callees)

    def test_reverse_graph_has_callers(self, sample_repo):
        indexer = Indexer(str(sample_repo))
        indexer.build()
        indexer._ensure_call_graph()
        # add is called by helper
        # Find any reverse graph key containing "add"
        add_keys = [k for k in indexer._reverse_graph if "add" in k]
        assert len(add_keys) >= 1
        callers = set()
        for k in add_keys:
            callers.update(indexer._reverse_graph[k])
        assert any("helper" in c for c in callers)

    def test_idempotent(self, sample_repo):
        indexer = Indexer(str(sample_repo))
        indexer.build()
        indexer._ensure_call_graph()
        graph1 = dict(indexer._call_graph)
        indexer._ensure_call_graph()
        graph2 = dict(indexer._call_graph)
        assert graph1 == graph2

    def test_empty_repo(self, tmp_path):
        (tmp_path / "empty.py").write_text("x = 1\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        indexer._ensure_call_graph()
        assert indexer._call_graph_built is True
