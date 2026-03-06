"""Tests for raw AST access."""
import pytest
from codetree.indexer import Indexer
from codetree.languages.python import PythonPlugin
from codetree.server import create_server


def _tool(mcp, name):
    return mcp.local_provider._components[f"tool:{name}@"].fn


PY = PythonPlugin()


# ─── AST S-expression (plugin) ───────────────────────────────────────────────

class TestAstSexp:

    def test_full_file(self):
        src = b"def foo(): pass\n"
        result = PY.get_ast_sexp(src)
        assert "function_definition" in result
        assert "foo" in result

    def test_specific_symbol(self):
        src = b"def foo(): pass\ndef bar(): pass\n"
        result = PY.get_ast_sexp(src, symbol_name="foo")
        assert "foo" in result
        assert "bar" not in result

    def test_max_depth_0(self):
        src = b"def foo(): pass\n"
        result = PY.get_ast_sexp(src, max_depth=0)
        assert "module" in result
        assert "..." in result

    def test_max_depth_1(self):
        src = b"def foo(): pass\n"
        result = PY.get_ast_sexp(src, max_depth=1)
        assert "function_definition" in result
        assert "..." in result

    def test_has_line_numbers(self):
        src = b"def foo(): pass\n"
        result = PY.get_ast_sexp(src)
        assert "[" in result

    def test_symbol_not_found(self):
        src = b"def foo(): pass\n"
        result = PY.get_ast_sexp(src, symbol_name="nonexistent")
        assert result is None

    def test_empty_file(self):
        result = PY.get_ast_sexp(b"")
        assert "module" in result


# ─── AST via indexer ─────────────────────────────────────────────────────────

class TestAstIndexer:

    def test_get_ast(self, tmp_path):
        (tmp_path / "app.py").write_text("def foo(): pass\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        result = indexer.get_ast("app.py")
        assert "function_definition" in result

    def test_get_ast_with_symbol(self, tmp_path):
        (tmp_path / "app.py").write_text("def foo(): pass\ndef bar(): pass\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        result = indexer.get_ast("app.py", symbol_name="foo")
        assert "foo" in result
        assert "bar" not in result

    def test_file_not_found(self, tmp_path):
        (tmp_path / "x.py").write_text("x = 1\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        result = indexer.get_ast("ghost.py")
        assert result is None


# ─── MCP tool: get_ast ───────────────────────────────────────────────────────

class TestGetAstTool:

    def test_full_file(self, tmp_path):
        (tmp_path / "app.py").write_text("def foo(): pass\n")
        fn = _tool(create_server(str(tmp_path)), "get_ast")
        result = fn(file_path="app.py")
        assert "function_definition" in result
        assert "foo" in result

    def test_specific_symbol(self, tmp_path):
        (tmp_path / "app.py").write_text("def foo(): pass\ndef bar(): pass\n")
        fn = _tool(create_server(str(tmp_path)), "get_ast")
        result = fn(file_path="app.py", symbol_name="foo")
        assert "foo" in result

    def test_max_depth(self, tmp_path):
        (tmp_path / "app.py").write_text("def foo(): pass\n")
        fn = _tool(create_server(str(tmp_path)), "get_ast")
        result = fn(file_path="app.py", max_depth=1)
        assert "..." in result

    def test_file_not_found(self, tmp_path):
        (tmp_path / "x.py").write_text("x = 1\n")
        fn = _tool(create_server(str(tmp_path)), "get_ast")
        result = fn(file_path="ghost.py")
        assert "not found" in result.lower()

    def test_symbol_not_found(self, tmp_path):
        (tmp_path / "app.py").write_text("def foo(): pass\n")
        fn = _tool(create_server(str(tmp_path)), "get_ast")
        result = fn(file_path="app.py", symbol_name="nonexistent")
        assert "not found" in result.lower()
