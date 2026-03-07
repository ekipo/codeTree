# codetree

An MCP server that gives coding agents structured code understanding via [tree-sitter](https://tree-sitter.github.io/).

Instead of reading entire files, an agent can ask *"what classes are in this file?"* or *"what does this function call?"* and get precise, structured answers — saving context window and improving accuracy.

## Quick Start

Add to Claude Code with one command:

```bash
claude mcp add codetree -- uvx codetree --root /path/to/your/project
```

Or run standalone:

```bash
uvx codetree --root /path/to/your/project
```

> **Note:** Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) to be installed. `uvx` downloads and runs the package automatically — no manual install needed.

See [Editor Setup](#editor-setup) below for Cursor, VS Code, Windsurf, and Claude Desktop.

## Tools

codetree exposes **16 tools** over MCP:

| Tool | Purpose | Example Return |
|------|---------|----------------|
| `get_file_skeleton(file_path)` | Classes, functions, methods with line numbers + doc comments | `class Foo → line 5` / `  def bar(x, y) → line 7` |
| `get_symbol(file_path, symbol_name)` | Full source of a function or class | `# calc.py:5\ndef add(a, b): ...` |
| `find_references(symbol_name)` | All usages across the repo | `  calc.py:12` / `  main.py:34` |
| `get_call_graph(file_path, function_name)` | What a function calls + what calls it | `→ validate` / `← main.py:20` |
| `get_imports(file_path)` | Import statements with line numbers | `  1: import os` / `  2: from pathlib import Path` |
| `get_skeletons(file_paths)` | Batch skeletons for multiple files | `=== calc.py ===\nclass Foo → line 1` |
| `get_symbols(symbols)` | Batch source for multiple symbols | `# calc.py:1\nclass Foo: ...` |
| `get_complexity(file_path, function_name)` | Cyclomatic complexity breakdown | `Complexity: 5 (if: 2, for: 1)` |
| `find_dead_code(file_path?)` | Symbols defined but never referenced | `function unused() → line 15` |
| `get_blast_radius(file_path, symbol_name)` | Transitive impact analysis | `Direct callers:\n  main.py: run() → line 4` |
| `detect_clones(file_path?, min_lines?)` | Duplicate/near-duplicate functions | `Clone group 1 (2 functions, 12 lines)` |
| `get_ast(file_path, symbol_name?, max_depth?)` | Raw AST as S-expression | `(function_definition [5:0-7:0] ...)` |
| `search_symbols(query?, type?, parent?)` | Flexible symbol search with filters | `calc.py: class Calculator → line 1` |
| `rank_symbols(top_n?, file_path?)` | Rank symbols by PageRank importance | `1. Foo → line 1 (importance: 12.3%)` |
| `find_tests(file_path, symbol_name)` | Find test functions for a symbol | `test_calc.py: test_add() → line 3` |
| `get_variables(file_path, function_name)` | Local variables and parameters | `Parameters:\n  x: int → line 1` |

`get_file_skeleton`, `get_skeletons`, and `search_symbols` accept an optional `format="compact"` parameter that omits doc comment lines for more concise output.

## Supported Languages

| Language | Extensions |
|----------|------------|
| Python | `.py` |
| JavaScript | `.js`, `.jsx` |
| TypeScript | `.ts` |
| TSX | `.tsx` |
| Go | `.go` |
| Rust | `.rs` |
| Java | `.java` |
| C | `.c`, `.h` |
| C++ | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh` |
| Ruby | `.rb` |

## Editor Setup

### Claude Code

```bash
claude mcp add codetree -- uvx codetree --root /path/to/your/project
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "codetree": {
      "command": "uvx",
      "args": ["codetree", "--root", "/path/to/your/project"]
    }
  }
}
```

### VS Code (Copilot)

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "codetree": {
      "command": "uvx",
      "args": ["codetree", "--root", "/path/to/your/project"]
    }
  }
}
```

### Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "codetree": {
      "command": "uvx",
      "args": ["codetree", "--root", "/path/to/your/project"]
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "codetree": {
      "command": "uvx",
      "args": ["codetree", "--root", "/path/to/your/project"]
    }
  }
}
```

## Architecture

```
MCP tool call → server.py → indexer.py → LanguagePlugin → tree-sitter → structured result
```

- **`server.py`** — FastMCP server, defines all 16 tools
- **`indexer.py`** — Discovers files, builds definition index and call graph
- **`cache.py`** — `.codetree/index.json` with mtime-based invalidation
- **`registry.py`** — Maps file extensions to language plugins
- **`languages/`** — One plugin per language, each implementing skeleton extraction, symbol lookup, call analysis, and more

## Adding a Language

1. `pip install tree-sitter-LANG` and add to `pyproject.toml`
2. Copy `src/codetree/languages/_template.py` to `languages/yourlang.py`
3. Implement the abstract methods
4. Register extensions in `registry.py`
5. Add tests

## Development

```bash
git clone https://github.com/ThinkyMiner/codeTree.git
cd codetree
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest

# Run all tests
pytest

# Run a single test file
pytest tests/languages/test_python.py -v
```

## Contributing

Contributions are welcome! Please open an issue to discuss larger changes before submitting a PR.
