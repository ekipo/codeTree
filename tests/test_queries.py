import pytest
from codetree.queries import (
    extract_skeleton,
    extract_symbol_source,
    extract_calls_in_function,
    extract_symbol_usages,
)

SAMPLE_CODE = b"""\
class Calculator:
    def add(self, a, b):
        return a + b

    def divide(self, a, b):
        if b == 0:
            raise ValueError("cannot divide by zero")
        return a / b

def helper():
    calc = Calculator()
    return calc.add(1, 2)
"""


def test_skeleton_finds_class():
    result = extract_skeleton(SAMPLE_CODE)
    assert any(item["type"] == "class" and item["name"] == "Calculator" for item in result)


def test_skeleton_finds_methods():
    result = extract_skeleton(SAMPLE_CODE)
    names = [item["name"] for item in result]
    assert "add" in names
    assert "divide" in names


def test_skeleton_finds_top_level_function():
    result = extract_skeleton(SAMPLE_CODE)
    names = [item["name"] for item in result]
    assert "helper" in names


def test_skeleton_includes_line_numbers():
    result = extract_skeleton(SAMPLE_CODE)
    calc = next(item for item in result if item["name"] == "Calculator")
    assert calc["line"] == 1


def test_extract_symbol_finds_function():
    source, start_line = extract_symbol_source(SAMPLE_CODE, "add")
    assert "def add" in source
    assert "return a + b" in source


def test_extract_symbol_finds_class():
    source, start_line = extract_symbol_source(SAMPLE_CODE, "Calculator")
    assert "class Calculator" in source
    assert "def add" in source


def test_extract_symbol_returns_none_for_missing():
    result = extract_symbol_source(SAMPLE_CODE, "nonexistent")
    assert result is None


def test_extract_calls_in_function():
    calls = extract_calls_in_function(SAMPLE_CODE, "helper")
    assert "Calculator" in calls
    assert "add" in calls


def test_extract_symbol_usages_finds_calls():
    usages = extract_symbol_usages(SAMPLE_CODE, "add")
    # "add" appears as a method call in helper()
    assert len(usages) >= 1
    assert any(u["line"] > 1 for u in usages)
