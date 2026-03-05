import pytest
from codetree.languages.typescript import TypeScriptPlugin

PLUGIN = TypeScriptPlugin()

SAMPLE = b"""\
class Calculator {
  add(a: number, b: number): number {
    return a + b;
  }
  divide(a: number, b: number): number {
    if (b === 0) throw new Error('div by zero');
    return a / b;
  }
}

function helper(): number {
  const calc = new Calculator();
  return calc.add(1, 2);
}

interface Shape {
  area(): number;
}
"""


def test_skeleton_finds_class():
    result = PLUGIN.extract_skeleton(SAMPLE)
    assert any(item["type"] == "class" and item["name"] == "Calculator" for item in result)


def test_skeleton_finds_methods():
    result = PLUGIN.extract_skeleton(SAMPLE)
    names = [item["name"] for item in result]
    assert "add" in names and "divide" in names


def test_skeleton_finds_top_level_function():
    result = PLUGIN.extract_skeleton(SAMPLE)
    names = [item["name"] for item in result]
    assert "helper" in names


def test_skeleton_finds_interface():
    result = PLUGIN.extract_skeleton(SAMPLE)
    assert any(item["name"] == "Shape" for item in result)


def test_extract_symbol_finds_function():
    result = PLUGIN.extract_symbol_source(SAMPLE, "helper")
    assert result is not None
    source, _ = result
    assert "function helper" in source


def test_extract_symbol_finds_class():
    result = PLUGIN.extract_symbol_source(SAMPLE, "Calculator")
    assert result is not None
    source, _ = result
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
