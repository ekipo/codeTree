"""Intra-function dataflow and taint analysis using tree-sitter AST."""

import re
from ..languages.base import LanguagePlugin

# Known taint sources — method calls that return external/untrusted data
TAINT_SOURCES = {
    "request.get", "request.form", "request.args", "request.json",
    "request.data", "request.values", "request.files",
    "input", "raw_input",
    "sys.stdin.read", "sys.stdin.readline",
    "os.environ.get", "os.environ",
    "open", "read", "readline", "readlines",
}

# Known sinks — calls where tainted data is dangerous
TAINT_SINKS = {
    "db.execute", "cursor.execute", "connection.execute",
    "os.system", "os.popen",
    "subprocess.run", "subprocess.call", "subprocess.Popen", "subprocess.check_output",
    "eval", "exec", "compile",
    "open().write", "write",
}

# Known sanitizers — calls that make data safe
SANITIZERS = {
    "sanitize", "escape", "html.escape", "markupsafe.escape",
    "bleach.clean", "urllib.parse.quote",
    "parameterize", "quote", "sanitize_input",
    "int", "float", "bool",  # type casting is a form of sanitization
}


def extract_dataflow(plugin: LanguagePlugin, source: bytes, fn_name: str) -> dict | None:
    """Extract intra-function variable dataflow from AST.

    Returns:
        {
            "variables": [{"name", "line", "depends_on": [str], "source_expr": str}],
            "flow_chains": [[var1, var2, ...] ordered by dependency],
            "sources": [{"expr", "line", "kind"}],
            "sinks": [{"expr", "line", "kind"}],
        }
    """
    # Get function source
    result = plugin.extract_symbol_source(source, fn_name)
    if result is None:
        return None

    fn_source, start_line = result
    fn_bytes = fn_source.encode("utf-8", errors="replace")

    # Parse the function to walk assignments
    parser = plugin._get_parser()
    tree = parser.parse(fn_bytes)
    root = tree.root_node

    # Find the function body
    fn_body = _find_function_body(root, fn_name)
    if fn_body is None:
        # If we can't find the function in its own source, use root
        fn_body = root

    variables = []
    all_var_names = set()

    # Walk assignment nodes to build dependency graph
    _walk_assignments(fn_body, variables, all_var_names, start_line)

    # Identify sources and sinks from call expressions
    sources = []
    sinks = []
    _walk_calls(fn_body, sources, sinks, all_var_names, start_line)

    # Build flow chains (topological sort of dependencies)
    flow_chains = _build_flow_chains(variables)

    return {
        "variables": variables,
        "flow_chains": flow_chains,
        "sources": sources,
        "sinks": sinks,
    }


def extract_taint_paths(plugin: LanguagePlugin, source: bytes, fn_name: str) -> dict | None:
    """Analyze taint paths from sources to sinks.

    Returns:
        {
            "paths": [
                {"verdict": "SAFE"|"UNSAFE", "chain": [str], "sanitizer": str|None, "risk": str|None}
            ]
        }
    """
    flow = extract_dataflow(plugin, source, fn_name)
    if flow is None:
        return {"paths": []}

    # Build variable dependency map
    dep_map: dict[str, list[str]] = {}
    for v in flow["variables"]:
        dep_map[v["name"]] = v["depends_on"]

    # Build call map — which variables pass through which function calls
    call_map: dict[str, str] = {}  # var_name → call_expr that produces it
    for v in flow["variables"]:
        expr = v.get("source_expr", "")
        if "(" in expr:
            call_map[v["name"]] = expr

    paths = []

    # For each sink, trace backward to see if any taint source reaches it
    for sink in flow["sinks"]:
        sink_expr = sink["expr"]
        # Find variables used in the sink call
        sink_vars = _extract_identifiers_from_expr(sink_expr)

        for sv in sink_vars:
            # Trace backward through dependencies
            chain = _trace_backward(sv, dep_map, call_map)
            if not chain:
                continue

            # Check if any source in the chain is a taint source
            has_taint = False
            taint_source = None
            for var_name in chain:
                expr = call_map.get(var_name, "")
                for src in TAINT_SOURCES:
                    if src in expr:
                        has_taint = True
                        taint_source = expr
                        break
                if has_taint:
                    break

            if not has_taint:
                continue

            # Check if any sanitizer exists in the chain
            sanitizer = None
            for var_name in chain:
                expr = call_map.get(var_name, "")
                for san in SANITIZERS:
                    if san in expr:
                        sanitizer = san
                        break
                if sanitizer:
                    break

            chain_strs = chain + [sink_expr]
            if sanitizer:
                paths.append({
                    "verdict": "SAFE",
                    "chain": chain_strs,
                    "sanitizer": sanitizer,
                    "risk": None,
                })
            else:
                # Determine risk type
                risk = "unknown"
                if "execute" in sink_expr:
                    risk = "SQL injection"
                elif "system" in sink_expr or "subprocess" in sink_expr:
                    risk = "Command injection"
                elif "eval" in sink_expr or "exec" in sink_expr:
                    risk = "Code injection"

                paths.append({
                    "verdict": "UNSAFE",
                    "chain": chain_strs,
                    "sanitizer": None,
                    "risk": risk,
                })

    return {"paths": paths}


def _find_function_body(root, fn_name: str):
    """Find the body node of a function by name."""
    for node in _walk_tree(root):
        if node.type in ("function_definition", "function_declaration", "method_definition"):
            for child in node.children:
                if child.type in ("identifier", "property_identifier") and child.text:
                    if child.text.decode("utf-8", errors="replace") == fn_name:
                        # Return the body/block child
                        for c in node.children:
                            if c.type in ("block", "statement_block", "compound_statement"):
                                return c
                        return node
    return None


def _walk_tree(node):
    """Depth-first walk of all nodes."""
    yield node
    for child in node.children:
        yield from _walk_tree(child)


def _walk_assignments(node, variables: list, all_var_names: set, line_offset: int):
    """Walk AST to find assignments and their dependencies."""
    for n in _walk_tree(node):
        if n.type == "assignment":
            left = None
            right = None
            for child in n.children:
                if child.type == "identifier" and left is None:
                    left = child
                elif child.type == "=" or child.type == "assignment_operator":
                    continue
                elif left is not None and right is None:
                    right = child

            if left and right:
                var_name = left.text.decode("utf-8", errors="replace")
                if var_name in ("self", "cls"):
                    continue
                all_var_names.add(var_name)
                rhs_text = right.text.decode("utf-8", errors="replace") if right.text else ""
                deps = _extract_identifiers_from_node(right, all_var_names)
                line = (left.start_point[0] + line_offset) if hasattr(left, 'start_point') else 0

                variables.append({
                    "name": var_name,
                    "line": line,
                    "depends_on": list(deps),
                    "source_expr": rhs_text,
                })


def _extract_identifiers_from_node(node, known_vars: set) -> set[str]:
    """Extract identifier names from an AST node that match known variables."""
    ids = set()
    for n in _walk_tree(node):
        if n.type == "identifier" and n.text:
            name = n.text.decode("utf-8", errors="replace")
            if name in known_vars:
                ids.add(name)
    return ids


def _extract_identifiers_from_expr(expr: str) -> list[str]:
    """Simple text-based identifier extraction from an expression string."""
    return re.findall(r'\b([a-zA-Z_]\w*)\b', expr)


def _walk_calls(node, sources: list, sinks: list, var_names: set, line_offset: int):
    """Find function calls that are taint sources or sinks."""
    for n in _walk_tree(node):
        if n.type == "call" or n.type == "call_expression":
            call_text = n.text.decode("utf-8", errors="replace") if n.text else ""
            line = (n.start_point[0] + line_offset) if hasattr(n, 'start_point') else 0

            # Check if it's a known source
            for src in TAINT_SOURCES:
                if src in call_text:
                    sources.append({"expr": call_text, "line": line, "kind": "external_input"})
                    break

            # Check if it's a known sink
            for sink in TAINT_SINKS:
                if sink in call_text:
                    sinks.append({"expr": call_text, "line": line, "kind": _sink_kind(sink)})
                    break


def _sink_kind(sink_name: str) -> str:
    if "execute" in sink_name:
        return "database"
    if "system" in sink_name or "subprocess" in sink_name:
        return "shell"
    if "eval" in sink_name or "exec" in sink_name:
        return "code_execution"
    return "output"


def _build_flow_chains(variables: list) -> list[list[str]]:
    """Build ordered flow chains from variable dependencies."""
    chains = []
    visited = set()

    for v in variables:
        if v["name"] in visited:
            continue
        chain = _trace_forward(v["name"], variables, visited)
        if len(chain) > 1:
            chains.append(chain)

    return chains


def _trace_forward(start: str, variables: list, visited: set) -> list[str]:
    """Trace forward from a variable through its dependents."""
    chain = [start]
    visited.add(start)
    # Find variables that depend on start
    for v in variables:
        if start in v["depends_on"] and v["name"] not in visited:
            chain.extend(_trace_forward(v["name"], variables, visited))
    return chain


def _trace_backward(var_name: str, dep_map: dict, call_map: dict,
                    visited: set | None = None, max_depth: int = 20) -> list[str]:
    """Trace backward from a variable to its origins."""
    if visited is None:
        visited = set()
    if var_name in visited or max_depth <= 0:
        return []
    visited.add(var_name)

    deps = dep_map.get(var_name, [])
    if not deps:
        return [var_name]

    chain = []
    for dep in deps:
        sub_chain = _trace_backward(dep, dep_map, call_map, visited, max_depth - 1)
        chain.extend(sub_chain)
    chain.append(var_name)
    return chain
