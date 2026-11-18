"""N3 routing audit for the engine split: seven static rules every file in ai-dnd/game_parts obeys (spec section 6, N3).

Read-only: parses with ast and symtable and never rewrites a source file. audit() returns the findings, each
`R<n> <file>:<line>: <what>`; an empty list means clean.
Run: python scripts/engine_split/routing_audit.py                                  (findings; exit 1 when any)
     python scripts/engine_split/routing_audit.py --write-allowed-imports <path>   (Task 17 only: freeze the R1 lock)
The lock equals engine_imports() (game.py + parts); a test asserts equality, so no module can be appended quietly.
"""
from __future__ import annotations

import argparse
import ast
import builtins
import dis
import json
import re
import symtable
import sys
from dataclasses import dataclass
from pathlib import Path
from types import CodeType

ROOT = Path(__file__).resolve().parents[2]
LOCKS = ROOT / "api" / "tests" / "engine_split_locks"

IDENTITY_NAMES = {"__file__", "__name__", "globals", "locals", "vars"}  # R6, plus sys.modules
MODULE_DUNDERS = {"__name__", "__file__", "__doc__", "__spec__", "__loader__", "__package__", "__builtins__", "__cached__"}
KNOWN = set(dir(builtins)) | MODULE_DUNDERS  # always defined in a module; R6 handles the identity ones
SKIP_PARTS = {"docs", "__pycache__"}  # same skip rule as patch_census (F2): these differ between the slot and CI
COMPREHENSIONS = {ast.ListComp: "listcomp", ast.SetComp: "setcomp", ast.DictComp: "dictcomp", ast.GeneratorExp: "genexpr"}
DEFINING_KINDS = {"def", "class", "assign"}  # how a moved definition is bound (R3 allows these only, and only when re-exported)
GAME_PARTS_IMPORT = re.compile(r"^\s*(?:from|import)\s+game_parts\b", re.MULTILINE)
GAME_PARTS_STRING = re.compile(r"^game_parts\.\w")  # a dotted part path: patch(...), resolve_name(...), sys.modules[...]
EXEC_NAMES = {"eval", "exec"}  # code the audit cannot see (game.py has none)
# bytecode reads that resolve through module globals (names differ by Python version; only those that exist are used)
GLOBAL_LOADS = {name for name in ("LOAD_GLOBAL", "LOAD_NAME", "LOAD_FROM_DICT_OR_GLOBALS") if name in dis.opmap}


@dataclass
class _Bind:
    name: str
    line: int
    kind: str
    module_level: bool  # lands in the module namespace (module scope, or a `global` name)
    via_global: bool


@dataclass
class _Use:
    name: str
    line: int
    in_function: bool   # inside a def or lambda body: runs after import
    where: str | None   # "default", "decorator" or "annotation": evaluated where the def/lambda is
    module_assign: bool  # inside a module-level assignment statement
    function: str       # dotted def/class chain, "<module>" at the top


class _Walker:
    """Walks one module and records, with the scope symtable gives each name, the facts the rules read."""

    def __init__(self, tree: ast.Module, top: symtable.SymbolTable):
        self.top = top
        self.table = top
        self.extra_locals: set[str] = set()  # targets of comprehensions that 3.12+ inlines (no symtable child)
        self.in_function = False
        self.where: str | None = None
        self.module_assign = False
        self.bind_kind: str | None = None
        self.qual: list[str] = []
        self.used: dict[int, tuple] = {}  # id(table) -> (table, used child indexes); holds the table so its id stays unique
        self.reads: list[_Use] = []          # global (module or builtin) name reads
        self.binds: list[_Bind] = []
        self.game_attrs: list[tuple[_Use, str, bool]] = []  # (use, attribute, is_load)
        self.bare_game: list[_Use] = []
        self.identity: list[_Use] = []       # sys.modules and `from sys import modules`
        self.imports: list[ast.Import | ast.ImportFrom] = []
        self.dynamic_imports: list[tuple[int, str | None]] = []
        self.globals: list[tuple[str, int]] = []
        self.stars: list[int] = []
        self.internal: list[tuple[int, str]] = []
        # module aliases are collected before the walk: a function body may use `sys` imported further down
        imported = [(a.name, a.asname or a.name) for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        self.sys_names: set[str] = {bound for name, bound in imported if name == "sys"}
        self.importlib_names: set[str] = {bound for name, bound in imported if name == "importlib"}
        self.import_module_names: set[str] = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                                              and n.level == 0 and n.module == "importlib"
                                              for a in n.names if a.name == "import_module"}
        for stmt in tree.body:
            self.walk(stmt)

    # ---- scope facts -------------------------------------------------------------------------
    def _is_global(self, name: str) -> bool:
        if name in self.extra_locals:
            return False
        if self.table is self.top:
            return True
        try:
            return self.table.lookup(name).is_global()
        except KeyError:  # not seen in this table (3.14 annotation scopes): resolve conservatively as global
            return True

    def _declared_global(self, name: str) -> bool:
        if self.table is self.top or name in self.extra_locals:
            return False
        try:
            return self.table.lookup(name).is_declared_global()
        except KeyError:
            return False

    def _child(self, name: str, line: int):
        used = self.used.setdefault(id(self.table), (self.table, set()))[1]
        for index, child in enumerate(self.table.get_children()):
            if index not in used and child.get_name() == name and child.get_lineno() == line:
                used.add(index)
                return child
        return None

    def _use(self, name: str, line: int) -> _Use:
        return _Use(name, line, self.in_function, self.where, self.module_assign, ".".join(self.qual) or "<module>")

    def _bind(self, name: str, line: int, kind: str):
        at_top = self.table is self.top and name not in self.extra_locals
        via_global = self._declared_global(name)
        self.binds.append(_Bind(name, line, kind, at_top or via_global, via_global))

    def _scoped(self, table, extra: set[str], in_function: bool, qual: list[str], body):
        saved = (self.table, self.extra_locals, self.in_function, self.where, self.module_assign, self.qual, self.bind_kind)
        self.table, self.extra_locals, self.in_function, self.qual = table, extra, in_function, qual
        self.where, self.module_assign, self.bind_kind = None, False, None
        for node in body:
            self.walk(node)
        (self.table, self.extra_locals, self.in_function, self.where, self.module_assign, self.qual, self.bind_kind) = saved

    def _with(self, nodes, **state):
        saved = {key: getattr(self, key) for key in state}
        for key, value in state.items():
            setattr(self, key, value)
        for node in nodes:
            if node is not None:
                self.walk(node)
        for key, value in saved.items():
            setattr(self, key, value)

    # ---- walk ----------------------------------------------------------------------------------
    def walk(self, node: ast.AST):
        method = getattr(self, "w_" + type(node).__name__, None)
        if method is not None:
            method(node)
            return
        if type(node) in COMPREHENSIONS:
            self._comprehension(node)
            return
        for child in ast.iter_child_nodes(node):
            self.walk(child)

    def _function(self, node, name: str):
        args = node.args
        self._with(args.defaults + [d for d in args.kw_defaults if d is not None], where="default")
        if not isinstance(node, ast.Lambda):
            self._with(node.decorator_list, where="decorator")
            every = args.posonlyargs + args.args + args.kwonlyargs + [a for a in (args.vararg, args.kwarg) if a]
            self._with([a.annotation for a in every] + [node.returns], where="annotation")
            for param in getattr(node, "type_params", []):
                self.walk(param)
            self._bind(node.name, node.lineno, "def")
        child = self._child(name, node.lineno)
        if child is None:
            self.internal.append((node.lineno, f"no symbol table for {name}; the audit cannot check its body"))
            return
        body = [node.body] if isinstance(node, ast.Lambda) else node.body
        qual = self.qual if isinstance(node, ast.Lambda) else self.qual + [name]
        self._scoped(child, set(), True, qual, body)

    def w_FunctionDef(self, node):
        self._function(node, node.name)

    w_AsyncFunctionDef = w_FunctionDef

    def w_Lambda(self, node):
        self._function(node, "lambda")

    def w_ClassDef(self, node):
        self._with(node.decorator_list, where="decorator")
        self._with(node.bases + node.keywords)
        for param in getattr(node, "type_params", []):
            self.walk(param)
        self._bind(node.name, node.lineno, "class")
        child = self._child(node.name, node.lineno)
        if child is None:
            self.internal.append((node.lineno, f"no symbol table for class {node.name}"))
            return
        self._scoped(child, set(), self.in_function, self.qual + [node.name], node.body)

    def _comprehension(self, node):
        generators = node.generators
        self.walk(generators[0].iter)  # the first iterable runs in the enclosing scope
        inner = ([node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt])
        rest = []
        for index, gen in enumerate(generators):
            rest += [gen.target] + ([gen.iter] if index else []) + gen.ifs
        child = self._child(COMPREHENSIONS[type(node)], node.lineno)
        if child is not None:
            self._scoped_keep(child, set(), rest + inner)
            return
        if isinstance(node, ast.GeneratorExp):  # never inlined: a missing table means the walk lost its place
            self.internal.append((node.lineno, "no symbol table for a generator expression"))
            return
        targets = {n.id for gen in generators for n in ast.walk(gen.target) if isinstance(n, ast.Name)}
        self._scoped_keep(self.table, self.extra_locals | targets, rest + inner)  # inlined comprehension (3.12+)

    def _scoped_keep(self, table, extra, nodes):
        """Enter a comprehension scope: the function/assignment context stays as it is."""
        saved = (self.table, self.extra_locals, self.bind_kind)
        self.table, self.extra_locals, self.bind_kind = table, extra, None
        for node in nodes:
            self.walk(node)
        self.table, self.extra_locals, self.bind_kind = saved

    def w_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            if self._is_global(node.id):
                use = self._use(node.id, node.lineno)
                self.reads.append(use)
                if node.id == "game":
                    self.bare_game.append(use)
        else:
            self._bind(node.id, node.lineno, "del" if isinstance(node.ctx, ast.Del) else (self.bind_kind or "assign"))

    def w_Attribute(self, node):
        value = node.value
        if isinstance(value, ast.Name) and value.id == "game":
            self.game_attrs.append((self._use("game", node.lineno), node.attr, isinstance(node.ctx, ast.Load)))
            return
        through_game = isinstance(value, ast.Attribute) and value.attr == "sys" and isinstance(value.value, ast.Name)             and value.value.id == "game"  # game.sys.modules
        if node.attr == "modules" and (through_game or isinstance(value, ast.Name) and value.id in self.sys_names):
            self.identity.append(self._use("sys.modules", node.lineno))
        self.walk(value)

    def _assignment(self, node, targets, values):
        module_level = self.table is self.top and not self.in_function
        saved = self.module_assign
        self.module_assign = saved or module_level
        self._with(values)
        plain = isinstance(node, (ast.Assign, ast.AnnAssign)) and all(isinstance(t, ast.Name) for t in targets)
        self._with(targets, bind_kind="assign" if plain else "augassign" if isinstance(node, ast.AugAssign) else "unpack")
        self.module_assign = saved

    def w_Assign(self, node):
        self._assignment(node, node.targets, [node.value])

    def w_AnnAssign(self, node):
        self._assignment(node, [node.target], [node.annotation, node.value])

    def w_AugAssign(self, node):
        self._assignment(node, [node.target], [node.value])

    def w_For(self, node):
        self.walk(node.iter)
        self._with([node.target], bind_kind="for")
        self._with(node.body + node.orelse)

    w_AsyncFor = w_For

    def w_withitem(self, node):
        self.walk(node.context_expr)
        self._with([node.optional_vars], bind_kind="with")

    def w_NamedExpr(self, node):
        self.walk(node.value)
        self._with([node.target], bind_kind="walrus")

    def w_ExceptHandler(self, node):
        if node.type is not None:
            self.walk(node.type)
        if node.name:
            self._bind(node.name, node.lineno, "except")
        self._with(node.body)

    def _match_name(self, node, name):
        if name:
            self._bind(name, node.lineno, "match")
        for child in ast.iter_child_nodes(node):
            self.walk(child)

    def w_MatchAs(self, node):
        self._match_name(node, node.name)

    def w_MatchStar(self, node):
        self._match_name(node, node.name)

    def w_MatchMapping(self, node):
        self._match_name(node, node.rest)

    def w_Global(self, node):
        self.globals.extend((name, node.lineno) for name in node.names)

    def w_Import(self, node):
        self.imports.append(node)
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            self._bind(bound, node.lineno, "import game" if (alias.name, alias.asname) == ("game", None) else "import")

    def w_ImportFrom(self, node):
        self.imports.append(node)
        module = node.module or ""
        kind = "reexport" if node.level == 0 and module.startswith("game_parts.") else "import"
        for alias in node.names:
            if alias.name == "*":
                self.stars.append(node.lineno)
                continue
            if node.level == 0 and module == "sys" and alias.name == "modules":
                self.identity.append(self._use("sys.modules", node.lineno))
            self._bind(alias.asname or alias.name, node.lineno, kind)

    def w_Call(self, node):
        func = node.func
        dynamic = ((isinstance(func, ast.Name) and (func.id == "__import__" or func.id in self.import_module_names))
                   or (isinstance(func, ast.Attribute) and func.attr == "import_module"
                       and isinstance(func.value, ast.Name) and func.value.id in self.importlib_names))
        if dynamic:
            first = node.args[0] if node.args else None
            constant = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
            self.dynamic_imports.append((node.lineno, constant))
        for child in ast.iter_child_nodes(node):
            self.walk(child)


def _read(path: Path):
    """(tree, symtable) or (None, error text)."""
    source = path.read_text(encoding="utf-8")
    try:
        return ast.parse(source, str(path)), symtable.symtable(source, str(path), "exec")
    except SyntaxError as error:
        return None, f"does not parse: {error.msg} (line {error.lineno})"


def _main_guard(tree: ast.Module):
    """game.py's first statement when it is the T1 terminal guard, else None.

    game.py never takes a docstring or `from __future__` line: the guard must stay statement 0 (Task 17 Ruling 4),
    and only there are its `import game` and `from game_parts import terminal` allowed (Ruling 1).
    """
    if not tree.body:
        return None
    guard = tree.body[0]
    test = getattr(guard, "test", None)
    if not (isinstance(guard, ast.If) and not guard.orelse and isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name) and test.left.id == "__name__" and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq) and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "__main__" and len(guard.body) == 3):
        return None
    first, second, third = guard.body
    if not (isinstance(first, ast.Import) and [(a.name, a.asname) for a in first.names] == [("game", None)]
            and isinstance(second, ast.ImportFrom) and second.level == 0 and second.module == "game_parts"
            and [(a.name, a.asname) for a in second.names] == [("terminal", None)] and isinstance(third, ast.Raise)):
        return None
    return guard


def _game_facts(root: Path, findings: list[str]):
    """R2 on game.py; returns (names game.py binds at module level, {"game_parts.<x>": names it re-exports from it})."""
    path = root / "game.py"
    tree, top = _read(path)
    if tree is None:
        findings.append(f"R2 game.py:1: {top}")
        return set(), {}
    guard = _main_guard(tree)
    allowed = {id(node) for node in guard.body[:2]} if guard else set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)) or id(node) in allowed:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {"game", "game_parts"}:
                    findings.append(f"R2 game.py:{node.lineno}: `import {alias.name}` outside the first-statement __main__ guard")
            continue
        module = node.module or ""
        if node.level or module.split(".")[0] not in {"game", "game_parts"}:
            continue
        parts = module.split(".")
        if (parts[0] != "game_parts" or len(parts) != 2 or node not in tree.body
                or any(a.name == "*" or a.asname for a in node.names)):
            findings.append(f"R2 game.py:{node.lineno}: `from {module} import ...` is not a top-level "
                            "`from game_parts.<x> import <names>` (no star, no alias)")
    walker = _Walker(tree, top)
    findings += [f"R2 game.py:{line}: {text}" for line, text in walker.internal]
    for line, constant in walker.dynamic_imports:
        if constant is not None and constant.split(".")[0] == "game_parts":
            findings.append(f"R2 game.py:{line}: dynamic import of {constant}")
    guard_lines = range(guard.lineno, guard.end_lineno + 1) if guard else range(0)
    binds = [b for b in walker.binds if b.module_level and not b.via_global and b.line not in guard_lines]
    reexports: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").startswith("game_parts."):
            reexports.setdefault(node.module, set()).update(a.name for a in node.names if a.name != "*")
    return {b.name for b in binds}, reexports


def _resolvable(node: ast.AST, parents: dict) -> bool:
    """True when a string reaches a call argument (patch, resolve_name, import_module...) or a subscript key
    (sys.modules[...]), through containers. Data (assignments, dict values kept aside, == operands, assert* arguments)
    is not resolved as a module."""
    child, parent = node, parents.get(node)
    while isinstance(parent, (ast.Tuple, ast.List, ast.Set, ast.Dict, ast.Starred, ast.keyword)):
        child, parent = parent, parents.get(parent)
    if isinstance(parent, ast.Subscript):
        return child is parent.slice
    if not isinstance(parent, ast.Call) or child is parent.func:
        return False
    return not (isinstance(parent.func, ast.Attribute) and parent.func.attr.startswith("assert"))


def _imports_game_parts(tree: ast.Module) -> list[int]:
    lines = []
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str) and GAME_PARTS_STRING.match(node.value)
                and _resolvable(node, parents)):
            lines.append(node.lineno)
        if isinstance(node, ast.Import):
            lines += [node.lineno for a in node.names if a.name.split(".")[0] == "game_parts"]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] == "game_parts":
            lines.append(node.lineno)
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if name in {"__import__", "import_module"} and str(node.args[0].value).split(".")[0] == "game_parts":
                lines.append(node.lineno)
    return sorted(set(lines))


def _outside_findings(root: Path) -> list[str]:
    """R2: no file under root outside game.py and game_parts/ imports game_parts (tests included)."""
    findings = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if set(rel.parts) & SKIP_PARTS or rel.as_posix() == "game.py":
            continue
        if rel.parts[0] == "game_parts":
            if len(rel.parts) > 2:
                findings.append(f"R2 {rel.as_posix()}:1: a module nested under game_parts/ is outside the audit")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "game_parts" not in text:
            continue
        try:
            lines = _imports_game_parts(ast.parse(text))
        except SyntaxError:  # unparsable: fall back to the plain import line
            lines = [text.count("\n", 0, m.start()) + 1 for m in GAME_PARTS_IMPORT.finditer(text)]
        findings += [f"R2 {rel.as_posix()}:{line}: imports or names a game_parts module (only game.py may)" for line in lines]
    return findings


def _global_loads(code: CodeType):
    """(line, name) for every bytecode read that resolves through module globals, in every nested code object."""
    line = code.co_firstlineno
    for ins in dis.get_instructions(code):
        line = (ins.positions.lineno if ins.positions else None) or line
        if ins.opname in GLOBAL_LOADS:
            yield line, ins.argval
    for const in code.co_consts:
        if isinstance(const, CodeType):
            yield from _global_loads(const)


def _imports_patched(node: ast.Import | ast.ImportFrom, patched: set[str]) -> list[str]:
    """The patched names an import binds or reaches: its module root, the imported name or the bound alias."""
    if isinstance(node, ast.Import):
        return [a.name for a in node.names if a.name != "game"
                and ({a.name.split(".")[0], a.asname or a.name.split(".")[0]} & patched)]
    if node.level or (node.module or "").split(".")[0] in {"game", "game_parts"}:
        return []  # R2 reports these
    root = (node.module or "").split(".")[0]
    return [f"{node.module}.{a.name}" for a in node.names if {root, a.name, a.asname or a.name} & patched]


def _module_ok(module: str, allowed_imports: set[str]) -> bool:
    return module.split(".")[0] in sys.stdlib_module_names or module in allowed_imports


def _part_findings(path: Path, rel: str, ctx: dict) -> list[str]:
    tree, top = _read(path)
    if tree is None:
        return [f"R7 {rel}:1: {top}"]
    w = _Walker(tree, top)
    out = [f"R7 {rel}:{line}: {text}" for line, text in w.internal]
    patched = ctx["targets"] | {"open"}

    # R1 / R2: imports
    for node in w.imports:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "game":
                    if alias.asname:
                        out.append(f"R4 {rel}:{node.lineno}: game imported as {alias.asname}; R4 and R7 cannot see its reads")
                elif alias.name.split(".")[0] == "game_parts":
                    out.append(f"R2 {rel}:{node.lineno}: a part imports {alias.name}")
                elif not _module_ok(alias.name, ctx["allowed"]):
                    out.append(f"R1 {rel}:{node.lineno}: {alias.name} is neither stdlib, game nor in allowed_imports.json")
        elif node.level:
            out.append(f"R2 {rel}:{node.lineno}: relative import in a part")
        elif (node.module or "").split(".")[0] == "game_parts":
            out.append(f"R2 {rel}:{node.lineno}: a part imports {node.module}")
        elif node.module == "game" or (node.module or "").startswith("game."):
            out.append(f"R2 {rel}:{node.lineno}: `from {node.module} import` in a part")
        elif not _module_ok(node.module, ctx["allowed"]):
            out.append(f"R1 {rel}:{node.lineno}: {node.module} is neither stdlib, game nor in allowed_imports.json")
    for line, constant in w.dynamic_imports:
        if constant is None:
            out.append(f"R1 {rel}:{line}: computed dynamic import cannot be checked")
        elif constant.split(".")[0] == "game_parts":
            out.append(f"R2 {rel}:{line}: a part imports {constant}")
        elif constant.split(".")[0] == "game":
            out.append(f"R7 {rel}:{line}: game reached through a dynamic import; only a module-level `import game` may bind it")
        elif not _module_ok(constant, ctx["allowed"]):
            out.append(f"R1 {rel}:{line}: {constant} is neither stdlib, game nor in allowed_imports.json")

    # R3: patched names never imported (any scope, any alias), never bound by the part except the definition
    # game.py re-exports from this very part, and never read bare (symtable view plus the bytecode view)
    defined = {b.name for b in w.binds if b.module_level and not b.via_global}
    out += [f"R3 {rel}:{line}: star import binds names the audit cannot see" for line in w.stars]
    for node in w.imports:
        out += [f"R3 {rel}:{node.lineno}: imports patched name {name}; a patch on game cannot reach it"
                for name in _imports_patched(node, patched)]
    reexported = ctx["reexports"].get(f"game_parts.{Path(rel).stem}", set())
    for b in w.binds:
        if b.module_level and b.name in patched and b.kind not in {"import", "import game", "reexport"} and (
                b.via_global or b.kind not in DEFINING_KINDS or b.name not in reexported):
            out.append(f"R3 {rel}:{b.line}: patched name {b.name} is bound in the part ({b.kind}); a patch on game.{b.name} cannot reach it")
    bare = {(u.line, u.name) for u in w.reads if u.name in patched}
    out += [f"R3 {rel}:{line}: bare read of patched name {name}; a patch on game.{name} cannot reach it" for line, name in sorted(bare)]
    try:
        loads = sorted(set(_global_loads(compile(tree, rel, "exec", dont_inherit=True))))
    except SyntaxError as error:
        loads = []
        out.append(f"R7 {rel}:{error.lineno or 1}: does not compile: {error.msg}")
    out += [f"R3 {rel}:{line}: bytecode reads patched name {name} from globals; a patch on game.{name} cannot reach it"
            for line, name in loads if name in patched and (line, name) not in bare]

    # R4: game.<x> and game itself only inside function bodies
    for use, attr, _ in w.game_attrs:
        if not use.in_function or use.where:
            out.append(f"R4 {rel}:{use.line}: game.{attr} outside a function body ({use.where or 'import time'})")
    for use in w.bare_game:
        if not use.in_function or use.where:
            out.append(f"R4 {rel}:{use.line}: game used outside a function body ({use.where or 'import time'})")

    # R5 / R7: undefined global names; at import time inside a module-level assignment it is R5
    for u in w.reads:
        if u.name in defined or u.name in KNOWN or u.name in patched:
            continue
        rule = "R5" if u.module_assign and not u.in_function else "R7"
        out.append(f"{rule} {rel}:{u.line}: {u.name} is not bound in this part, its imports or builtins")
    out += [f"R7 {rel}:{line}: `global {name}` rebinds the part's namespace, not game" for name, line in w.globals]
    executed = {(u.line, u.name) for u in w.reads if u.name in EXEC_NAMES} | {(ln, n) for ln, n in loads if n in EXEC_NAMES}
    out += [f"R7 {rel}:{line}: {name} runs code the audit cannot see" for line, name in sorted(executed)]
    # game must be the module bound by a plain module-level `import game`; any other binding of the name hides game.<x>
    plain = [b for b in w.binds if b.name == "game" and b.kind == "import game" and b.module_level and not b.via_global]
    out += [f"R7 {rel}:{b.line}: the name game is rebound ({b.kind}); only a module-level `import game` may bind it"
            for b in w.binds if b.name == "game" and b not in plain]
    out += [f"R7 {rel}:{t.get_lineno()}: the name game is a parameter of {t.get_name()}"
            for t in _tables(top) if "game" in t.get_identifiers() and t.lookup("game").is_parameter()]
    if (w.game_attrs or w.bare_game) and not plain:
        out.append(f"R7 {rel}:{(w.game_attrs[0][0] if w.game_attrs else w.bare_game[0]).line}: "
                   "the part uses game without a module-level `import game`")
    for use, attr, _ in w.game_attrs:
        if attr in ctx["character_names"]:
            out.append(f"R7 {rel}:{use.line}: game.{attr} is a character attribute; read it from the session")
        elif attr not in ctx["game_bound"]:
            out.append(f"R7 {rel}:{use.line}: game.{attr} is not bound at module level in game.py")

    # R6: identity names unless an allowlist row matches (file, function, name)
    for u in [r for r in w.reads if r.name in IDENTITY_NAMES] + w.identity:
        key = (rel, u.function, u.name)
        if key in ctx["allow"]:
            ctx["allow_used"].add(key)
        else:
            out.append(f"R6 {rel}:{u.line}: identity name in {u.function}: {u.name}")
    return out


def _tables(table):
    yield table
    for child in table.get_children():
        yield from _tables(child)


def part_files(root: Path) -> list[Path]:
    """The audited parts: the same list engine_source_files gives after game.py."""
    return sorted((Path(root) / "game_parts").glob("*.py"))


def audit(root: Path, surface_targets: set[str], allowed_imports: set[str], identity_allowlist: list[dict],
          character_names: set[str]) -> list[str]:
    """Every N3 finding under root (ai-dnd); empty = clean. Each finding starts with `R<n> <file>:<line>`."""
    root = Path(root)
    findings: list[str] = []
    game_bound, reexports = _game_facts(root, findings)
    allow, rows = set(), []
    for index, row in enumerate(identity_allowlist, 1):
        if not (isinstance(row, dict) and set(row) == {"file", "function", "name", "reason"}
                and all(isinstance(v, str) and v.strip() for v in row.values())):
            findings.append(f"R6 identity_allowlist.json:{index}: a row needs non-empty file, function, name and reason")
            continue
        key = (row["file"], row["function"], row["name"])
        allow.add(key)
        rows.append((index, key))
    ctx = {"targets": set(surface_targets), "allowed": set(allowed_imports), "character_names": set(character_names),
           "game_bound": game_bound, "reexports": reexports, "allow": allow, "allow_used": set()}
    for path in part_files(root):
        findings += _part_findings(path, path.relative_to(root).as_posix(), ctx)
    findings += [f"R6 identity_allowlist.json:{index}: row {key} matches nothing" for index, key in rows
                 if key not in ctx["allow_used"]]
    findings += _outside_findings(root)
    return findings


def character_names(game_py: Path) -> set[str]:
    """The keys of game.py's `_CHARACTER_GLOBALS` dict literal (constant keys and a `**{k: k for k in (...)}` block)."""
    tree = ast.parse(Path(game_py).read_text(encoding="utf-8"))
    node = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_CHARACTER_GLOBALS" for t in n.targets))
    names = set()
    for key, value in zip(node.keys, node.values):
        if isinstance(key, ast.Constant):
            names.add(key.value)
        elif (key is None and isinstance(value, ast.DictComp) and len(value.generators) == 1
              and isinstance(value.key, ast.Name) and isinstance(value.generators[0].target, ast.Name)
              and value.key.id == value.generators[0].target.id
              and isinstance(value.generators[0].iter, (ast.Tuple, ast.List, ast.Set))):
            names |= {e.value for e in value.generators[0].iter.elts}
        else:
            raise ValueError(f"_CHARACTER_GLOBALS line {node.lineno}: a key form the audit cannot read")
    return names


def game_imports(game_py: Path) -> list[str]:
    """Every non-stdlib module game.py imports (top level, in-function and constant __import__), minus game/game_parts."""
    return _project_imports([Path(game_py)])


def engine_imports(root: Path) -> list[str]:
    """game_imports over game.py and every part: a move keeps this list, a newly imported project module changes it."""
    return _project_imports([Path(root) / "game.py", *part_files(root)])


def _project_imports(paths: list[Path]) -> list[str]:
    modules = set()
    for node in (n for path in paths for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))):
        if isinstance(node, ast.Import):
            modules |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            modules.add(node.module)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__"
              and node.args and isinstance(node.args[0], ast.Constant)):
            modules.add(node.args[0].value)
    return sorted(m for m in modules if m.split(".")[0] not in sys.stdlib_module_names | {"game", "game_parts"})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-allowed-imports", metavar="PATH")
    args = ap.parse_args(argv)
    if args.write_allowed_imports:
        modules = engine_imports(ROOT)
        Path(args.write_allowed_imports).write_text(json.dumps(modules, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"allowed_imports={len(modules)}")
        return 0
    load = lambda name: json.loads((LOCKS / name).read_text(encoding="utf-8"))  # noqa: E731
    findings = audit(ROOT, set(load("patch_census.json")["targets"]), set(load("allowed_imports.json")),
                     load("identity_allowlist.json"), character_names(ROOT / "game.py"))
    print("\n".join(findings) or "clean")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
