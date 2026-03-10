import pytest
import tempfile
from pathlib import Path
from codetree.graph.store import GraphStore
from codetree.graph.builder import GraphBuilder
from codetree.graph.queries import GraphQueries


@pytest.fixture
def built_graph():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "calc.py").write_text(
            'class Calculator:\n'
            '    """A calculator class."""\n'
            '    def add(self, a, b):\n'
            '        return a + b\n'
            '    def sub(self, a, b):\n'
            '        return a - b\n'
        )
        (p / "main.py").write_text(
            'from calc import Calculator\n'
            'def main():\n'
            '    c = Calculator()\n'
            '    print(c.add(1, 2))\n'
        )
        (p / "utils.py").write_text(
            'def add(a, b):\n'
            '    return a + b\n'
            'def helper():\n'
            '    pass\n'
        )
        (p / "test_calc.py").write_text(
            'from calc import Calculator\n'
            'def test_add():\n'
            '    c = Calculator()\n'
            '    assert c.add(1, 2) == 3\n'
        )
        store = GraphStore(str(p))
        store.open()
        builder = GraphBuilder(str(p), store)
        builder.build()
        queries = GraphQueries(store)
        yield queries, store, p
        store.close()


class TestRepositoryMap:
    def test_returns_languages(self, built_graph):
        queries, _, _ = built_graph
        result = queries.repository_map()
        assert "py" in result["languages"]

    def test_returns_entry_points(self, built_graph):
        queries, _, _ = built_graph
        result = queries.repository_map()
        assert any("main" in ep for ep in result["entry_points"])

    def test_returns_hotspots(self, built_graph):
        queries, _, _ = built_graph
        result = queries.repository_map()
        assert len(result["hotspots"]) > 0

    def test_returns_stats(self, built_graph):
        queries, _, _ = built_graph
        result = queries.repository_map()
        assert result["stats"]["files"] > 0
        assert result["stats"]["symbols"] > 0

    def test_max_items_limits_output(self, built_graph):
        queries, _, _ = built_graph
        result = queries.repository_map(max_items=2)
        assert len(result["hotspots"]) <= 2


class TestResolveSymbol:
    def test_exact_match(self, built_graph):
        queries, _, _ = built_graph
        results = queries.resolve_symbol("Calculator")
        assert len(results) >= 1
        assert results[0].name == "Calculator"

    def test_disambiguates_by_callers(self, built_graph):
        queries, _, _ = built_graph
        # "add" exists in both calc.py and utils.py
        results = queries.resolve_symbol("add")
        assert len(results) >= 2

    def test_kind_filter(self, built_graph):
        queries, _, _ = built_graph
        results = queries.resolve_symbol("add", kind="method")
        assert all(r.kind == "method" for r in results)

    def test_path_hint(self, built_graph):
        queries, _, _ = built_graph
        results = queries.resolve_symbol("add", path_hint="utils.py")
        assert results[0].file_path == "utils.py"

    def test_non_test_preferred(self, built_graph):
        queries, _, _ = built_graph
        results = queries.resolve_symbol("add")
        # Non-test results should come before test results
        non_test = [r for r in results if not r.is_test]
        if non_test:
            assert not results[0].is_test


class TestSearchGraph:
    def test_search_by_name(self, built_graph):
        queries, _, _ = built_graph
        result = queries.search_graph(query="calc")
        assert result["total"] > 0

    def test_search_by_kind(self, built_graph):
        queries, _, _ = built_graph
        result = queries.search_graph(kind="class")
        assert all(r["kind"] == "class" for r in result["results"])

    def test_search_by_file_pattern(self, built_graph):
        queries, _, _ = built_graph
        result = queries.search_graph(file_pattern="calc")
        assert all("calc" in r["file_path"] for r in result["results"])

    def test_search_pagination(self, built_graph):
        queries, _, _ = built_graph
        r1 = queries.search_graph(limit=2, offset=0)
        r2 = queries.search_graph(limit=2, offset=2)
        if r1["total"] > 2:
            assert r1["results"] != r2["results"]

    def test_search_by_min_degree(self, built_graph):
        queries, _, _ = built_graph
        result = queries.search_graph(min_degree=1)
        # All results should have at least 1 connection
        for r in result["results"]:
            assert r["in_degree"] + r["out_degree"] >= 1
