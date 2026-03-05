"""Tests for cyclomatic complexity metrics."""
import pytest
from codetree.languages.python import PythonPlugin

PY = PythonPlugin()


class TestPythonComplexity:

    def test_simple_function_complexity_1(self):
        src = b"def simple():\n    return 1\n"
        result = PY.compute_complexity(src, "simple")
        assert result is not None
        assert result["total"] == 1
        assert result["breakdown"] == {}

    def test_single_if(self):
        src = b"def check(x):\n    if x > 0:\n        return x\n    return 0\n"
        result = PY.compute_complexity(src, "check")
        assert result["total"] == 2
        assert result["breakdown"].get("if", 0) == 1

    def test_if_elif_else(self):
        src = b"""\
def classify(x):
    if x > 0:
        return "positive"
    elif x < 0:
        return "negative"
    else:
        return "zero"
"""
        result = PY.compute_complexity(src, "classify")
        assert result["total"] == 3
        assert result["breakdown"]["if"] == 1
        assert result["breakdown"]["elif"] == 1

    def test_for_loop(self):
        src = b"def loop(items):\n    for x in items:\n        print(x)\n"
        result = PY.compute_complexity(src, "loop")
        assert result["total"] == 2

    def test_while_loop(self):
        src = b"def wait():\n    while True:\n        pass\n"
        result = PY.compute_complexity(src, "wait")
        assert result["total"] == 2

    def test_try_except(self):
        src = b"""\
def safe():
    try:
        return 1
    except ValueError:
        return 0
    except Exception:
        return -1
"""
        result = PY.compute_complexity(src, "safe")
        assert result["total"] == 3

    def test_boolean_operators(self):
        src = b"def check(a, b):\n    if a and b or a:\n        return 1\n"
        result = PY.compute_complexity(src, "check")
        assert result["total"] == 4

    def test_with_statement(self):
        src = b"def read():\n    with open('f') as f:\n        return f.read()\n"
        result = PY.compute_complexity(src, "read")
        assert result["total"] == 2

    def test_nested_complexity(self):
        src = b"""\
def nested(items):
    for x in items:
        if x > 0:
            while x > 10:
                x -= 1
"""
        result = PY.compute_complexity(src, "nested")
        assert result["total"] == 4

    def test_function_not_found(self):
        src = b"def foo(): pass\n"
        result = PY.compute_complexity(src, "nonexistent")
        assert result is None

    def test_empty_function(self):
        src = b"def empty(): pass\n"
        result = PY.compute_complexity(src, "empty")
        assert result is not None
        assert result["total"] == 1

    def test_method_in_class(self):
        src = b"""\
class Calc:
    def process(self, x):
        if x > 0:
            for i in range(x):
                print(i)
"""
        result = PY.compute_complexity(src, "process")
        assert result["total"] == 3
