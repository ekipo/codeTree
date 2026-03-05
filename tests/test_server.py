import pytest
from codetree.server import create_server


def _get_tool_fn(mcp, name):
    """
    Helper to retrieve a registered tool's underlying function.

    In fastmcp 3.1.0 there is no _tool_manager. Tools are stored in
    mcp.local_provider._components keyed as 'tool:<name>@'.
    """
    key = f"tool:{name}@"
    tool = mcp.local_provider._components.get(key)
    if tool is None:
        raise KeyError(f"Tool '{name}' not found. Available: {list(mcp.local_provider._components.keys())}")
    return tool.fn


# ---------------------------------------------------------------------------
# Task 5: get_file_skeleton
# ---------------------------------------------------------------------------

def test_get_file_skeleton_returns_classes_and_functions(sample_repo):
    mcp = create_server(str(sample_repo))
    fn = _get_tool_fn(mcp, "get_file_skeleton")
    result = fn(file_path="calculator.py")
    assert "Calculator" in result
    assert "add" in result
    assert "divide" in result


def test_get_file_skeleton_unknown_file(sample_repo):
    mcp = create_server(str(sample_repo))
    fn = _get_tool_fn(mcp, "get_file_skeleton")
    result = fn(file_path="nonexistent.py")
    assert "not found" in result.lower() or result.strip() == ""


# ---------------------------------------------------------------------------
# Task 6: get_symbol
# ---------------------------------------------------------------------------

def test_get_symbol_returns_function_source(sample_repo):
    mcp = create_server(str(sample_repo))
    fn = _get_tool_fn(mcp, "get_symbol")
    result = fn(file_path="calculator.py", symbol_name="divide")
    assert "def divide" in result
    assert "ValueError" in result


def test_get_symbol_not_found(sample_repo):
    mcp = create_server(str(sample_repo))
    fn = _get_tool_fn(mcp, "get_symbol")
    result = fn(file_path="calculator.py", symbol_name="nonexistent")
    assert "not found" in result.lower()
