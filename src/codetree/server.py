from fastmcp import FastMCP
from .indexer import Indexer


def create_server(root: str) -> FastMCP:
    mcp = FastMCP("codetree")
    indexer = Indexer(root)
    indexer.build()

    @mcp.tool()
    def get_file_skeleton(file_path: str) -> str:
        """Get all classes and function signatures in a Python file without their bodies."""
        skeleton = indexer.get_skeleton(file_path)
        if not skeleton:
            return f"File not found or empty: {file_path}"

        lines = []
        for item in skeleton:
            prefix = "  " if item["parent"] else ""
            parent_info = f" (in {item['parent']})" if item["parent"] else ""
            lines.append(f"{prefix}{item['type']} {item['name']}{parent_info} → line {item['line']}")
        return "\n".join(lines)

    @mcp.tool()
    def get_symbol(file_path: str, symbol_name: str) -> str:
        """Get the full source code of a specific function or class by name."""
        result = indexer.get_symbol(file_path, symbol_name)
        if result is None:
            return f"Symbol '{symbol_name}' not found in {file_path}"
        source, line = result
        return f"# {file_path}:{line}\n{source}"

    @mcp.tool()
    def find_references(symbol_name: str) -> str:
        """Find all usages of a symbol across the entire repo."""
        refs = indexer.find_references(symbol_name)
        if not refs:
            return f"No references found for '{symbol_name}'"
        lines = [f"References to '{symbol_name}':"]
        for ref in refs:
            lines.append(f"  {ref['file']}:{ref['line']}")
        return "\n".join(lines)

    @mcp.tool()
    def get_call_graph(file_path: str, function_name: str) -> str:
        """Get what a function calls and what calls it across the repo."""
        graph = indexer.get_call_graph(file_path, function_name)
        lines = [f"Call graph for '{function_name}':"]

        if graph["calls"]:
            lines.append(f"\n  {function_name} calls:")
            for c in graph["calls"]:
                lines.append(f"    → {c}")
        else:
            lines.append(f"\n  {function_name} calls: (nothing detected)")

        if graph["callers"]:
            lines.append(f"\n  {function_name} is called by:")
            for caller in graph["callers"]:
                lines.append(f"    ← {caller['file']}:{caller['line']}")
        else:
            lines.append(f"\n  {function_name} is called by: (no callers found)")

        return "\n".join(lines)

    return mcp


def run(root: str):
    mcp = create_server(root)
    mcp.run()
