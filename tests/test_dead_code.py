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


from codetree.server import create_server


def _tool(mcp, name):
    return mcp.local_provider._components[f"tool:{name}@"].fn


# ─── Dead code detection (indexer) ───────────────────────────────────────────

class TestFindDeadCode:

    def test_finds_unused_function(self, tmp_path):
        (tmp_path / "app.py").write_text("""\
def used():
    return 1

def unused():
    return 2

def main():
    used()
""")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        dead = indexer.find_dead_code()
        dead_names = [d["name"] for d in dead]
        assert "unused" in dead_names

    def test_used_function_not_dead(self, tmp_path):
        (tmp_path / "app.py").write_text("""\
def used():
    return 1

def main():
    used()
""")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        dead = indexer.find_dead_code()
        dead_names = [d["name"] for d in dead]
        assert "used" not in dead_names

    def test_cross_file_usage_not_dead(self, tmp_path):
        (tmp_path / "lib.py").write_text("def helper(): return 1\n")
        (tmp_path / "main.py").write_text("from lib import helper\nx = helper()\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        dead = indexer.find_dead_code()
        dead_names = [d["name"] for d in dead]
        assert "helper" not in dead_names

    def test_main_excluded(self, tmp_path):
        (tmp_path / "app.py").write_text("def main(): pass\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        dead = indexer.find_dead_code()
        dead_names = [d["name"] for d in dead]
        assert "main" not in dead_names

    def test_test_functions_excluded(self, tmp_path):
        (tmp_path / "test_app.py").write_text("def test_something(): pass\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        dead = indexer.find_dead_code()
        dead_names = [d["name"] for d in dead]
        assert "test_something" not in dead_names

    def test_dunder_methods_excluded(self, tmp_path):
        (tmp_path / "app.py").write_text("""\
class Foo:
    def __init__(self): pass
    def __str__(self): return ""
""")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        dead = indexer.find_dead_code()
        dead_names = [d["name"] for d in dead]
        assert "__init__" not in dead_names
        assert "__str__" not in dead_names

    def test_init_py_symbols_excluded(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("def public_api(): pass\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        dead = indexer.find_dead_code()
        dead_names = [d["name"] for d in dead]
        assert "public_api" not in dead_names

    def test_per_file_mode(self, tmp_path):
        (tmp_path / "a.py").write_text("def unused_a(): pass\n")
        (tmp_path / "b.py").write_text("def unused_b(): pass\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        dead = indexer.find_dead_code(file_path="a.py")
        dead_names = [d["name"] for d in dead]
        assert "unused_a" in dead_names
        assert "unused_b" not in dead_names

    def test_dead_code_returns_type_and_line(self, tmp_path):
        (tmp_path / "app.py").write_text("def unused(): pass\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        dead = indexer.find_dead_code()
        item = next(d for d in dead if d["name"] == "unused")
        assert item["type"] == "function"
        assert item["line"] == 1
        assert item["file"] == "app.py"

    def test_empty_repo(self, tmp_path):
        (tmp_path / "empty.py").write_text("x = 1\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        dead = indexer.find_dead_code()
        assert dead == []

    def test_class_used_cross_file(self, tmp_path):
        (tmp_path / "models.py").write_text("class User:\n    pass\n")
        (tmp_path / "main.py").write_text("from models import User\nu = User()\n")
        indexer = Indexer(str(tmp_path))
        indexer.build()
        dead = indexer.find_dead_code()
        dead_names = [d["name"] for d in dead]
        assert "User" not in dead_names
