"""In-place move of top-level blocks from ai-dnd/game.py into game_parts/<part>.py (N3 rules).

The source text is edited in place: blocks are cut byte for byte, and the only change inside a moved block is the
six characters `game.` before each free reference to an engine name. Nothing is regenerated from a syntax tree.
Run: python scripts/engine_split/move_block.py --game game.py --part game_parts/<x>.py (--names a,b | --names-file F)
     --census api/tests/engine_split_locks/patch_census.json [--report out.json]
     [--identity-allowlist api/tests/engine_split_locks/identity_allowlist.json]
A refusal prints `REFUSED <reason>` on stderr, exits 2 and writes no file.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import symtable
import sys
import tokenize
from pathlib import Path

# A script run as a file has only its own folder on sys.path: add ai-dnd and ai-dnd/scripts (same as the tests).
if __name__ == "__main__":
    sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]

from engine_split.inventory import top_level_index  # noqa: E402

FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
DYNAMIC_NAMES = {"__file__", "__name__"}
DYNAMIC_CALLS = {"globals", "locals", "vars"}
IDENTITY_ROW_NAMES = {"locals", "sys.modules"}  # the only identity uses an identity_allowlist.json row can let through
COMPREHENSION_NAMES = {ast.ListComp: "listcomp", ast.SetComp: "setcomp", ast.DictComp: "dictcomp", ast.GeneratorExp: "genexpr"}
MOVABLE_KINDS ={"function", "class", "assign"}
# Spec section 5: names that stay in game.py (the `game.py (kalır)` row and the bullets under the table).
NEVER_MOVED = frozenset({
    "world_state", "messages", "RULE_ORDER", "GameSession", "_session", "_bind_session_engine", "create_session",
    "_GameModule", "_speech_debug_trail", "DEFAULT_SAVE_PATH", "start_terminal_game",
    "_DEFAULT_SESSION", "_ACTIVE_SESSION", "_ENGINE_FUNCTIONS", "_ENGINE_NAMESPACE", "_CHARACTER_GLOBALS",
    "_PART_MODULES", "recent_dm_narrations",
})


class MoveRefused(Exception):
    """The block cannot be moved mechanically; the message is the reason."""


def _collect_tables(table: symtable.SymbolTable, out: dict) -> None:
    for child in table.get_children():
        kind = child.get_type()
        if kind in ("function", "class"):
            flavour = "lambda" if child.get_name() == "lambda" else kind
            out.setdefault((kind, child.get_lineno(), flavour), []).append(child)
        _collect_tables(child, out)


class _Scan:
    """Walks one block with the symtable of the same text and records the free references to engine names."""

    def __init__(self, block: str, prefix: set[str], identity_allow=frozenset(), part_rel: str | None = None):
        self.prefix = prefix
        self.identity_allow = identity_allow  # (file, function, name) rows, the key R6 (routing_audit) uses
        self.part_rel = part_rel
        self.qual: list[str] = []  # enclosing def and class names, joined with "." as R6 reports the function
        self.tree = ast.parse(block)
        self.top = symtable.symtable(block, "<block>", "exec")
        self.tables: dict = {}
        _collect_tables(self.top, self.tables)
        self.hits: list[tuple[int, int, str]] = []  # (line, byte column, name)
        self.shadowed: list[set[str]] = []  # loop variables of inlined comprehensions

    def run(self) -> list[tuple[int, int, str]]:
        for stmt in self.tree.body:
            self.visit(stmt, self.top, False, None)
        return self.hits

    def claim(self, node: ast.AST, kind: str):
        """The symtable table of a scope node, matched by kind, line and name. None for a comprehension the compiler inlined."""
        flavour = "lambda" if isinstance(node, ast.Lambda) else kind
        queue = self.tables.get((kind, node.lineno, flavour), [])
        for i, table in enumerate(queue):
            if isinstance(node, COMPREHENSIONS):
                matches = table.get_name().strip("<>") == COMPREHENSION_NAMES[type(node)]
            else:
                matches = isinstance(node, ast.Lambda) or table.get_name() == node.name
            if matches:
                return queue.pop(i)
        if isinstance(node, COMPREHENSIONS):
            return None
        raise MoveRefused(f"scope mismatch between ast and symtable at line {node.lineno}")

    def allowed(self, name: str) -> bool:
        """An identity use (`locals` or `sys.modules`) that an identity_allowlist.json row names for this part and function."""
        key = (self.part_rel, ".".join(self.qual) or "<module>", name)
        return name in IDENTITY_ROW_NAMES and self.part_rel is not None and key in self.identity_allow

    def visit_all(self, nodes, table, in_def, where):
        for node in nodes:
            if node is not None:
                self.visit(node, table, in_def, where)

    def visit(self, node: ast.AST, table, in_def: bool, where):
        if isinstance(node, FUNCTION_NODES) or isinstance(node, ast.Lambda):
            args = node.args
            if isinstance(node, FUNCTION_NODES):
                self.visit_all(node.decorator_list, table, in_def, "decorator")
            self.visit_all(args.defaults + args.kw_defaults, table, in_def, "default")
            if isinstance(node, FUNCTION_NODES):
                every_arg = args.posonlyargs + args.args + args.kwonlyargs + [args.vararg, args.kwarg]
                self.visit_all([a.annotation for a in every_arg if a is not None] + [node.returns],
                               table, in_def, "annotation")
            inner = self.claim(node, "function")
            body = node.body if isinstance(node, FUNCTION_NODES) else [node.body]
            self.qual += [node.name] if isinstance(node, FUNCTION_NODES) else []  # a lambda keeps its enclosing name (R6)
            self.visit_all(body, inner, True, None)
            if isinstance(node, FUNCTION_NODES):
                self.qual.pop()
        elif isinstance(node, ast.ClassDef):
            self.visit_all(node.decorator_list, table, in_def, "decorator")
            self.visit_all(node.bases + [k.value for k in node.keywords], table, in_def, where)
            self.qual.append(node.name)
            self.visit_all(node.body, self.claim(node, "class"), in_def, where)
            self.qual.pop()
        elif isinstance(node, COMPREHENSIONS):
            first = node.generators[0]
            self.visit(first.iter, table, in_def, where)
            inner = self.claim(node, "function")
            if inner is None:  # inlined by the compiler: its names sit in the enclosing table; the loop targets stay local to it
                inner = table
                self.shadowed.append({n.id for gen in node.generators for n in ast.walk(gen.target) if isinstance(n, ast.Name)})
            self.visit(first.target, inner, in_def, where)
            self.visit_all(first.ifs, inner, in_def, where)
            for gen in node.generators[1:]:
                self.visit_all([gen.iter, gen.target] + gen.ifs, inner, in_def, where)
            self.visit_all([node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt], inner, in_def, where)
            if inner is table:
                self.shadowed.pop()
        elif isinstance(node, ast.Name):
            self.name(node, table, in_def, where)
        else:
            if isinstance(node, ast.Global):
                raise MoveRefused(f"`global` statement at line {node.lineno}")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in DYNAMIC_CALLS
                    and not self.allowed(node.func.id)):
                raise MoveRefused(f"`{node.func.id}(` at line {node.lineno} (N3 rule 6)")
            if (isinstance(node, ast.Attribute) and node.attr == "modules"
                    and isinstance(node.value, ast.Name) and node.value.id == "sys" and not self.allowed("sys.modules")):
                raise MoveRefused(f"`sys.modules` at line {node.lineno} (N3 rule 6)")
            self.visit_all(ast.iter_child_nodes(node), table, in_def, where)

    def name(self, node: ast.Name, table, in_def: bool, where) -> None:
        if node.id in DYNAMIC_NAMES:
            raise MoveRefused(f"`{node.id}` at line {node.lineno} (N3 rule 6)")
        if not isinstance(node.ctx, ast.Load) or any(node.id in names for names in self.shadowed):
            return
        module_level = table is self.top
        try:
            symbol = table.lookup(node.id)
        except KeyError:
            raise MoveRefused(f"name {node.id!r} missing from the symtable at line {node.lineno}") from None
        if module_level:
            is_global = not (symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace())
        else:
            is_global = symbol.is_global()
        if node.id == "open" and is_global:
            raise MoveRefused(f"bare `open` at line {node.lineno}: it must stay a patchable engine name")
        if node.id not in self.prefix or not (is_global or module_level):
            return
        if where:
            raise MoveRefused(f"engine name {node.id!r} in a {where} at line {node.lineno} (N3 rule 4)")
        if not in_def:
            raise MoveRefused(f"engine name {node.id!r} outside a def body at line {node.lineno} (F6)")
        self.hits.append((node.lineno, node.col_offset, node.id))


def prefix_names(block: str, engine_names: set[str], keep_bare: set[str], identity_allow=frozenset(),
                 part_rel: str | None = None) -> tuple[str, list[tuple[int, int, str]]]:
    """Insert `game.` before each free (global-scope) reference to a name in engine_names - keep_bare.

    Returns the new text and the insertions (line, column, name), 1-based line, column in characters of the original.
    Raises MoveRefused for the N3 refusals (bare open, engine name in a default / decorator / annotation or outside a
    def body, `global`, __file__, __name__, globals(), locals(), vars(), sys.modules).
    A `locals(` call or a `sys.modules` read is let through, unchanged, when identity_allow holds
    (part_rel, <function as R6 reports it>, "locals" | "sys.modules"); every other refusal stays.
    """
    lines = block.split("\n")  # "\r" stays at the end of its line, so line endings survive
    hits = _Scan(block, set(engine_names) - set(keep_bare), identity_allow, part_rel).run()
    try:
        name_tokens = {tok.start: tok.string for tok in tokenize.generate_tokens(io.StringIO(block).readline)
                       if tok.type == tokenize.NAME}
    except (tokenize.TokenError, SyntaxError) as exc:
        raise MoveRefused(f"cannot tokenize the block: {exc}") from exc
    insertions = []
    for line, byte_col, name in hits:
        col = len(lines[line - 1].encode("utf-8")[:byte_col].decode("utf-8"))
        if name_tokens.get((line, col)) != name:
            raise MoveRefused(f"{name!r} at line {line} has no matching name token (ast and tokenize disagree)")
        insertions.append((line, col, name))
    insertions.sort()
    for line, col, _ in reversed(insertions):
        text = lines[line - 1]
        lines[line - 1] = text[:col] + "game." + text[col:]
    return "\n".join(lines), insertions


def move(game_py: Path, part_py: Path, names: list[str], surface_targets: set[str], identity_allow=frozenset()) -> dict:
    """Cut the blocks that bind `names` out of game_py, append them (prefixed) to part_py, leave one import line.

    The import line takes the place of the first cut block. Both files are written only when every block was accepted.
    The part header (`import game`, stdlib and other non-engine imports) is written by hand; move() does not add it.
    surface_targets is used as given: the caller must first drop the patch-census targets marked `absent`.
    Names in NEVER_MOVED (spec section 5) are refused.
    identity_allow: (file, function, name) rows of identity_allowlist.json; the part's file is `<folder>/<file name>`.
    Returns {"blocks": [{"names", "game_span", "part_span"}], "insertions": [(part line, col, name)], "import_line"}.
    """
    game_py, part_py = Path(game_py), Path(part_py)
    for name in names:
        if name in NEVER_MOVED:
            raise MoveRefused(f"{name!r} never leaves game.py (spec section 5)")
    index = top_level_index(game_py)
    by_name = {entry["name"]: entry for entry in index}
    for name in names:
        if sum(1 for entry in index if entry["name"] == name) > 1:
            raise MoveRefused(f"{name!r} is bound more than once at top level; move it by hand")
    spans: dict[tuple[int, int], list[str]] = {}
    for name in names:
        entry = by_name.get(name)
        if entry is None or entry["kind"] not in MOVABLE_KINDS:
            raise MoveRefused(f"{name!r} is not a top-level function, class or constant of {game_py.name}")
        spans.setdefault((entry["start"], entry["end"]), [])
    for entry in index:  # a statement that binds several names moves whole
        if (entry["start"], entry["end"]) in spans:
            spans[(entry["start"], entry["end"])].append(entry["name"])
    for bound in spans.values():  # a never-moved name must not ride along with a requested one
        for name in bound:
            if name in NEVER_MOVED:
                raise MoveRefused(f"{name!r} never leaves game.py (spec section 5); it shares a statement with a moved name")
    ordered = sorted(spans)
    for (_, end), (start, _) in zip(ordered, ordered[1:]):
        if start <= end:
            raise MoveRefused(f"blocks overlap near line {start}")

    part_lines = part_py.read_bytes().decode("utf-8").split("\n") if part_py.exists() else [""]
    part_index = top_level_index(part_py) if part_py.exists() and part_py.read_bytes().strip() else []
    moved_names = [n for key in ordered for n in spans[key]]
    # names game.py re-exports from an earlier move (`from game_parts.<x> import ...`) are engine names too (F7 amended)
    reexports = {a.asname or a.name for node in ast.parse(game_py.read_text(encoding="utf-8")).body
                 if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("game_parts.") for a in node.names}
    engine_names = {e["name"] for e in index if e["kind"] in MOVABLE_KINDS} | reexports | set(surface_targets)
    in_part = {e["name"] for e in part_index if e["kind"] == "assign"} | {n for n in moved_names if by_name[n]["kind"] == "assign"}
    keep_bare = in_part - set(surface_targets)

    part_rel = f"{part_py.resolve().parent.name}/{part_py.name}"  # game_parts/<x>.py, as R6 names the file
    game_lines = game_py.read_bytes().decode("utf-8").split("\n")
    blocks, insertions, appended = [], [], list(part_lines[:-1]) if part_lines[-1] == "" else list(part_lines)
    for key in ordered:
        start, end = key
        text, ins = prefix_names("\n".join(game_lines[start - 1:end]) + "\n", engine_names, keep_bare, identity_allow,
                                 part_rel)
        if appended:
            appended.append("")  # one blank line between blocks
        first = len(appended) + 1
        appended.extend(text.split("\n")[:-1])
        insertions += [(first - 1 + line, col, name) for line, col, name in ins]
        blocks.append({"names": spans[key], "game_span": key, "part_span": (first, len(appended))})

    eol = "\r" if game_lines[ordered[0][1] - 1].endswith("\r") else ""
    import_line = f"from game_parts.{part_py.stem} import {', '.join(moved_names)}{eol}"
    kept = []
    for number, line in enumerate(game_lines, start=1):
        if number == ordered[0][0]:
            kept.append(import_line)
        if not any(s <= number <= e for s, e in ordered):
            kept.append(line)
    part_py.write_bytes(("\n".join(appended) + "\n").encode("utf-8"))
    game_py.write_bytes("\n".join(kept).encode("utf-8"))
    return {"blocks": blocks, "insertions": insertions, "import_line": ordered[0][0]}


def read_names(path: Path) -> list[str]:
    """Names from a file: one per line; blank lines are skipped."""
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--game", required=True, type=Path, help="game.py to cut the blocks from")
    ap.add_argument("--part", required=True, type=Path, help="game_parts/<x>.py to append the blocks to")
    names_group = ap.add_mutually_exclusive_group(required=True)
    names_group.add_argument("--names", help="a,b")
    names_group.add_argument("--names-file", type=Path, help="one name per line")
    ap.add_argument("--census", required=True, type=Path, help="patch_census.json lock; its `absent` targets are dropped")
    ap.add_argument("--report", type=Path, help="write move()'s result here as JSON")
    ap.add_argument("--identity-allowlist", type=Path, help="identity_allowlist.json; its rows let those identity uses move")
    args = ap.parse_args(argv)
    if args.names is not None:
        names = [name.strip() for name in args.names.split(",") if name.strip()]
    else:
        names = read_names(args.names_file)
    if not names:
        ap.error("no names given")
    targets = json.loads(args.census.read_text(encoding="utf-8"))["targets"]
    surface_targets = {name for name, kind in targets.items() if kind != "absent"}
    rows = json.loads(args.identity_allowlist.read_text(encoding="utf-8")) if args.identity_allowlist else []
    identity_allow = frozenset((row["file"], row["function"], row["name"]) for row in rows)
    try:
        result = move(args.game, args.part, names, surface_targets, identity_allow)
    except MoveRefused as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2
    moved = sum(len(block["names"]) for block in result["blocks"])
    print(f"MOVED names={moved} import_line={result['import_line']} insertions={len(result['insertions'])}")
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
