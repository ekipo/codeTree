import pytest
import tempfile
from pathlib import Path
from codetree.indexer import Indexer
from codetree.graph.dataflow import extract_dataflow, extract_taint_paths


@pytest.fixture
def py_indexer():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "app.py").write_text(
            'def process(request):\n'
            '    user_input = request.get("name")\n'
            '    cleaned = sanitize(user_input)\n'
            '    query = f"SELECT * FROM users WHERE name = {cleaned}"\n'
            '    db.execute(query)\n'
        )
        (p / "unsafe.py").write_text(
            'def handle(request):\n'
            '    data = request.get("id")\n'
            '    db.execute(f"DELETE FROM users WHERE id = {data}")\n'
        )
        (p / "simple.py").write_text(
            'def add(a, b):\n'
            '    result = a + b\n'
            '    return result\n'
        )
        idx = Indexer(str(p))
        idx.build()
        yield idx, p


class TestDataflow:
    def test_tracks_assignment_chain(self, py_indexer):
        idx, _ = py_indexer
        entry = idx._index["app.py"]
        result = extract_dataflow(entry.plugin, entry.source, "process")
        assert result is not None
        # user_input depends on request
        var_names = {v["name"] for v in result["variables"]}
        assert "user_input" in var_names
        assert "cleaned" in var_names
        assert "query" in var_names

    def test_dependency_edges(self, py_indexer):
        idx, _ = py_indexer
        entry = idx._index["app.py"]
        result = extract_dataflow(entry.plugin, entry.source, "process")
        # cleaned depends on user_input
        cleaned = next(v for v in result["variables"] if v["name"] == "cleaned")
        assert "user_input" in cleaned["depends_on"]

    def test_identifies_sinks(self, py_indexer):
        idx, _ = py_indexer
        entry = idx._index["app.py"]
        result = extract_dataflow(entry.plugin, entry.source, "process")
        sink_exprs = [s["expr"] for s in result["sinks"]]
        assert any("execute" in s for s in sink_exprs)

    def test_simple_function(self, py_indexer):
        idx, _ = py_indexer
        entry = idx._index["simple.py"]
        result = extract_dataflow(entry.plugin, entry.source, "add")
        assert result is not None
        var_names = {v["name"] for v in result["variables"]}
        assert "result" in var_names

    def test_function_not_found(self, py_indexer):
        idx, _ = py_indexer
        entry = idx._index["simple.py"]
        result = extract_dataflow(entry.plugin, entry.source, "nonexistent")
        assert result is None


class TestTaintPaths:
    def test_safe_path_with_sanitizer(self, py_indexer):
        idx, _ = py_indexer
        entry = idx._index["app.py"]
        result = extract_taint_paths(entry.plugin, entry.source, "process")
        # Has a sanitize() call in the chain, so should be SAFE
        safe_paths = [p for p in result["paths"] if p["verdict"] == "SAFE"]
        assert len(safe_paths) > 0

    def test_unsafe_path_without_sanitizer(self, py_indexer):
        idx, _ = py_indexer
        entry = idx._index["unsafe.py"]
        result = extract_taint_paths(entry.plugin, entry.source, "handle")
        # No sanitizer between request.get and db.execute
        unsafe_paths = [p for p in result["paths"] if p["verdict"] == "UNSAFE"]
        assert len(unsafe_paths) > 0

    def test_no_taint_in_simple_function(self, py_indexer):
        idx, _ = py_indexer
        entry = idx._index["simple.py"]
        result = extract_taint_paths(entry.plugin, entry.source, "add")
        # No external sources or dangerous sinks
        assert len(result["paths"]) == 0
