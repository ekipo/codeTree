import pytest
from codetree.languages.javascript import JavaScriptPlugin

PLUGIN = JavaScriptPlugin()

SAMPLE = b"""\
class Calculator {
  add(a, b) {
    return a + b;
  }
  divide(a, b) {
    if (b === 0) throw new Error('div by zero');
    return a / b;
  }
}

function helper() {
  const calc = new Calculator();
  return calc.add(1, 2);
}
"""


def test_skeleton_finds_class():
    result = PLUGIN.extract_skeleton(SAMPLE)
    assert any(item["type"] == "class" and item["name"] == "Calculator" for item in result)


def test_skeleton_finds_methods():
    result = PLUGIN.extract_skeleton(SAMPLE)
    names = [item["name"] for item in result]
    assert "add" in names
    assert "divide" in names


def test_skeleton_method_has_parent():
    result = PLUGIN.extract_skeleton(SAMPLE)
    add = next(item for item in result if item["name"] == "add")
    assert add["parent"] == "Calculator"


def test_skeleton_finds_top_level_function():
    result = PLUGIN.extract_skeleton(SAMPLE)
    names = [item["name"] for item in result]
    assert "helper" in names


def test_skeleton_includes_line_numbers():
    result = PLUGIN.extract_skeleton(SAMPLE)
    calc = next(item for item in result if item["name"] == "Calculator")
    assert calc["line"] == 1


def test_extract_symbol_finds_function():
    result = PLUGIN.extract_symbol_source(SAMPLE, "helper")
    assert result is not None
    source, line = result
    assert "function helper" in source


def test_extract_symbol_finds_class():
    result = PLUGIN.extract_symbol_source(SAMPLE, "Calculator")
    assert result is not None
    source, line = result
    assert "class Calculator" in source


def test_extract_symbol_returns_none_for_missing():
    assert PLUGIN.extract_symbol_source(SAMPLE, "nonexistent") is None


def test_extract_calls_in_function():
    calls = PLUGIN.extract_calls_in_function(SAMPLE, "helper")
    assert "Calculator" in calls
    assert "add" in calls


def test_extract_symbol_usages():
    usages = PLUGIN.extract_symbol_usages(SAMPLE, "Calculator")
    assert len(usages) >= 1
