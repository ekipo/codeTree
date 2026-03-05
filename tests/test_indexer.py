import pytest
from codetree.indexer import Indexer


def test_indexer_finds_python_files(sample_repo):
    idx = Indexer(sample_repo)
    idx.build()
    assert "calculator.py" in [p.name for p in idx.files]


def test_indexer_ignores_non_python_files(sample_repo):
    (sample_repo / "notes.txt").write_text("hello")
    idx = Indexer(sample_repo)
    idx.build()
    assert "notes.txt" not in [p.name for p in idx.files]


def test_indexer_skeleton_for_file(sample_repo):
    idx = Indexer(sample_repo)
    idx.build()
    skeleton = idx.get_skeleton("calculator.py")
    names = [item["name"] for item in skeleton]
    assert "Calculator" in names
    assert "add" in names
    assert "divide" in names


def test_indexer_get_symbol(sample_repo):
    idx = Indexer(sample_repo)
    idx.build()
    result = idx.get_symbol("calculator.py", "add")
    assert result is not None
    source, line = result
    assert "def add" in source


def test_indexer_find_references_across_files(sample_repo):
    idx = Indexer(sample_repo)
    idx.build()
    refs = idx.find_references("Calculator")
    files_with_refs = {r["file"] for r in refs}
    assert "calculator.py" in files_with_refs
    assert "main.py" in files_with_refs


def test_indexer_get_call_graph(sample_repo):
    idx = Indexer(sample_repo)
    idx.build()
    graph = idx.get_call_graph("calculator.py", "helper")
    assert "Calculator" in graph["calls"]
    assert "add" in graph["calls"]
