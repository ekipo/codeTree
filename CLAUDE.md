# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

codetree is a Python MCP (Model Context Protocol) server that gives coding agents structured code understanding via tree-sitter. Instead of reading entire files, an agent can ask "what classes are in this file?" or "what does this function call?" and get precise, structured answers.

It exposes **17 tools** over MCP:

| Tool | Purpose | Returns |
|------|---------|---------|
| `get_file_skeleton(file_path, format?)` | Classes, functions, methods with line numbers + doc comments; `format="compact"` omits doc lines | `class Foo → line 5`, `"A calculator."`, `  def bar(x, y) (in Foo) → line 7` |
| `get_symbol(file_path, symbol_name)` | Full source of a function/class | `# path:line\n<source code>` |
| `find_references(symbol_name)` | All usages across the repo | `  file.py:12`, `  other.py:34` |
| `get_call_graph(file_path, function_name)` | What it calls + what calls it | `→ callee`, `← file.py:20` |
| `get_imports(file_path)` | Import/use statements with line numbers | `  1: import os`, `  2: from pathlib import Path` |
| `get_skeletons(file_paths, format?)` | Skeletons for multiple files in one call; `format="compact"` omits doc lines | `=== calc.py ===\nclass Foo → line 1` |
| `get_symbols(symbols)` | Full source of multiple symbols | `# calc.py:1\nclass Foo:` |
| `get_complexity(file_path, function_name)` | Cyclomatic complexity of a function | `Complexity of foo() in calc.py: 5\n  if: 2, for: 1` |
| `find_dead_code(file_path?)` | Symbols defined but never referenced | `Dead code in calc.py:\n  function unused() → line 15` |
| `get_blast_radius(file_path, symbol_name)` | Transitive impact analysis | `Direct callers:\n  main.py: run() → line 4` |
| `detect_clones(file_path?, min_lines?)` | Duplicate/near-duplicate functions | `Clone group 1 (2 functions, 12 lines each):` |
| `get_ast(file_path, symbol_name?, max_depth?)` | Raw AST as S-expression | `(function_definition [5:0-7:0] ...)` |
| `search_symbols(query?, type?, parent?, ..., format?)` | Flexible symbol search; `format="compact"` omits doc lines | `calc.py: class Calculator → line 1` |
| `rank_symbols(top_n?, file_path?)` | Rank symbols by PageRank importance | `1. file.py: class Foo → line 1  (importance: 12.3%)` |
| `find_tests(file_path, symbol_name)` | Find test functions for a symbol | `test_calc.py: test_add() → line 3  (name match)` |
| `get_variables(file_path, function_name)` | Local variables in a function | `Parameters:\n  x: int → line 1` |

`get_file_skeleton` also warns about syntax errors (`WARNING: File has syntax errors — skeleton may be incomplete`).

All `file_path` arguments are **relative to the repo root** (e.g., `"src/main.py"`).

## Supported Languages

| Extension(s) | Plugin | Key node types |
|---|---|---|
| `.py` | PythonPlugin | `function_definition`, `class_definition`, `decorated_definition` |
| `.js`, `.jsx` | JavaScriptPlugin | `function_declaration`, `class_declaration`, `arrow_function`, `generator_function_declaration` |
| `.ts` | TypeScriptPlugin | `function_declaration`, `class_declaration`, `abstract_class_declaration`, `interface_declaration`, `type_alias_declaration` |
| `.tsx` | TSXPlugin | Same as TS, uses `tsts.language_tsx()` |
| `.go` | GoPlugin | `function_declaration`, `method_declaration`, `struct_type`, `interface_type` |
| `.rs` | RustPlugin | `function_item`, `struct_item`, `enum_item`, `trait_item`, `impl_item` |
| `.java` | JavaPlugin | `class_declaration`, `interface_declaration`, `enum_declaration`, `method_declaration`, `constructor_declaration` |
| `.c`, `.h` | CPlugin | `function_definition`, `struct_specifier`, `type_definition` |
| `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh` | CppPlugin | `class_specifier`, `function_definition`, `struct_specifier`, `namespace_definition` |
| `.rb` | RubyPlugin | `class`, `module`, `method`, `singleton_method` |

## Commands

```bash
# Activate venv (required before all commands)
source .venv/bin/activate

# Run all tests (921 tests, ~20s)
pytest

# Run a single test file
pytest tests/languages/test_python.py -v

# Run a single test
pytest tests/languages/test_python.py::test_skeleton_finds_class -v

# Run only comprehensive tests for one language
pytest tests/languages/test_rust_comprehensive.py -v

# Run the MCP server
codetree --root /path/to/repo

# Install in dev mode
pip install -e .
```

No linter or formatter is configured.

## Architecture

```
MCP tool call → server.py → indexer.py → FileEntry.plugin → tree-sitter parse → structured result
```

### Core modules (`src/codetree/`)

| File | Responsibility |
|---|---|
| `server.py` | FastMCP 3.1.0 server — defines the 17 tools, wires cache + indexer at startup. Language-unaware. |
| `indexer.py` | Discovers files, stores a `FileEntry` per file (with its plugin + `has_errors` flag), routes all queries through the stored plugin. Builds a definition index and lazy call graph for dead code, blast radius, and clone detection. Skips `.venv`, `node_modules`, `__pycache__`, `.git`, etc. |
| `cache.py` | `.codetree/index.json` — stores pre-computed skeletons with mtime-based invalidation. Language-unaware. |
| `registry.py` | Maps file extensions → plugin instances. The **only** place languages are registered. |

### Plugin system (`src/codetree/languages/`)

| File | Responsibility |
|---|---|
| `base.py` | `LanguagePlugin` ABC with 5 abstract methods + `check_syntax()`, `compute_complexity()`, `normalize_source_for_clones()`, `get_ast_sexp()` defaults + shared `_matches()`, `_clean_doc()`, `_fill_docs_from_siblings()` helpers |
| `python.py` | PythonPlugin |
| `javascript.py` | JavaScriptPlugin (also provides `_arrow_params()` used by TS) |
| `typescript.py` | TypeScriptPlugin + TSXPlugin |
| `go.py` | GoPlugin |
| `rust.py` | RustPlugin |
| `java.py` | JavaPlugin |
| `c.py` | CPlugin |
| `cpp.py` | CppPlugin (inherits CPlugin) |
| `ruby.py` | RubyPlugin |
| `_template.py` | Boilerplate for adding new languages |

Each plugin implements:
1. **`extract_skeleton(source: bytes) -> list[dict]`** — top-level classes/functions/methods with `{type, name, line, parent, params, doc}`
2. **`extract_symbol_source(source: bytes, name: str) -> tuple[str, int] | None`** — full source text + start line
3. **`extract_calls_in_function(source: bytes, fn_name: str) -> list[str]`** — sorted callee names
4. **`extract_symbol_usages(source: bytes, name: str) -> list[dict]`** — all occurrences with `{line, col}`
5. **`extract_imports(source: bytes) -> list[dict]`** — import statements with `{line, text}`
6. **`check_syntax(source: bytes) -> bool`** — True if file has syntax errors (non-abstract, default False)
7. **`compute_complexity(source: bytes, fn_name: str) -> dict | None`** — cyclomatic complexity `{total, breakdown}` (non-abstract, default None)
8. **`normalize_source_for_clones(source: bytes) -> str`** — AST-normalized source for clone detection (non-abstract, default in base; requires `_get_parser()`)
9. **`get_ast_sexp(source: bytes, symbol_name?, max_depth?) -> str | None`** — S-expression AST output (non-abstract, default in base; requires `_get_parser()`)
10. **`extract_variables(source: bytes, fn_name: str) -> list[dict]`** — local variables with `{name, line, type, kind}` (non-abstract, default `[]`)

### Test structure (`tests/`)

| File | What it tests |
|---|---|
| `test_server.py` | Original 4 MCP tools via FastMCP, output format, line accuracy, cross-language |
| `test_indexer.py` | Build, skip-dirs, skeleton/symbol/refs/callgraph through indexer layer |
| `test_cache.py` | Cache load/save/invalidation |
| `tests/languages/test_<lang>.py` | Per-language core tests |
| `tests/languages/test_<lang>_comprehensive.py` | Exhaustive code pattern coverage per language |
| `test_new_features.py` | Method extraction, Rust traits/enums, Java enums, TS type aliases, indexer fixes |
| `test_edge_cases.py` | Empty files, syntax errors, comment-only files, unicode, nested code |
| `test_server_new_types.py` | MCP server formatting of trait/enum/type skeleton types |
| `test_imports.py` | Import extraction per-language + `get_imports` MCP tool |
| `test_docstrings.py` | Doc comment extraction per-language + skeleton doc display |
| `test_syntax_errors.py` | Syntax error detection per-language + skeleton warning |
| `test_dead_code.py` | Definition index, `find_dead_code` indexer method + MCP tool |
| `test_blast_radius.py` | Lazy call graph, `get_blast_radius` indexer method + MCP tool |
| `test_clones.py` | Clone normalization, `detect_clones` indexer method + MCP tool |
| `test_ast.py` | `get_ast_sexp` plugin method, `get_ast` indexer + MCP tool |
| `test_search.py` | `search_symbols` indexer method + MCP tool |
| `test_token_opt.py` | Compact format for skeleton/search tools |
| `test_importance.py` | PageRank symbol importance |
| `test_discovery.py` | Test function discovery |
| `test_variables.py` | Variable extraction per-language + MCP tool |

Fixtures in `conftest.py`: `sample_repo` (Python-only), `rich_py_repo` (decorators/dataclasses), `multi_lang_repo` (5 languages).

## tree-sitter 0.25.x API

The tree-sitter Python bindings have breaking changes from older docs:
- Use `Query(LANGUAGE, "...")` not `LANGUAGE.query(...)`
- Use `QueryCursor(query).matches(node)` not `query.matches(node)`
- Match captures are `list[Node]` — unwrap with `nodes[0]` or use the shared `_matches()` helper from `languages/base.py`
- All `.decode()` calls must use `errors="replace"`

## Language-Specific Gotchas

- **Python:** Decorated functions/classes are wrapped in `decorated_definition` — query both decorated and plain patterns. Check `decorated_definition` FIRST in `extract_symbol_source` to include decorator lines. `from __future__` is `future_import_statement` (not `import_from_statement`). Docstrings are in the function body (`expression_statement > string`), unlike all other languages where doc comments are `prev_named_sibling`.
- **JavaScript:** `new Foo()` is a `new_expression`, not `call_expression`. Exported classes wrap in `export_statement`. Generators use `generator_function_declaration`. Arrow functions: `lexical_declaration → arrow_function`. JSDoc `/** */` is a `comment` node (same type as `//`).
- **TypeScript:** Class names use `type_identifier` (not `identifier`). Grammar API: `tsts.language_typescript()` / `tsts.language_tsx()`. Abstract classes use `abstract_class_declaration` (separate from `class_declaration`). Same `export_statement` wrapping as JS.
- **Go/Rust/Java:** Struct/type names are `type_identifier` — search both `identifier` and `type_identifier` in usage queries.
- **Go:** Each `//` line is a separate `comment` node. Multi-line doc comments require walking back through consecutive `comment` siblings.
- **Rust:** Associated function calls (`Server::new()`) use `scoped_identifier name: (identifier)` in `call_expression`. Trait method signatures use `function_signature_item` (not `function_item`). Enums use `enum_item`. Each `///` line is a separate `line_comment` node (same walk-back needed as Go).
- **Java:** Constructors use `constructor_declaration` (not `method_declaration`). Interfaces use `interface_declaration` with methods in `interface_body`. Enum methods live under `enum_body > enum_body_declarations > method_declaration` (not directly in `enum_body`). Javadoc `/** */` is `block_comment` as `prev_named_sibling`.
- **C:** Root node is `translation_unit`. Functions use `function_definition → function_declarator → identifier`. Structs use `struct_specifier → type_identifier`. Typedef structs use `type_definition → type_identifier`. Includes use `preproc_include`. Doc comments are `///` comments as `prev_named_sibling`.
- **C++:** Inherits from CPlugin. Classes use `class_specifier → type_identifier`. Methods inside classes use `field_identifier` (not `identifier`). Namespaces use `namespace_definition → namespace_identifier`. Also searches `using_declaration` for imports.
- **Ruby:** Root node is `program`. Classes/modules use `constant` for names (not `identifier`). Methods without params don't have a `method_parameters` child. Singleton methods (`def self.foo`) use `singleton_method` node. Imports are `call` nodes where method is `require`/`require_relative`.

## Adding a New Language

1. `pip install tree-sitter-LANG` and add to `pyproject.toml`
2. Copy `src/codetree/languages/_template.py` → `languages/LANG.py`, implement 5 abstract methods + `check_syntax`
3. Register in `registry.py`
4. Add tests (use existing `tests/languages/test_python.py` as reference)

## Key Conventions

- Plugin classes: `{Lang}Plugin` (e.g., `PythonPlugin`, `GoPlugin`)
- Module-level parser/language globals: `_PARSER`, `_LANGUAGE`
- Skeleton results are deduplicated by `(name, line)` and sorted by line number
- Indexer `SKIP_DIRS` includes `.venv`, `node_modules`, `__pycache__`, `.git` — without this, crawling `.venv` causes Claude Code timeout
- FastMCP tool access in tests: `mcp.local_provider._components[f"tool:{name}@"].fn`
