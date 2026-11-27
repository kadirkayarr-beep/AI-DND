"""Inventory of ai-dnd/game.py for the engine split: block index, call graph, constant clusters, claim re-check.

Read-only: parses with ast, symtable and tokenize and never rewrites a source file.
Run: python scripts/engine_split/inventory.py --root . --out-json <inventory.json> --out-claims <claims.md>
     python scripts/engine_split/inventory.py --root . --touching <names file>   (prints the touching test modules)
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

from engine_split.patch_census import _aliases  # noqa: E402

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


def bound_names(node: ast.stmt) -> tuple[str, list[str]]:
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
        kind, names = bound_names(node)
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
        kind, names = bound_names(node)
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


def _re_export_kinds(path: Path) -> dict[str, str]:
    """Names game.py binds with `from game_parts.<x> import`: their kind in the part file, else "function" (D-347)."""
    _, tree = _parse(path)
    kinds: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("game_parts."):
            part = Path(path).parent / "game_parts" / (node.module.split(".", 1)[1] + ".py")
            in_part = {d["name"]: d["kind"] for d in top_level_index(part)} if part.exists() else {}
            kinds.update({(a.asname or a.name): in_part.get(a.name, "function") for a in node.names})
    return kinds


def closed_helpers(path: Path) -> list[str]:
    """Functions whose call-graph entry holds no function or class name (a self-call does not count).

    A name re-exported from a part counts as what the part binds (a moved function is still a function)."""
    kinds = {d["name"]: d["kind"] for d in top_level_index(path)} | _re_export_kinds(path)
    return [name for name, reads in call_graph(path).items()
            if not any(kinds.get(r) in ("function", "class") and r != name for r in reads)]


_GAME_STRING = re.compile(r"(?<![\w.])game\.(\w+)")


def _last_identifier(node: ast.AST) -> str | None:
    """`a` for `a`, `b` for `a.b`; a call counts by what it calls (`game._session()` -> `_session`)."""
    while isinstance(node, ast.Call):
        node = node.func
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None


def _session_value(node: ast.AST | None, helpers: set[str]) -> bool:
    """A value that is a session (D-452): a call whose last identifier ends in "session" (create_session,
    GameSession, make_session, session(...)) or names a local helper that returns one, or a BoolOp/IfExp with one."""
    if isinstance(node, ast.Call):
        last = _last_identifier(node) or ""
        return last.lower().endswith("session") or last in helpers
    if isinstance(node, ast.BoolOp):
        return any(_session_value(v, helpers) for v in node.values)
    if isinstance(node, ast.IfExp):
        return _session_value(node.body, helpers) or _session_value(node.orelse, helpers)
    return False


def _session_helpers(tree: ast.Module) -> set[str]:
    """Names of functions that return a session value, or another helper's session, until nothing grows (D-452)."""
    functions = [n for n in ast.walk(tree) if isinstance(n, FUNCTION_NODES)]
    helpers: set[str] = set()
    grown = {None}
    while grown:
        grown = {f.name for f in functions if f.name not in helpers
                 and any(isinstance(r, ast.Return) and _session_value(r.value, helpers) for r in ast.walk(f))}
        helpers |= grown
    return helpers


def _created_sessions(tree: ast.Module) -> set[str]:
    """Last identifiers of what the module binds from a session value (D-446, D-452): `s = game.create_session()`
    gives `s`, `self.a = GameSession()` gives `a`, `p = make_session(seed=1)`, `s = sess or game.create_session()`
    and `s = create()` (a module function that returns a session) give their targets."""
    helpers = _session_helpers(tree)
    created = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and _session_value(n.value, helpers):
            created.update(_last_identifier(t) for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
                           if isinstance(t, (ast.Name, ast.Attribute)))
    return created


def _is_session(node: ast.AST, sessions: set[str]) -> bool:
    """A receiver that holds a session (D-446: GameSession binds every engine function): its last identifier
    contains "session" (any case) or the module bound it from create_session()/GameSession(). Conservative."""
    last = _last_identifier(node)
    return last is not None and ("session" in last.lower() or last in sessions)


def _names_engine(text: str, names: set[str]) -> bool:
    """A string that holds "game.<name>", or that is the engine file path: a test that names the file reads its
    source whatever the names (D-461)."""
    return text == "game.py" or text.endswith("/game.py") or any(m in names for m in _GAME_STRING.findall(text))


def _touches(node: ast.AST, aliases: set[str], names: set[str], sessions: set[str]) -> bool:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
        return node.attr in names
    if isinstance(node, ast.Attribute) and _is_session(node.value, sessions):  # session.<name>
        return node.attr in names
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _names_engine(node.value, names)
    if isinstance(node, ast.Call) and len(node.args) > 1:  # patch.object(game, "<name>"), getattr(game, "<name>")
        first, second = node.args[0], node.args[1]  # and the same on a session
        return (((isinstance(first, ast.Name) and first.id in aliases) or _is_session(first, sessions))
                and isinstance(second, ast.Constant) and second.value in names)
    if isinstance(node, ast.ImportFrom) and node.module == "game":
        return any(a.name in names for a in node.names)
    return False


def _attr_reads(tree: ast.Module):
    """Returns alias -> the attributes read as `alias.<attr>` in the module, or None when alias is used bare."""
    attrs: dict[str, set[str]] = {}
    on_attribute = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            attrs.setdefault(n.value.id, set()).add(n.attr)
            on_attribute.add(id(n.value))
    bare = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in on_attribute}
    return lambda alias: None if alias in bare else attrs.get(alias, set())


def _from_import_unit(stmt: ast.ImportFrom, alias: ast.alias, names: set[str], attrs_read) -> dict:
    """The unit of one `from m import x`: a top-level `from game import <name>` touches and runs on import (D-438)."""
    star = alias.name == "*"
    direct = stmt.module == "game" and alias.name in names
    return {"binds": {alias.asname or alias.name} - {"*"}, "run": star or direct, "reads": set(), "import": True,
            "direct": direct,
            "refs": [(stmt.module, None if star else alias.name, None if star else attrs_read(alias.asname or alias.name))]}


def _units(tree: ast.Module, aliases: set[str], names: set[str]) -> list[dict]:
    """One unit per top-level def/class/statement and per imported alias: the names it binds, whether it runs on
    import ("run"), whether it touches a name itself, the bare names it reads and the (module, name, attrs) it
    imports (name None = the module named; attrs = what is read on a module imported whole, None = all of it)."""
    _attrs_read = _attr_reads(tree)
    sessions = _created_sessions(tree)
    units = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)) and not getattr(stmt, "level", 0):
            for a in stmt.names:
                if isinstance(stmt, ast.Import):  # `import a.b` binds `a`: the whole module counts
                    units.append({"binds": {a.asname or a.name.split(".")[0]}, "run": False, "direct": False,
                                  "import": True, "reads": set(), "refs": [(a.name, None, _attrs_read(a.asname)
                                                                            if a.asname else None)]})
                else:
                    units.append(_from_import_unit(stmt, a, names, _attrs_read))
            continue
        refs = []
        for node in ast.walk(stmt):
            if isinstance(node, ast.Import):
                refs += [(a.name, None, None) for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                refs += [(node.module, None if a.name == "*" else a.name,
                          None if a.name == "*" else _attrs_read(a.asname or a.name)) for a in node.names]
        is_def = isinstance(stmt, (*FUNCTION_NODES, ast.ClassDef))
        units.append({"binds": {stmt.name} if is_def else set(bound_names(stmt)[1]), "run": not is_def, "refs": refs,
                      "direct": any(_touches(node, aliases, names, sessions) for node in ast.walk(stmt)),
                      "reads": {n.id for n in ast.walk(stmt) if isinstance(n, ast.Name)}})
        if isinstance(stmt, ast.ClassDef):  # a class body (not its methods) runs on import
            body = [s for s in stmt.body if not isinstance(s, FUNCTION_NODES)]
            units.append({"binds": set(), "run": True, "refs": [], "reads": set(),
                          "direct": any(_touches(n, aliases, names, sessions) for s in body for n in ast.walk(s))})
    return units


def touching_tests(root: Path, names: set[str]) -> list[str]:
    """Dotted test modules (root/test_*.py, root/api/tests/test_*.py) that read game.<name> (also through an
    `import game as x` alias, `patch.object(game, "<name>")` or `from game import <name>`), read it on a session
    (`session.<name>`, `getattr(session, "<name>")`, see _is_session; D-446) or hold "game.<name>",
    directly or through a name they import (transitively) from a module under api/tests that does
    (e.g. rule_oracles reads game.SKILLS). Name level: importing an untouched helper of a touching module does
    not count, unless that module touches while it is imported. A test that holds the path "game.py" counts for
    every name (it reads the engine source). Import chains of any depth are followed (D-437)."""
    root = Path(root)
    tests = sorted(root.glob("test_*.py")) + sorted((root / "api" / "tests").glob("test_*.py"))
    modules: dict[str, list[dict]] = {}
    for path in tests + [p for p in sorted((root / "api" / "tests").rglob("*.py")) if p not in tests]:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parts = path.relative_to(root).with_suffix("").parts
        modules[".".join(parts[:-1] if parts[-1] == "__init__" else parts)] = _units(tree, _aliases(tree), names)

    def any_touch(m):
        return any(u["direct"] for u in modules[m])

    def touch_by(m, wanted):  # a run unit touches every importer; a def or name only the importer that reads it
        return any(u["direct"] and (u["run"] or u["binds"] & wanted) for u in modules[m])

    def ref_touches(mod, name, attrs):
        whole = f"{mod}.{name}" if name is not None and f"{mod}.{name}" in modules else mod if name is None else None
        if whole is not None:  # `import m` or `from package import m`: m counts by the attributes read on it
            return whole in modules and (any_touch(whole) if attrs is None else touch_by(whole, attrs))
        return mod in modules and touch_by(mod, {name})

    def runs_touch(mod, name):  # importing the module runs a statement of it that touches (D-366)
        whole = f"{mod}.{name}" if name is not None and f"{mod}.{name}" in modules else mod
        return whole in modules and any(u["run"] and u["direct"] for u in modules[whole])

    changed = True
    while changed:  # "direct" grows into "touches" until nothing changes
        changed = False
        for units in modules.values():
            for u in units:  # an import of a module that touches while it runs is itself a run statement
                if u.get("import") and not u["run"] and any(runs_touch(r[0], r[1]) for r in u["refs"]):
                    u["run"] = u["direct"] = changed = True
            touching_binds = {b for u in units if u["direct"] for b in u["binds"]}
            for u in units:
                if not u["direct"] and (u["reads"] & touching_binds or any(ref_touches(*r) for r in u["refs"])):
                    u["direct"] = changed = True
    return sorted(m for m in (".".join(p.relative_to(root).with_suffix("").parts) for p in tests) if any_touch(m))


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
                                    "advance_campaign_time"],
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
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-claims", type=Path)
    parser.add_argument("--touching", type=Path, help="a file of names, one per line (a batch file)")
    args = parser.parse_args(argv)
    if args.touching:
        names = {line.strip() for line in args.touching.read_text(encoding="utf-8").splitlines() if line.strip()}
        print(" ".join(touching_tests(args.root, names)))
        return 0
    if not (args.out_json and args.out_claims):
        parser.error("--out-json and --out-claims are required without --touching")
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
