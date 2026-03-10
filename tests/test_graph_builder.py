import pytest
import hashlib
import tempfile
from pathlib import Path
from codetree.graph.builder import GraphBuilder
from codetree.graph.store import GraphStore
from codetree.indexer import Indexer


@pytest.fixture
def repo_dir():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "calc.py").write_text(
            'class Calculator:\n'
            '    """A calculator."""\n'
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
        (p / "test_calc.py").write_text(
            'from calc import Calculator\n'
            'def test_add():\n'
            '    c = Calculator()\n'
            '    assert c.add(1, 2) == 3\n'
        )
        yield p


class TestGraphBuilder:
    def test_full_build(self, repo_dir):
        store = GraphStore(str(repo_dir))
        store.open()
        builder = GraphBuilder(str(repo_dir), store)
        result = builder.build()
        assert result["files_indexed"] > 0
        assert result["symbols_created"] > 0
        assert result["edges_created"] > 0
        store.close()

    def test_symbols_have_qualified_names(self, repo_dir):
        store = GraphStore(str(repo_dir))
        store.open()
        builder = GraphBuilder(str(repo_dir), store)
        builder.build()
        # Calculator class should have qualified name
        sym = store.get_symbol("calc.py::Calculator")
        assert sym is not None
        assert sym.kind == "class"
        # Method should include parent
        sym = store.get_symbol("calc.py::Calculator.add")
        assert sym is not None
        assert sym.kind == "method"
        store.close()

    def test_calls_edges_created(self, repo_dir):
        store = GraphStore(str(repo_dir))
        store.open()
        builder = GraphBuilder(str(repo_dir), store)
        builder.build()
        # main calls add
        edges = store.edges_from("main.py::main", edge_type="CALLS")
        callee_names = {e.target_qn.split("::")[-1] for e in edges}
        assert "add" in callee_names or "Calculator" in callee_names
        store.close()

    def test_contains_edges(self, repo_dir):
        store = GraphStore(str(repo_dir))
        store.open()
        builder = GraphBuilder(str(repo_dir), store)
        builder.build()
        edges = store.edges_from("calc.py::Calculator", edge_type="CONTAINS")
        child_names = {e.target_qn for e in edges}
        assert "calc.py::Calculator.add" in child_names
        assert "calc.py::Calculator.sub" in child_names
        store.close()

    def test_incremental_unchanged(self, repo_dir):
        store = GraphStore(str(repo_dir))
        store.open()
        builder = GraphBuilder(str(repo_dir), store)
        r1 = builder.build()
        r2 = builder.build()
        # Second build should skip unchanged files
        assert r2["files_skipped"] == r1["files_indexed"]
        assert r2["files_indexed"] == 0
        store.close()

    def test_incremental_changed_file(self, repo_dir):
        store = GraphStore(str(repo_dir))
        store.open()
        builder = GraphBuilder(str(repo_dir), store)
        builder.build()
        # Modify calc.py
        (repo_dir / "calc.py").write_text(
            'class Calculator:\n'
            '    def add(self, a, b):\n'
            '        return a + b\n'
            '    def multiply(self, a, b):\n'
            '        return a * b\n'
        )
        r2 = builder.build()
        assert r2["files_indexed"] == 1
        # sub should be gone, multiply should exist
        assert store.get_symbol("calc.py::Calculator.sub") is None
        assert store.get_symbol("calc.py::Calculator.multiply") is not None
        store.close()

    def test_deleted_file(self, repo_dir):
        store = GraphStore(str(repo_dir))
        store.open()
        builder = GraphBuilder(str(repo_dir), store)
        builder.build()
        assert store.get_symbol("main.py::main") is not None
        # Delete main.py
        (repo_dir / "main.py").unlink()
        builder.build()
        assert store.get_symbol("main.py::main") is None
        assert store.get_file("main.py") is None
        store.close()

    def test_test_file_detected(self, repo_dir):
        store = GraphStore(str(repo_dir))
        store.open()
        builder = GraphBuilder(str(repo_dir), store)
        builder.build()
        f = store.get_file("test_calc.py")
        assert f is not None
        assert f["is_test"] is True
        sym = store.get_symbol("test_calc.py::test_add")
        assert sym is not None
        assert sym.is_test is True
        store.close()
