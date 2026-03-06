"""Tests for variable listing in functions."""
import pytest
from codetree.indexer import Indexer
from codetree.languages.python import PythonPlugin
from codetree.server import create_server


def _tool(mcp, name):
    return mcp.local_provider._components[f"tool:{name}@"].fn


PY = PythonPlugin()


# ─── Python variable extraction ─────────────────────────────────────────────

class TestPythonVariables:

    def test_simple_assignments(self):
        src = b"def foo():\n    x = 1\n    y = 'hello'\n    return x + y\n"
        result = PY.extract_variables(src, "foo")
        names = [v["name"] for v in result]
        assert "x" in names
        assert "y" in names

    def test_annotated_assignment(self):
        src = b"def foo():\n    x: int = 42\n    return x\n"
        result = PY.extract_variables(src, "foo")
        item = next(v for v in result if v["name"] == "x")
        assert item["type"] == "int"

    def test_parameters_included(self):
        src = b"def foo(a, b, c=1):\n    return a + b + c\n"
        result = PY.extract_variables(src, "foo")
        names = [v["name"] for v in result]
        assert "a" in names
        assert "b" in names
        assert "c" in names
        params = [v for v in result if v["kind"] == "parameter"]
        assert len(params) == 3

    def test_loop_variables(self):
        src = b"def foo(data):\n    for item in data:\n        pass\n"
        result = PY.extract_variables(src, "foo")
        item = next(v for v in result if v["name"] == "item")
        assert item["kind"] == "loop_var"

    def test_ignores_self(self):
        src = b"class Foo:\n    def bar(self):\n        x = 1\n        return x\n"
        result = PY.extract_variables(src, "bar")
        names = [v["name"] for v in result]
        assert "self" not in names

    def test_ignores_attribute_assignments(self):
        src = b"class Foo:\n    def __init__(self):\n        self.x = 1\n        y = 2\n"
        result = PY.extract_variables(src, "__init__")
        names = [v["name"] for v in result]
        assert "x" not in names  # self.x is not a local var
        assert "y" in names

    def test_deduplicates(self):
        src = b"def foo():\n    x = 1\n    x = 2\n    x += 3\n"
        result = PY.extract_variables(src, "foo")
        x_entries = [v for v in result if v["name"] == "x"]
        assert len(x_entries) == 1
        assert x_entries[0]["line"] == 2  # first assignment

    def test_function_not_found(self):
        src = b"def foo(): pass\n"
        result = PY.extract_variables(src, "nonexistent")
        assert result == []

    def test_has_line_numbers(self):
        src = b"def foo():\n    x = 1\n    y = 2\n"
        result = PY.extract_variables(src, "foo")
        item = next(v for v in result if v["name"] == "x")
        assert item["line"] == 2


# ─── Indexer integration ────────────────────────────────────────────────────

class TestVariablesIndexer:

    def test_get_variables(self, tmp_path):
        (tmp_path / "app.py").write_text("def foo():\n    x = 1\n    return x\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        result = indexer.get_variables("app.py", "foo")
        assert result is not None
        names = [v["name"] for v in result]
        assert "x" in names

    def test_file_not_found(self, tmp_path):
        (tmp_path / "x.py").write_text("x = 1\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        result = indexer.get_variables("ghost.py", "foo")
        assert result is None
