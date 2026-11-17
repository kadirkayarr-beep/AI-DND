"""Inventory of ai-dnd/game.py for the engine split: block index, call graph, constant clusters, claim re-check.

Read-only: parses with ast, symtable and tokenize and never rewrites a source file.
Run: python scripts/engine_split/inventory.py --root . --out-json <inventory.json> --out-claims <claims.md>
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import symtable
import sys
import tokenize
from pathlib import Path

# A script run as a file has only its own folder on sys.path: add ai-dnd and ai-dnd/scripts (same as the tests).
if __name__ == "__main__":
    sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]

FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _parse(path: Path) -> tuple[str, ast.Module]:
    source = Path(path).read_text(encoding="utf-8")
    return source, ast.parse(source, filename=str(path))


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [n for e in node.elts for n in _target_names(e)]
    if isinstance(node, ast.Starred):
        return _target_names(node.value)
    return []


def _bound(node: ast.stmt) -> tuple[str, list[str]]:
    """Kind and bound names of one top-level statement (kind 'other' when it binds no plain name)."""
    if isinstance(node, FUNCTION_NODES):
        return "function", [node.name]
    if isinstance(node, ast.ClassDef):
        return "class", [node.name]
    if isinstance(node, ast.Assign):
        names = [n for t in node.targets for n in _target_names(t)]
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        names = _target_names(node.target)
    elif isinstance(node, ast.Import):
        return "import", [(a.asname or a.name.split(".")[0]) for a in node.names]
    elif isinstance(node, ast.ImportFrom):
        return "import", [(a.asname or a.name) for a in node.names]
    else:
        names = []
    if names:
        return "assign", names
    return "other", [f"<{type(node).__name__}@{node.lineno}>"]


def top_level_index(path: Path) -> list[dict]:
    """One entry per name bound at module top level, in file order.

    start: first line of the comment block directly above (no blank line between), else the decorator or def line.
    def_line: the decorator line when decorated, else the statement line.
    lines: end - statement line + 1; the comment block and decorators are not counted.
    """
    source, tree = _parse(path)
    text = source.splitlines()
    out: list[dict] = []
    previous_end = 0
    for node in tree.body:
        decorators = getattr(node, "decorator_list", [])
        def_line = min([node.lineno] + [d.lineno for d in decorators])
        start = def_line
        while start - 1 > previous_end and text[start - 2].lstrip().startswith("#"):
            start -= 1
        kind, names = _bound(node)
        for name in names:
            out.append({"name": name, "kind": kind, "start": start, "def_line": def_line,
                        "end": node.end_lineno, "lines": node.end_lineno - node.lineno + 1})
        previous_end = node.end_lineno
    return out


def _global_reads(table: symtable.SymbolTable) -> set[str]:
    names = {s.get_name() for s in table.get_symbols() if s.is_global() and s.is_referenced()}
    for child in table.get_children():
        names |= _global_reads(child)
    return names


def call_graph(path: Path) -> dict[str, list[str]]:
    """Top-level function -> sorted top-level names (functions, classes, assignments, imports) it reads as free names."""
    source, tree = _parse(path)
    top = symtable.symtable(source, str(path), "exec")
    tables = {(c.get_name(), c.get_lineno()): c for c in top.get_children() if c.get_type() == "function"}
    engine_names = {d["name"] for d in top_level_index(path) if d["kind"] != "other"}
    graph: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, FUNCTION_NODES):
            reads = _global_reads(tables[(node.name, node.lineno)]) & engine_names
            graph.setdefault(node.name, set()).update(reads)
    return {name: sorted(reads) for name, reads in graph.items()}


def constant_clusters(path: Path) -> list[list[str]]:
    """Connected components of top-level assigned names; two names join when one's value reads the other."""
    _, tree = _parse(path)
    order: list[str] = []
    edges: list[tuple[str, str]] = []
    for node in tree.body:
        kind, names = _bound(node)
        if kind != "assign":
            continue
        order += [n for n in names if n not in order]
        value = getattr(node, "value", None)
        if value is None:
            continue
        read = {n.id for n in ast.walk(value) if isinstance(n, ast.Name)}
        edges += [(name, other) for name in names for other in read]
    assigned = set(order)
    parent = {n: n for n in order}

    def find(n: str) -> str:
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for a, b in edges:
        if b in assigned:
            parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for n in order:
        groups.setdefault(find(n), []).append(n)
    return sorted(groups.values(), key=lambda g: order.index(g[0]))


def closed_helpers(path: Path) -> list[str]:
    """Functions whose call-graph entry holds no function or class name (a self-call does not count)."""
    kinds = {d["name"]: d["kind"] for d in top_level_index(path)}
    return [name for name, reads in call_graph(path).items()
            if not any(kinds.get(r) in ("function", "class") and r != name for r in reads)]


# ---------------------------------------------------------------- spec claim re-check

def _functions(tree: ast.Module) -> list[ast.AST]:
    return [n for n in tree.body if isinstance(n, FUNCTION_NODES)]


def _functions_where(tree: ast.Module, test) -> list[str]:
    return sorted({f.name for f in _functions(tree) if any(test(n) for n in ast.walk(f))})


def _is_call_to(node: ast.AST, name: str) -> bool:
    return (isinstance(node, ast.Call)
            and ((isinstance(node.func, ast.Name) and node.func.id == name)
                 or (isinstance(node.func, ast.Attribute) and node.func.attr == name)))


def _is_sys_modules_name(node: ast.AST) -> bool:
    return (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
            and node.value.attr == "modules" and isinstance(node.slice, ast.Name)
            and node.slice.id == "__name__")


def _is_getlogger_name(node: ast.AST) -> bool:
    return _is_call_to(node, "getLogger") and any(isinstance(a, ast.Name) and a.id == "__name__" for a in node.args)


def _is_locals_get_preparsed(node: ast.AST) -> bool:
    return (_is_call_to(node, "get") and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Name) and node.func.value.func.id == "locals"
            and bool(node.args) and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "preparsed_scene_intent")


def _non_constant_default_functions(tree: ast.Module) -> list[str]:
    """Functions with a default that is not a bare constant node (the spec counts () and names as non-constant)."""
    found = set()
    for f in _functions(tree):
        defaults = list(f.args.defaults) + [d for d in f.args.kw_defaults if d is not None]
        if any(not isinstance(d, ast.Constant) for d in defaults):
            found.add(f.name)
    return sorted(found)


def _python_files(root: Path) -> list[Path]:
    """Every .py under root except game.py and docs/ (the scope of the spec's 430 / 245 / 190 counts)."""
    out = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root).parts
        if rel == ("game.py",) or rel[0] == "docs" or any(part in ("node_modules", ".venv") for part in rel):
            continue
        out.append(p)
    return out


def _game_usage(root: Path) -> tuple[int, set[str], int, set[str]]:
    imports = calls = 0
    names: set[str] = set()
    session_names: set[str] = set()
    for p in _python_files(root):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imports += sum(1 for a in n.names if a.name == "game" and a.asname is None)
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "game":
                names.add(n.attr)
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "game"
                    and any(k.arg == "session" for k in n.keywords)):
                calls += 1
                session_names.add(n.func.attr)
    return imports, names, calls, session_names


def _coin_writers_has_game_row(root: Path) -> bool | None:
    path = root / "api" / "tests" / "test_coin_writers.py"
    if not path.exists():
        return None
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(_target_names(t) == ["WRITERS"] for t in node.targets):
            return any(isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value.startswith("game.py:")
                       for c in ast.walk(node.value))
    return None


def _legacy_exec_scripts(root: Path) -> int:
    folder = root / "legacy_debug"
    count = 0
    for p in sorted(folder.glob("*.py")) if folder.exists() else []:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "exec"
               for n in ast.walk(tree)):
            count += 1
    return count


OWNER_COMMENT = re.compile(r"Kadir|\bowner\b|\bD-\d{3}", re.IGNORECASE)


def verify_claims(root: Path) -> list[dict]:
    """Re-measure each spec [D] claim on root/game.py. status: same | shifted (count moved) | false (named set differs)."""
    root = Path(root)
    game = root / "game.py"
    source, tree = _parse(game)
    index = top_level_index(game)
    rows: list[dict] = []

    def count(claim: str, spec, measured) -> None:
        rows.append({"claim": claim, "spec_value": spec, "measured": measured,
                     "status": "same" if spec == measured else "shifted"})

    def named(claim: str, spec: list[str], measured: list[str]) -> None:
        rows.append({"claim": claim, "spec_value": sorted(spec), "measured": sorted(measured),
                     "status": "same" if sorted(spec) == sorted(measured) else "false"})

    functions = _functions(tree)
    count("top-level functions", 521, len(functions))
    longest = next((d["lines"] for d in index if d["name"] == "_run_player_turn_internal"), None)
    count("_run_player_turn_internal lines", 2743, longest)

    with tokenize.open(game) as handle:
        comments = [t.string for t in tokenize.generate_tokens(handle.readline) if t.type == tokenize.COMMENT]
    count("comments (tokenize.COMMENT)", 1056, len(comments))
    count("comments naming Kadir, an owner decision or D-nnn", 119,
          sum(1 for c in comments if OWNER_COMMENT.search(c)))

    in_function = {f.name: sum(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(f)) for f in functions}
    count("in-function imports", 338, sum(in_function.values()))
    count("functions holding an in-function import", 127, sum(1 for v in in_function.values() if v))

    assigns = [n for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign))]
    count("top-level assignments", 170, len(assigns))
    count("top-level assignments holding re.compile(", 68,
          sum(1 for n in assigns if "re.compile(" in (ast.get_source_segment(source, n) or "")))

    named("uuid4( called only in", ["_apply_player_damage", "_resolve_player_death_turn",
                                    "_start_combat_with_initiative", "_down_outside_combat_turn",
                                    "_migrate_legacy_combat_state", "advance_campaign_time"],
          _functions_where(tree, lambda n: _is_call_to(n, "uuid4")))
    named("sys.modules[__name__] only in", ["_local_place_turn", "_run_player_turn_internal"],
          _functions_where(tree, _is_sys_modules_name))
    named("getLogger(__name__) only in", ["_repair_dilim1_fields", "_repair_dilim2_fields"],
          _functions_where(tree, _is_getlogger_name))
    named('locals().get("preparsed_scene_intent") only in', ["_run_player_turn_internal"],
          _functions_where(tree, _is_locals_get_preparsed))
    named("non-constant defaults only in", ["_combat_record_for_actor", "_has_unregistered_person_name",
                                            "_combat_end_if_decided", "initialize_game", "_death_save_line",
                                            "start_terminal_game"],
          _non_constant_default_functions(tree))

    count("closed helpers", 151, len(closed_helpers(game)))
    count("legacy_debug scripts that call exec(", 25, _legacy_exec_scripts(root))

    imports, names, calls, session_names = _game_usage(root)
    count("import game sites", 430, imports)
    count("distinct game.X names", 245, len(names))
    count("outside game.X(..., session=...) calls", 190, calls)
    count("names behind those session= calls", 39, len(session_names))

    has_row = _coin_writers_has_game_row(root)
    rows.append({"claim": "test_coin_writers.WRITERS holds no game.py row", "spec_value": "no game.py row",
                 "measured": {None: "WRITERS not found", True: "game.py row present",
                              False: "no game.py row"}[has_row],
                 "status": "same" if has_row is False else "false"})
    return rows


def claims_markdown(rows: list[dict]) -> str:
    lines = ["# Spec claim re-check (generated by scripts/engine_split/inventory.py)", "",
             "| Claim | Spec | Measured | Status |", "| --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['claim']} | {r['spec_value']} | {r['measured']} | {r['status']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="the ai-dnd folder (holds game.py)")
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-claims", type=Path, required=True)
    args = parser.parse_args(argv)
    game = args.root / "game.py"
    inventory = {"index": top_level_index(game), "call_graph": call_graph(game),
                 "constant_clusters": constant_clusters(game), "closed_helpers": closed_helpers(game)}
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(inventory, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = verify_claims(args.root)
    args.out_claims.write_text(claims_markdown(rows), encoding="utf-8")
    for r in rows:
        print(f"{r['status']:8} {r['claim']}: spec {r['spec_value']} measured {r['measured']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
