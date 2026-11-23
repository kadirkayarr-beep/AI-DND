"""In-place cut of one block out of a function into a helper in game_parts/<part>.py (turn split).

The block's source lines are cut byte for byte (dedented to the helper's body indent; lines inside multi-line strings
are never touched); the only change inside the block is `game.` before each free engine name (move_block's rule).
Class A (no return): `o1, o2 = game._NAME(i1=i1)`; class B (return, no outputs):
`_exit = game._NAME(...)`, `if _exit is not game._TURN_FALL_THROUGH: return _exit`. Class C, more than 5 outputs,
a hazard (the block rebinds a name a nested helper it calls reads), a conditionally bound input, or a helper of
151 lines or more is refused: `REFUSED <reason>` on stderr, exit 2, nothing written.
Run: python scripts/engine_split/cut_block.py --file F --function NAME[.NESTED] --anchor TEXT [--occurrence N]
     [--sub-anchor TEXT] --helper _NAME --part game_parts/X.py --census api/tests/engine_split_locks/patch_census.json
     [--report out.json]
F is a part file; game.py is found as F's folder's parent (or the working directory's game.py).
"""
from __future__ import annotations

import argparse
import ast
import builtins
import json
import symtable
import sys
from pathlib import Path

# A script run as a file has only its own folder on sys.path: add ai-dnd and ai-dnd/scripts (same as the tests).
if __name__ == "__main__":
    sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]

from engine_split.inventory import top_level_index  # noqa: E402
from engine_split.move_block import MoveRefused, prefix_names  # noqa: E402

FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
MAX_OUTPUTS = 5
LONG_FUNCTION_MIN = 151
SENTINEL = "_TURN_FALL_THROUGH"
SENTINEL_PART = "turn_cuts_common"
DYNAMIC = {"locals", "globals", "vars", "eval", "exec"}
LOOPS = (ast.For, ast.AsyncFor, ast.While)


# --- analysis (Scan, function_free, flow_stores are copied from the measure folder's block_io.py) ---

class Scan(ast.NodeVisitor):
    def __init__(self):
        self.loads: set[str] = set()
        self.stores: set[str] = set()
        self.nested: dict[str, set[str]] = {}  # nested fn name -> free names
        self.nonlocal_writes: set[str] = set()

    def visit_Name(self, node):
        (self.loads if isinstance(node.ctx, ast.Load) else self.stores).add(node.id)

    def _function(self, node, name):
        for d in getattr(node, "decorator_list", []):
            self.visit(d)
        for d in node.args.defaults + [x for x in node.args.kw_defaults if x]:
            self.visit(d)
        free, nonlocals = function_free(node)
        self.loads |= free
        self.stores |= nonlocals
        self.nonlocal_writes |= nonlocals
        if name:
            self.stores.add(name)
            self.nested[name] = free

    def visit_FunctionDef(self, node):
        self._function(node, node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        self._function(node, None)

    def visit_Assign(self, node):  # `name = lambda ...` is a nested helper too
        self.generic_visit(node)
        if isinstance(node.value, ast.Lambda) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            self.nested[node.targets[0].id] = function_free(node.value)[0]

    def visit_ClassDef(self, node):
        self.stores.add(node.name)
        for b in node.bases:
            self.visit(b)

    def _comp(self, node, elts):
        inner = Scan()
        targets: set[str] = set()
        for gen in node.generators:
            t = Scan()
            t.visit(gen.target)
            targets |= t.stores
            inner.visit(gen.iter)
            for cond in gen.ifs:
                inner.visit(cond)
        for e in elts:
            inner.visit(e)
        self.loads |= inner.loads - targets
        self.stores |= inner.stores - targets  # walrus leaks out
        self.nested.update(inner.nested)

    def visit_ListComp(self, node):
        self._comp(node, [node.elt])

    visit_SetComp = visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node):
        self._comp(node, [node.key, node.value])

    def visit_Import(self, node):
        for a in node.names:
            self.stores.add((a.asname or a.name).split(".")[0])

    visit_ImportFrom = visit_Import

    def visit_ExceptHandler(self, node):
        if node.name:
            self.stores.add(node.name)
        self.generic_visit(node)


def function_free(fn) -> tuple[set[str], set[str]]:
    a = fn.args
    params = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    if a.vararg:
        params.add(a.vararg.arg)
    if a.kwarg:
        params.add(a.kwarg.arg)
    s = Scan()
    nonlocals: set[str] = set()
    body = fn.body if isinstance(fn.body, list) else [fn.body]
    for st in body:
        for n in ast.walk(st):
            if isinstance(n, ast.Nonlocal):
                nonlocals |= set(n.names)
        s.visit(st)
    local = (s.stores - nonlocals) | params
    return (s.loads - local) | nonlocals, nonlocals


def stores_of(node) -> set[str]:
    s = Scan()
    s.visit(node)
    return s.stores


def flow_stores(stmts) -> tuple[set[str], bool]:
    """Names that may still be bound when control leaves `stmts` by falling off the end (return/raise paths excluded)."""
    out: set[str] = set()
    for st in stmts:
        if isinstance(st, (ast.Return, ast.Raise)):
            return out | stores_of(st), True
        if isinstance(st, ast.If):
            test = stores_of(st.test)
            b, tb = flow_stores(st.body)
            o, to = flow_stores(st.orelse)
            out |= test | (set() if tb else b) | (set() if to else o)
            if tb and to:
                return out, True
        elif isinstance(st, (ast.With, ast.AsyncWith)):
            b, tb = flow_stores(st.body)
            out |= b | set().union(*[stores_of(i) for i in st.items] or [set()])
            if tb:
                return out, True
        else:
            out |= stores_of(st)
    return out, False


# --- definite assignment and upward-exposed reads ---

def scope_walk(nodes):
    """Every node of one scope; a nested def, lambda or class is yielded but not entered."""
    for n in nodes:
        yield n
        if not isinstance(n, SCOPES):
            yield from scope_walk(ast.iter_child_nodes(n))


def params_of(fn) -> set[str]:
    a = fn.args
    names = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    names |= {x.arg for x in (a.vararg, a.kwarg) if x}
    return names


def _definite_stores(st) -> set[str]:
    walrus = {n.target.id for n in ast.walk(st) if isinstance(n, ast.NamedExpr)}
    return stores_of(st) - walrus


def _reads(node) -> set[str]:
    s = Scan()
    s.visit(node)
    return s.loads


def exposure(stmts, assigned: set[str]):
    """(names read before the block binds them, names definitely bound afterwards or None when the path ends)."""
    exposed: set[str] = set()
    a = set(assigned)
    for st in stmts:
        e, a2 = _exposure_stmt(st, a)
        exposed |= e
        if a2 is None:
            return exposed, None
        a = a2
    return exposed, a


def _exposure_stmt(st, a: set[str]):
    if isinstance(st, (ast.Return, ast.Raise)):
        return _reads(st) - a, None
    if isinstance(st, (ast.Break, ast.Continue)):
        return set(), None
    if isinstance(st, ast.If):
        e = _reads(st.test) - a
        e1, a1 = exposure(st.body, a)
        e2, a2 = exposure(st.orelse, a)
        live = [x for x in (a1, a2) if x is not None]
        after = None if not live else set.intersection(*live)
        return e | e1 | e2, after
    if isinstance(st, (ast.For, ast.AsyncFor)):
        e = _reads(st.iter) - a
        e1, _ = exposure(st.body, a | stores_of(st.target))
        e2, _ = exposure(st.orelse, a)
        return e | e1 | e2, a
    if isinstance(st, ast.While):
        e = _reads(st.test) - a
        e1, _ = exposure(st.body, a)
        e2, _ = exposure(st.orelse, a)
        return e | e1 | e2, a
    if isinstance(st, (ast.With, ast.AsyncWith)):
        e: set[str] = set()
        cur = set(a)
        for item in st.items:
            e |= _reads(item.context_expr) - cur
            if item.optional_vars is not None:
                cur |= stores_of(item.optional_vars)
        e1, after = exposure(st.body, cur)
        return e | e1, after
    if isinstance(st, ast.Try) or type(st).__name__ == "TryStar":
        e1, ab = exposure(st.body, a)
        e: set[str] = set(e1)
        for h in st.handlers:
            if h.type is not None:
                e |= _reads(h.type) - a
            eh, _ = exposure(h.body, a | ({h.name} if h.name else set()))
            e |= eh
        e2, _ = exposure(st.orelse, ab if ab is not None else a)
        ef, _ = exposure(st.finalbody, a)
        return e | e2 | ef, a
    if type(st).__name__ == "Match":
        return _reads(st) - a, a
    reads = _reads(st)
    if isinstance(st, ast.AugAssign) and isinstance(st.target, ast.Name):
        reads = reads | {st.target.id}
    return reads - a, a | _definite_stores(st)


def _children(st):
    """(entry-set extension, statement list) for each child list of a compound statement."""
    if isinstance(st, ast.If):
        return [(set(), st.body), (set(), st.orelse)]
    if isinstance(st, (ast.For, ast.AsyncFor)):
        return [(stores_of(st.target), st.body), (set(), st.orelse)]
    if isinstance(st, ast.While):
        return [(set(), st.body), (set(), st.orelse)]
    if isinstance(st, (ast.With, ast.AsyncWith)):
        return [(set().union(*[stores_of(i.optional_vars) for i in st.items if i.optional_vars] or [set()]), st.body)]
    if isinstance(st, ast.Try) or type(st).__name__ == "TryStar":
        return ([(set(), st.body)] + [({h.name} if h.name else set(), h.body) for h in st.handlers]
                + [(set(), st.orelse), (set(), st.finalbody)])
    if type(st).__name__ == "Match":
        return [(set(), c.body) for c in st.cases]
    return []


def assigned_before(stmts, target, a: set[str]):
    """Names definitely bound where `target` starts, or None when `target` is not inside `stmts`."""
    for st in stmts:
        if st is target:
            return a
        if any(n is target for n in scope_walk([st])):
            for extra, lst in _children(st):
                r = assigned_before(lst, target, a | extra)
                if r is not None:
                    return r
            return None
        _, a2 = _exposure_stmt(st, a)
        a = a if a2 is None else a2
    return None


# --- locating the block ---

def find_function(tree, dotted: str) -> list:
    chain, body = [], tree.body
    for name in dotted.split("."):
        fn = next((n for n in scope_walk(body) if isinstance(n, FUNCTIONS) and n.name == name), None)
        if fn is None:
            raise MoveRefused(f"function {name!r} not found")
        chain.append(fn)
        body = fn.body
    return chain


def locate_block(text: str, function: str, anchor: str, occurrence: int | None = None, sub_anchor: str | None = None):
    """(function chain, statement, first line, last line); the first line includes the comment block directly above."""
    lines = text.split("\n")
    chain = find_function(ast.parse(text), function)
    body = chain[-1].body
    if sub_anchor:
        subs = [n for n in scope_walk(body) if isinstance(n, ast.stmt) and not isinstance(n, SCOPES)
                and hasattr(n, "body") and lines[n.lineno - 1].strip().startswith(sub_anchor.strip())]
        if len(subs) != 1:
            raise MoveRefused(f"sub-anchor {sub_anchor!r} matches {len(subs)} statements; expected exactly one")
        body = subs[0].body
    matches = [st for st in body if lines[st.lineno - 1].strip().startswith(anchor.strip())]
    if not matches:
        raise MoveRefused(f"anchor {anchor!r} not found")
    if occurrence is None and len(matches) > 1:
        raise MoveRefused(f"anchor {anchor!r} is ambiguous ({len(matches)} matches); give --occurrence")
    if occurrence is not None and not 1 <= occurrence <= len(matches):
        raise MoveRefused(f"anchor {anchor!r} has {len(matches)} matches; --occurrence {occurrence} does not exist")
    st = matches[(occurrence or 1) - 1]
    start = st.lineno
    indent = len(lines[start - 1]) - len(lines[start - 1].lstrip())
    while start > 1:
        prev = lines[start - 2].rstrip("\r")
        if prev.strip().startswith("#") and len(prev) - len(prev.lstrip()) == indent:
            start -= 1
        else:
            break
    return chain, st, start, st.end_lineno


def call_lines(indent: str, cls: str, helper: str, params: list[str], outputs: list[str]) -> list[str]:
    call = f"game.{helper}({', '.join(f'{p}={p}' for p in params)})"
    if cls == "B":
        return [f"{indent}_exit = {call}", f"{indent}if _exit is not game.{SENTINEL}:", f"{indent}    return _exit"]
    if outputs:
        return [f"{indent}{', '.join(outputs)} = {call}"]
    return [f"{indent}{call}"]


# --- the cut ---

def _loose_jump(node, in_loop=False):
    if isinstance(node, (ast.Break, ast.Continue)):
        return not in_loop
    if isinstance(node, SCOPES):
        return False
    inner = in_loop or isinstance(node, LOOPS)
    return any(_loose_jump(c, inner) for c in ast.iter_child_nodes(node))


def _forbidden(block) -> str | None:
    for n in ast.walk(block):
        if isinstance(n, (ast.Yield, ast.YieldFrom, ast.Await, ast.Global, ast.Nonlocal)):
            return type(n).__name__.lower()
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in DYNAMIC:
            return f"{n.func.id}()"
    if _loose_jump(block):
        return "break/continue leaving the block"
    return None


def _has_return(node) -> bool:
    if isinstance(node, ast.Return):
        return True
    if isinstance(node, SCOPES):
        return False
    return any(_has_return(c) for c in ast.iter_child_nodes(node))


def analyse(text: str, chain, st) -> dict:
    """Class, parameters and outputs of the block `st` inside chain[-1]; raises MoveRefused."""
    fn = chain[-1]
    reason = _forbidden(st)
    if reason:
        raise MoveRefused(f"forbidden construct: {reason}")
    if isinstance(st, SCOPES):
        raise MoveRefused("class D: a nested def or class is lifted by the shim pattern, not cut")
    scan = Scan()
    for s in fn.body:
        scan.visit(s)
    nested = scan.nested
    local = scan.stores | params_of(fn)
    outer: set[str] = set()
    for f in chain[:-1]:
        sc = Scan()
        for s in f.body:
            sc.visit(s)
        outer |= sc.stores | params_of(f)
    outer -= local
    has_return = _has_return(st)
    block_scan = Scan()
    block_scan.visit(st)
    # outputs: names that may be bound when the block falls off its end and that code after it (or a nested helper
    # called after it, or anything in an enclosing loop) reads
    later: set[str] = set()
    loop_ancestors = [n for n in scope_walk(fn.body) if isinstance(n, LOOPS) and any(m is st for m in scope_walk([n]))]
    for n in scope_walk(fn.body):
        if isinstance(n, ast.stmt) and n.lineno > st.end_lineno:
            later |= _reads(n)
    for lp in loop_ancestors:
        later |= _reads(lp)
    todo = list(later & set(nested))
    while todo:
        for f in nested[todo.pop()]:
            if f not in later:
                later.add(f)
                if f in nested:
                    todo.append(f)
    flow, _ = flow_stores([st])
    outputs = sorted(flow & later & (local | outer))
    if has_return and outputs:
        raise MoveRefused(f"class C: the block has a return and {len(outputs)} outputs")
    if len(outputs) > MAX_OUTPUTS:
        raise MoveRefused(f"{len(outputs)} outputs (more than {MAX_OUTPUTS})")
    called = [k for k in block_scan.loads if k in nested]
    hazard = sorted(block_scan.stores & set().union(*[nested[k] for k in called] or [set()]))
    if hazard:
        raise MoveRefused(f"hazard {' '.join(hazard)}")
    exposed, after = exposure([st], set())
    needed = set(exposed)
    if after is not None:
        needed |= set(outputs) - after  # a conditionally rebound output also needs its old value
    before = assigned_before(fn.body, st, params_of(fn))
    inputs = []
    for name in sorted(needed):
        if name in local:
            if name not in before:
                raise MoveRefused(f"conditional input {name}: not bound on every path before the block")
            inputs.append(name)
        elif name in outer:
            inputs.append(name)
    params = sorted(set(inputs))
    return {"class": "B" if has_return else "A", "params": params, "outputs": outputs, "local": local | outer}


def _dedent(lines: list[str], shift: int, protected: set[int], first_line: int) -> list[str]:
    out = []
    for i, line in enumerate(lines):
        if first_line + i in protected or shift <= 0:
            out.append(line)
            continue
        k = 0
        while k < shift and k < len(line) and line[k] == " ":
            k += 1
        if k < shift and k < len(line) and line[k] == "\t":
            raise MoveRefused("tab indentation")
        out.append(line[k:])
    return out


def _bound_at_top(text: str) -> dict[str, ast.stmt]:
    out = {}
    for node in ast.parse(text).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                out[(a.asname or a.name).split(".")[0] if isinstance(node, ast.Import) else (a.asname or a.name)] = node
        else:
            for name in stores_of(node) if not isinstance(node, SCOPES) else {node.name}:
                out[name] = node
    return out


def _all_symbols(table, kind) -> set[str]:
    out = {s.get_name() for s in table.get_symbols() if getattr(s, kind)()}
    for c in table.get_children():
        out |= _all_symbols(c, kind)
    return out


def _split(data: bytes) -> list[str]:
    return data.decode("utf-8").split("\n")


def _read(files: dict[Path, str], path: Path) -> str:
    if path not in files:
        files[path] = path.read_bytes().decode("utf-8") if path.exists() else ""
    return files[path]


def _part_modules_insert(game_text: str, module: str) -> str:
    tree = ast.parse(game_text)
    node = next((n for n in tree.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "_PART_MODULES" for t in n.targets)), None)
    if node is None or not isinstance(node.value, (ast.Tuple, ast.List)):
        raise MoveRefused("game.py has no _PART_MODULES tuple")
    if any(isinstance(e, ast.Constant) and e.value == module for e in node.value.elts):
        return game_text
    lines = game_text.split("\n")

    def offset(line, col):
        return sum(len(l) + 1 for l in lines[:line - 1]) + len(lines[line - 1].encode()[:col].decode())

    item = f'"{module}"'
    later = next((e for e in node.value.elts if isinstance(e, ast.Constant) and e.value > module), None)
    if later is not None:
        pos = offset(later.lineno, later.col_offset)
        return game_text[:pos] + item + ", " + game_text[pos:]
    last = node.value.elts[-1]
    pos = offset(last.end_lineno, last.end_col_offset)
    return game_text[:pos] + ", " + item + game_text[pos:]


def _reexport_insert(game_text: str, module: str, names: str) -> str:
    tree = ast.parse(game_text)
    anchor = next((n for n in tree.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "_PART_MODULES" for t in n.targets)), None)
    if anchor is None:
        raise MoveRefused("game.py has no _PART_MODULES tuple")
    prior = [n for n in tree.body if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("game_parts.")
             and n.end_lineno < anchor.lineno]
    if not prior:
        raise MoveRefused("game.py has no `from game_parts.` import before _PART_MODULES")
    lines = game_text.split("\n")
    eol = "\r" if lines[0].endswith("\r") else ""
    lines.insert(prior[-1].end_lineno, f"from game_parts.{module} import {names}{eol}")
    return "\n".join(lines)


def cut(file: Path, function: str, anchor: str, helper: str, part: Path, census: Path, occurrence=None,
        sub_anchor=None) -> dict:
    """Do the cut and write the files; returns the report row. Raises MoveRefused (nothing written)."""
    file, part = Path(file).resolve(), Path(part).resolve()
    if file.name == "game.py":
        raise MoveRefused("game.py itself: move the function into a part first")
    game_py = file.parent.parent / "game.py"
    if not game_py.exists():
        game_py = Path("game.py").resolve()
    files: dict[Path, str] = {}
    text = _read(files, file)
    chain, st, start, end = locate_block(text, function, anchor, occurrence, sub_anchor)
    info = analyse(text, chain, st)
    cls, params, outputs = info["class"], info["params"], info["outputs"]
    lines = text.split("\n")
    indent_n = len(lines[st.lineno - 1]) - len(lines[st.lineno - 1].lstrip())
    indent = lines[st.lineno - 1][:indent_n]
    if "_exit" in info["local"] and cls == "B":
        raise MoveRefused("the function already uses the name _exit")
    if not helper.startswith("_") or not helper.isidentifier():
        raise MoveRefused(f"bad helper name {helper!r}")
    game_text = _read(files, game_py)
    game_index = top_level_index(game_py)
    if helper in {e["name"] for e in game_index} | set(_bound_at_top(text)) | set(_bound_at_top(_read(files, part) or "\n")):
        raise MoveRefused(f"helper name {helper} is already bound")
    eol = "\r" if lines[0].endswith("\r") else ""
    block_lines = lines[start - 1:end]
    protected = _string_lines(lines, st)
    body = _dedent(block_lines, indent_n - 4, protected, start)
    head = f"def {helper}({'*, ' + ', '.join(params) if params else ''}):{eol}"
    if cls == "B":
        tail = [f"    return game.{SENTINEL}{eol}"]
    elif outputs:
        tail = [f"    return {', '.join(outputs)}{eol}"]
    else:
        tail = []
    helper_text = "\n".join([head, *body, *tail])
    # `game.` prefix on free engine names (move_block's rule)
    census_targets = json.loads(Path(census).read_text(encoding="utf-8"))["targets"]
    surface = {n for n, k in census_targets.items() if k != "absent"}
    reexports = {a.asname or a.name for node in ast.parse(game_text).body
                 if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("game_parts.") for a in node.names}
    engine_names = {e["name"] for e in game_index if e["kind"] in ("function", "class", "assign")} | reexports | surface
    part_text = _read(files, part)
    in_part = {n for n, node in _bound_at_top(part_text or "\n").items() if isinstance(node, ast.Assign)}
    part_rel = f"{part.parent.name}/{part.name}"
    helper_text, _ = prefix_names(helper_text + "\n", engine_names, in_part - surface, frozenset(), part_rel)
    helper_text = helper_text.rstrip("\n")
    if helper_text.count("\n") + 1 >= LONG_FUNCTION_MIN:
        raise MoveRefused(f"the helper would have {helper_text.count(chr(10)) + 1} lines (limit {LONG_FUNCTION_MIN - 1})")
    # names the helper reads that the part does not bind: copy the source file's import or refuse
    table = symtable.symtable(helper_text.replace("\r", "") + "\n", "<helper>", "exec")
    free_globals = _all_symbols(table, "is_global") - set(dir(builtins)) - {"game", helper}
    part_bound = set(_bound_at_top(part_text or "\n")) if part_text.strip() else set()
    src_bound = _bound_at_top(text)
    copy_lines: list[str] = []
    for name in sorted(free_globals - part_bound):
        node = src_bound.get(name)
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            raise MoveRefused(f"name {name} is not bound in {part.name} and is no import of {file.name}")
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("game_parts"):
            raise MoveRefused(f"name {name} comes from a part ({node.module}); a part never imports a part")
        seg = "\n".join(lines[node.lineno - 1:node.end_lineno])
        if seg not in copy_lines:
            copy_lines.append(seg)
    # assemble the edits
    cl = [c + eol for c in call_lines(indent, cls, helper, params, outputs)]
    src_new = "\n".join(lines[:start - 1] + cl + lines[end:])
    cur = src_new if part == file else part_text
    if not cur.strip():
        cur = f"import game{eol}\n"
    elif "game" not in part_bound:
        cur = f"import game{eol}\n" + cur
    for c in copy_lines:
        if c not in cur:
            cur = c.replace("\n", eol + "\n") + eol + "\n" + cur
    files[part] = cur.rstrip("\n") + "\n\n\n" + helper_text + "\n"
    if part != file:
        files[file] = src_new
    g = game_text
    modules_needed = [(part.stem, helper)]
    if cls == "B" and SENTINEL not in {e["name"] for e in game_index} | reexports:
        common = part.parent / f"{SENTINEL_PART}.py"
        files[common] = f"{SENTINEL} = object(){eol}\n"
        modules_needed.append((SENTINEL_PART, SENTINEL))
    for module, names in modules_needed:
        g = _reexport_insert(g, module, names)
        g = _part_modules_insert(g, f"game_parts.{module}")
    files[game_py] = g
    for path, content in files.items():
        path.write_bytes(content.encode("utf-8"))
    root = game_py.parent
    return {"file": file.relative_to(root).as_posix(), "function": function, "anchor": anchor, "occurrence": occurrence,
            "sub_anchor": sub_anchor, "helper": helper, "part": part.relative_to(root).as_posix(), "class": cls,
            "params": params, "outputs": outputs,
            "block": "\n".join(l.rstrip("\r") for l in lines[start - 1:end]), "indent": indent}


def _string_lines(lines: list[str], st) -> set[int]:
    """Absolute 1-based line numbers (inside the statement) that continue a multi-line string."""
    prot: set[int] = set()
    # parse the statement alone: dedent its lines to column 0 first (string bodies are not read, only line spans)
    first = lines[st.lineno - 1]
    shift = len(first) - len(first.lstrip())
    text = "\n".join(l[shift:] if l[:shift].strip() == "" else l.lstrip() for l in lines[st.lineno - 1:st.end_lineno])
    try:
        tree = ast.parse(text.replace("\r", ""))
    except SyntaxError:
        return prot
    for n in ast.walk(tree):
        if isinstance(n, (ast.Constant, ast.JoinedStr)) and n.end_lineno > n.lineno:
            if isinstance(n, ast.JoinedStr) or isinstance(n.value, (str, bytes)):
                prot |= set(range(st.lineno + n.lineno, st.lineno + n.end_lineno))
    return prot


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", required=True, type=Path)
    ap.add_argument("--function", required=True)
    ap.add_argument("--anchor", required=True)
    ap.add_argument("--occurrence", type=int)
    ap.add_argument("--sub-anchor")
    ap.add_argument("--helper", required=True)
    ap.add_argument("--part", required=True, type=Path)
    ap.add_argument("--census", required=True, type=Path)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)
    try:
        row = cut(args.file, args.function, args.anchor, args.helper, args.part, args.census, args.occurrence,
                  args.sub_anchor)
    except (MoveRefused, SyntaxError) as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2
    print(f"CUT {row['helper']} class={row['class']} params={len(row['params'])} outputs={len(row['outputs'])}")
    if args.report:
        rows = json.loads(args.report.read_text(encoding="utf-8"))["helpers"] if args.report.exists() else []
        args.report.write_text(json.dumps({"helpers": rows + [row]}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
