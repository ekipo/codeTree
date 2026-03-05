"""Tests for batch operations: get_skeletons and get_symbols."""
import pytest
from codetree.server import create_server


def _tool(mcp, name):
    return mcp.local_provider._components[f"tool:{name}@"].fn


# ─── get_skeletons ───────────────────────────────────────────────────────────

class TestGetSkeletons:

    def test_returns_skeletons_for_multiple_files(self, sample_repo):
        fn = _tool(create_server(str(sample_repo)), "get_skeletons")
        result = fn(file_paths=["calculator.py", "main.py"])
        assert "=== calculator.py ===" in result
        assert "=== main.py ===" in result
        assert "Calculator" in result
        assert "run" in result

    def test_single_file(self, sample_repo):
        fn = _tool(create_server(str(sample_repo)), "get_skeletons")
        result = fn(file_paths=["calculator.py"])
        assert "=== calculator.py ===" in result
        assert "Calculator" in result

    def test_empty_list_returns_message(self, sample_repo):
        fn = _tool(create_server(str(sample_repo)), "get_skeletons")
        result = fn(file_paths=[])
        assert "no files" in result.lower()

    def test_missing_file_shows_inline_error(self, sample_repo):
        fn = _tool(create_server(str(sample_repo)), "get_skeletons")
        result = fn(file_paths=["calculator.py", "nonexistent.py"])
        assert "=== calculator.py ===" in result
        assert "Calculator" in result
        assert "nonexistent.py" in result
        assert "not found" in result.lower()

    def test_all_files_missing(self, sample_repo):
        fn = _tool(create_server(str(sample_repo)), "get_skeletons")
        result = fn(file_paths=["a.py", "b.py"])
        assert "not found" in result.lower()

    def test_includes_line_numbers(self, sample_repo):
        fn = _tool(create_server(str(sample_repo)), "get_skeletons")
        result = fn(file_paths=["calculator.py"])
        assert "→ line" in result

    def test_multi_language_files(self, multi_lang_repo):
        fn = _tool(create_server(str(multi_lang_repo)), "get_skeletons")
        result = fn(file_paths=["calc.py", "utils.js", "server.go"])
        assert "=== calc.py ===" in result
        assert "=== utils.js ===" in result
        assert "=== server.go ===" in result
