"""Tests for dead code detection."""
import pytest
from codetree.indexer import Indexer


# ─── Definition index ────────────────────────────────────────────────────────

class TestDefinitionIndex:

    def test_definitions_built_from_skeleton(self, sample_repo):
        indexer = Indexer(str(sample_repo))
        indexer.build()
        assert "Calculator" in indexer._definitions
        assert "helper" in indexer._definitions
        assert "run" in indexer._definitions

    def test_definitions_contain_file_and_line(self, sample_repo):
        indexer = Indexer(str(sample_repo))
        indexer.build()
        defs = indexer._definitions["Calculator"]
        assert len(defs) == 1
        assert defs[0][0] == "calculator.py"  # file
        assert isinstance(defs[0][1], int)     # line

    def test_same_name_different_files(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo(): pass\n")
        (tmp_path / "b.py").write_text("def foo(): pass\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        assert len(indexer._definitions["foo"]) == 2

    def test_methods_included(self, sample_repo):
        indexer = Indexer(str(sample_repo))
        indexer.build()
        assert "add" in indexer._definitions
        assert "divide" in indexer._definitions
