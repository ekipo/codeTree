# codetree Production Hardening

## What This Is

codetree is a Python MCP server that gives coding agents structured code understanding via tree-sitter. This hardening effort fixes critical and high-priority bugs discovered during a codebase audit — issues that cause agents to receive wrong data, crash the server, or expose security holes.

## Core Value

Every MCP tool call returns correct, trustworthy data — agents can rely on codetree without worrying about stale state, silent failures, or wrong results.

## Requirements

### Validated

- ✓ `.codetree` added to SKIP_DIRS — existing (fixed 2026-04-03)
- ✓ `cache.load()` handles corrupt JSON gracefully — existing (fixed 2026-04-03)
- ✓ `--root` defaults to cwd instead of hardcoded path — existing (fixed 2026-04-03)
- ✓ MCP registration removed hardcoded `--root` — existing (fixed 2026-04-03)

### Active

- [ ] SQLite GraphStore is thread-safe for concurrent MCP tool calls (CONCERNS #4)
- [ ] All tool `file_path` inputs are validated against path traversal (CONCERNS #5)
- [ ] Definition index has no duplicates after cache injection (CONCERNS #2)
- [ ] Stale definitions from deleted files are cleaned up (CONCERNS #3)
- [ ] Symbol resolution uses qualified names, not bare names (CONCERNS #9)
- [ ] Plugin errors during indexing don't crash the server (CONCERNS #14)

### Out of Scope

- Low-priority tech debt (#15-18, #25-27) — not user-facing, can be addressed later
- Performance optimization (#20 find_references) — functional, just slow on large repos
- Taint analysis completeness (#19) — feature enhancement, not a bug
- Complexity for all languages (#22) — feature gap, not a bug
- Silent failure improvements (#6, #7) — these return empty data (not wrong data); lower risk
- Schema version enforcement (#11) — no schema changes are planned
- Cache mtime-only validation (#10) — extremely rare edge case

## Context

- Brownfield Python project with 23 MCP tools, ~1070 tests, 10 language plugins
- Uses FastMCP 3.1.0 with stdio transport
- SQLite graph database at `.codetree/graph.db` with `check_same_thread=False`
- MCP servers receive concurrent tool calls from agents — thread safety is critical
- Agents trust tool output — wrong data leads to wrong code suggestions

## Constraints

- **Testing**: All fixes must have tests; existing 1070 tests must continue passing
- **Backward compat**: No changes to MCP tool signatures (agents already use them)
- **Performance**: Server startup must stay under ~2s for typical repos

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Scope to Critical + High only | Focus on issues that cause wrong data or crashes, skip tech debt | — Pending |
| Skip already-fixed issues | cache.load(), .codetree SKIP_DIRS, --root default already done | ✓ Good |
| Thread safety via locking, not connection pooling | Simpler, lower risk for MCP use case | — Pending |
| Qualified name resolution in indexer | Graph layer already uses qualified names; align indexer | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

---
*Last updated: 2026-04-05 after initialization*
