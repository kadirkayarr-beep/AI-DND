"""Turn-split block inventory (read-only measurement, no engine change).

Usage:
    python -I block_io.py <source.py> <function> [<nested function>] [--label TEXT]

For every top-level statement of the target function body it prints:
  line range, statement kind, inputs (names read that a parameter or an
  earlier block defined), outputs (names written that a later block reads),
  return/raise points (outside nested defs), late closure reads, and
  marker hits for money, save, Undo, session writes and model calls.

"Read" includes the free names of nested functions the block defines or
calls (closure reads happen at call time), so a name a nested helper reads
counts as read by every block that calls the helper.  Comprehension targets
are local to the comprehension and are not counted.  Outputs count only stores
that can reach the end of the block on a path without return/raise.  The script never
imports the measured module.
"""
from __future__ import annotations

import ast
import json
import re
import sys

MARKERS = {
    "money": re.compile(r"settled_money|money|coin|gold|shop|price|receipt|ledger|purchase|wallet", re.I),
    "save": re.compile(r"save_result|save_game|autosave|persist|campaign_store|\bcommit\(|\bsaved\b", re.I),
    "undo": re.compile(r"undo|snapshot|rollback|_restore_runtime", re.I),
    "session_write": re.compile(r"_session\(\)\.\w+(\.\w+)*\s*(=(?!=)|\+=|-=)|_session\(\)\.\w+\.(append|update|pop|clear|extend|setdefault)\("),
    "model": re.compile(r"ask_dm|ask_dungeon_master|model_calls|_model\b|llm|chat_completion", re.I),
    "locals()": re.compile(r"\blocals\(\)"),
}


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
    """Names that may still be bound when control leaves `stmts` by falling off the end.

    A path that ends in return/raise does not count: its stores never reach a later block.
    If/With are followed; loops and try are taken whole and never counted as terminating.
    """
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


def exits(node) -> tuple[int, int]:
    r = x = 0
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)) and n is not node:
            continue
        if isinstance(n, ast.Return):
            r += 1
        elif isinstance(n, ast.Raise):
            x += 1
        stack.extend(ast.iter_child_nodes(n))
    return r, x


def kind(st, lines) -> str:
    if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"def {st.name}"
    head = lines[st.lineno - 1].strip()
    return head[:70]


def find(tree, names):
    scope = tree.body
    fn = None
    for name in names:
        fn = next(n for n in scope if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
        scope = fn.body
    return fn


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    label = ""
    if "--label" in argv:
        i = argv.index("--label")
        label = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    sub = None
    if "--sub" in argv:
        i = argv.index("--sub")
        sub = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    path, names = argv[0], argv[1:]
    src = open(path, encoding="utf-8").read()
    lines = src.splitlines()
    fn = find(ast.parse(src), names)
    a = fn.args
    params = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    nested_free: dict[str, set[str]] = {}

    def build(stmts):
        out = []
        for st in stmts:
            s = Scan()
            s.visit(st)
            nested_free.update(s.nested)
            end = st.end_lineno
            seg = "\n".join(lines[st.lineno - 1:end])
            r, x = exits(st)
            out.append({
                "start": st.lineno, "end": end, "n": end - st.lineno + 1,
                "kind": kind(st, lines), "loads": s.loads, "stores": s.stores, "flow": flow_stores([st])[0],
                "nonlocal": s.nonlocal_writes, "returns": r, "raises": x,
                "markers": {k: len(p.findall(seg)) for k, p in MARKERS.items() if p.search(seg)},
            })
        return out

    # effective reads: direct loads plus free names of nested helpers loaded (transitive)
    def expand(names_):
        out, todo = set(names_), list(names_)
        while todo:
            n = todo.pop()
            for f in nested_free.get(n, ()):
                if f not in out:
                    out.add(f)
                    todo.append(f)
        return out

    def finish(blocks, defined, later_extra):
        for b in blocks:
            b["reads"] = expand(b["loads"])
        for i, b in enumerate(blocks):
            later = set(later_extra).union(*[c["reads"] for c in blocks[i + 1:]])
            b["inputs"] = sorted(b["reads"] & defined)
            b["direct_in"] = len(b["loads"] & defined)
            b["outputs"] = sorted(b["flow"] & later)  # only stores that can reach the block end
            free_here = set().union(*[nested_free[k] for k in b["stores"] if k in nested_free] or [set()])
            later_stores = set().union(*[c["stores"] for c in blocks[i + 1:]] or [set()])
            b["late_closure"] = sorted((free_here - defined - b["stores"]) & later_stores)
            defined |= b["stores"]

    top = build(fn.body)
    finish(top, set(params), set())
    blocks = top
    if sub is not None:
        # --sub LINE: the body of the compound statement starting at LINE,
        # anywhere inside the function.  "Defined before" = parameters plus
        # every name stored on an earlier line; "read later" = top-level
        # blocks after the containing one plus loads in the containing block
        # after LINE's end (line-order approximation; loops are not modelled).
        k = max(i for i, st in enumerate(fn.body) if st.lineno <= sub)
        node = next(n for n in ast.walk(fn.body[k]) if isinstance(n, ast.stmt) and n.lineno == sub and hasattr(n, "body"))
        before = set(params)
        after_loads = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Name):
                if not isinstance(n.ctx, ast.Load) and n.lineno < sub:
                    before.add(n.id)
                elif isinstance(n.ctx, ast.Load) and node.end_lineno < n.lineno <= fn.body[k].end_lineno:
                    after_loads.add(n.id)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not fn and n.lineno < sub:
                before.add(n.name)
        blocks = build(node.body)
        finish(blocks, before, expand(after_loads).union(*[b["reads"] for b in top[k + 1:]]))
        names = names + [f"block@{sub}.body"]
    total = fn.end_lineno - fn.lineno + 1
    print(f"# {label or path} :: {'.'.join(names)}  lines {fn.lineno}-{fn.end_lineno} ({total})  blocks={len(blocks)}")
    print("idx | lines | n | kind | in(direct) | out | ret/raise | markers | outputs | late-closure | inputs | nonlocal")
    for i, b in enumerate(blocks):
        mk = ",".join(f"{k}:{v}" for k, v in b["markers"].items())
        print(f"{i:3} | {b['start']}-{b['end']} | {b['n']} | {b['kind']} | {len(b['inputs'])}({b['direct_in']}) | {len(b['outputs'])} "
              f"| {b['returns']}/{b['raises']} | {mk} | {' '.join(b['outputs'])} | {' '.join(b['late_closure'])} | {' '.join(b['inputs'])} | {' '.join(sorted(b['nonlocal']))}")
    elig = [i for i, b in enumerate(blocks) if len(b["outputs"]) <= 5]
    big = [b for b in blocks if b["n"] >= 20]
    summary = {
        "target": ".".join(names), "label": label, "lines": total, "blocks": len(blocks),
        "blocks_ge20_lines": len(big),
        "blocks_ge20_out_le5": sum(1 for b in big if len(b["outputs"]) <= 5),
        "lines_in_ge20_out_le5": sum(b["n"] for b in big if len(b["outputs"]) <= 5),
        "blocks_out_le5": len(elig),
        "blocks_with_return": sum(1 for b in blocks if b["returns"]),
        "returns": sum(b["returns"] for b in blocks), "raises": sum(b["raises"] for b in blocks),
        "nested_defs": sorted(nested_free),
        "blocks_touching": {k: sum(1 for b in blocks if k in b["markers"]) for k in MARKERS},
    }
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False))
    # Cut classes (plan "Cut rule"): A = no return, outputs <= 5; B = returns, no outputs;
    # C = returns and outputs (not cut whole).  Hazard = the block calls a nested helper
    # and rebinds a name that helper reads from the enclosing scope (the extracted copy
    # would hand the helper the old binding).  Only blocks of MIN_CUT lines or more listed.
    min_cut = 10
    rows = []
    for i, b in enumerate(blocks):
        called = [k for k in b["loads"] if k in nested_free]
        hazard = sorted(b["stores"] & set().union(*[nested_free[k] for k in called] or [set()]))
        if b["kind"].startswith("def "):
            cls = "D"  # nested def: handled by the shim pattern, not by block extraction
        elif b["returns"] == 0:
            cls = "A"
        elif not b["outputs"]:
            cls = "B"
        else:
            cls = "C"
        ok = cls in "AB" and len(b["outputs"]) <= 5 and not hazard and "locals()" not in b["markers"]
        b.update(cls=cls, hazard=hazard, ok=ok)
        if b["n"] >= min_cut:
            rows.append(b)
    for b in rows:
        flags = [k for k in ("money", "save", "undo", "session_write", "model") if k in b["markers"]]
        print(f"CUT {'yes' if b['ok'] else 'no '} {b['cls']} {b['start']}-{b['end']} n={b['n']} out={len(b['outputs'])} "
              f"ret={b['returns']} hazard={','.join(b['hazard']) or '-'} flags={','.join(flags) or '-'} :: {b['kind'][:50]}")
    yes = [b for b in rows if b["ok"]]
    print("CUTSUM " + json.dumps({
        "rows_ge_min": len(rows), "cut_yes": len(yes), "cut_yes_lines": sum(b["n"] for b in yes),
        "by_class": {c: sum(1 for b in rows if b["cls"] == c) for c in "ABCD"},
        "hazard_blocks": sum(1 for b in rows if b["hazard"]),
    }))


if __name__ == "__main__":
    main(sys.argv[1:])
