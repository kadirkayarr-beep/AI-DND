# Read-only (Plan 3 fix wave 2): transitive money/death/save writer scan over the whole engine (D-355 class).
# A batch name is HELD when it can reach, in any number of hops, a function whose own body writes money (a store or a
# mutating call on a "currency"/purse/coin/ledger key, or on a local bound from one), player death (a store on a
# death-state key, a "condition_death" result) or save/Undo state (N8 save/snapshot names, file writes, SQL writes).
# Call graph: every function and method of every engine module (ai-dnd/**.py minus tests, scripts, legacy_debug,
# docs, *_test.py); edges from names, module attributes (imports at module level and inside functions, game.X too),
# self/cls methods, and a by-name fallback for a called `obj.meth(...)` (GameSession.__getattr__ -> game.meth; meth not a builtin-container method, defined in at
# most FALLBACK_MAX classes). Blind spots: getattr/strings, callbacks stored in data, methods with common names.
# A batch name starts where it is defined: in game.py, or (after a move) in the game_parts module its game.py re-export
# names. A name defined nowhere prints MISSING and counts as missing, never as clean.
# Usage: python writer_scan.py <repo root> <batch file> [<batch file> ...]
#   a .json batch file is a {batch: {"names": [...]}} dict (batches.py output); any other file is one name per line
#   (the committed ai-dnd/scripts/engine_split/batches/<B>.txt; blank and # lines skipped; batch = file stem).
# Exit 1 when any name is HELD or MISSING; the pass line is `SUMMARY held=0 missing=0 clean=<names>`.
import ast
import json
import pathlib
import re
import sys
from collections import deque

ROOT = pathlib.Path(sys.argv[1]) / "ai-dnd"
batches = {}
for arg in sys.argv[2:]:
    bf = pathlib.Path(arg)
    if bf.suffix == ".json":
        batches.update(json.loads(bf.read_text(encoding="utf-8")))
    else:
        batches[bf.stem] = {"names": [x.strip() for x in bf.read_text(encoding="utf-8").splitlines()
                                      if x.strip() and not x.strip().startswith("#")]}
FALLBACK_MAX = 3
SKIP_DIRS = {"tests", "scripts", "legacy_debug", "docs", "node_modules", "__pycache__", "class_progression_data"}
MONEY_KEYS = {"currency", "purse", "purses", "coins", "coin", "gold", "gp", "sp", "cp", "ep", "pp", "copper",
              "wallet", "coin_ledger", "ledger", "economic_ledger", "money"}
DEATH_KEYS = {"dead", "stable", "death_state", "death_resolution", "death_save", "death_saves", "failed_death_saves",
              "successful_death_saves", "last_death_save_result", "last_death_save_turn_key", "condition_death",
              "death_results"}
MUTATORS = {"update", "pop", "popitem", "append", "extend", "insert", "remove", "clear", "__setitem__", "add",
            "discard", "setdefault"}
SAVE_CALLS = {"save_game", "load_game", "serialize_game_state", "_player_state_for_save", "_capture_runtime_snapshot",
              "_restore_runtime_snapshot", "_capture_combat_death_checkpoint", "_restore_combat_death_checkpoint",
              "_restore_in_place", "write_text", "write_bytes"}
MONEY_CALL = re.compile(r"offer_records|_writable_records|purse|ledger|currency|coin|wallet")
# Log/telemetry file writers: not save state (usage ledger, Haiku spend counter, route log, debug trail, reports).
TELEMETRY_MODULES = ("api.usage_ledger", "reports.", "run_tests")
TELEMETRY_UNITS = {"api.model_chain:HaikuSpend.add", "front_proposal:log_turn", "game:_speech_debug_trail"}
COMMON = set()
for t in (dict, list, str, set, tuple, object, bytes, int, frozenset):
    COMMON |= set(dir(t))
COMMON |= {"get", "run", "apply", "load", "save", "read", "write", "close", "open", "send", "start", "stop", "step",
           "reset", "copy", "items", "keys", "values", "group", "match", "search", "sub", "split", "strip", "join",
           "lower", "upper", "format", "execute", "commit", "fetchone", "fetchall", "cursor", "isoformat"}


def modname(p):
    rel = p.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


files = {}
for p in ROOT.rglob("*.py"):
    rel = p.relative_to(ROOT).parts
    if any(x in SKIP_DIRS for x in rel[:-1]) or p.name.endswith("_test.py") or p.name.startswith("test_"):
        continue
    try:
        files[modname(p)] = ast.parse(p.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        print("UNPARSED", p)

units = {}        # "mod:Qual" -> node
mod_defs = {}     # mod -> {name: kind}
classes = {}      # mod -> {cls: (bases, {meth})}
meth_index = {}   # meth -> ["mod:Cls.meth"]
for m, tree in files.items():
    mod_defs[m], classes[m] = {}, {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            units[f"{m}:{n.name}"] = n
            mod_defs[m][n.name] = "f"
        elif isinstance(n, ast.ClassDef):
            mod_defs[m][n.name] = "c"
            meths = set()
            for b in n.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    units[f"{m}:{n.name}.{b.name}"] = b
                    meths.add(b.name)
                    meth_index.setdefault(b.name, []).append(f"{m}:{n.name}.{b.name}")
            classes[m][n.name] = ([x.id for x in n.bases if isinstance(x, ast.Name)], meths)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            tg = n.targets if isinstance(n, ast.Assign) else [n.target]
            for x in tg:
                if isinstance(x, ast.Name):
                    units[f"{m}:{x.id}"] = n
                    mod_defs[m].setdefault(x.id, "a")


def resolve_from(m, node):
    if node.level:
        base = m.split(".")
        pkg = base[:-1] if not (ROOT / pathlib.Path(*base) / "__init__.py").exists() else base
        pkg = pkg[:len(pkg) - (node.level - 1)] if node.level > 1 else pkg
        return ".".join(pkg + ([node.module] if node.module else []))
    return node.module or ""


def aliases_of(m, nodes):
    out = {}
    for x in nodes:
        if isinstance(x, ast.Import):
            for a in x.names:
                if a.asname:
                    out[a.asname] = ("mod", a.name)
                else:
                    out[a.name.split(".")[0]] = ("mod", a.name.split(".")[0])
        elif isinstance(x, ast.ImportFrom):
            src = resolve_from(m, x)
            for a in x.names:
                full = f"{src}.{a.name}"
                out[a.asname or a.name] = ("mod", full) if full in files else ("name", src, a.name)
    return out


mod_alias = {m: aliases_of(m, [n for n in t.body if isinstance(n, (ast.Import, ast.ImportFrom))]) for m, t in files.items()}


def defining(mod, name):
    """(module, name) that defines `name` of `mod`, following `from X import name` re-exports; None if undefined."""
    if mod_defs.get(mod, {}).get(name):
        return mod, name
    a = mod_alias.get(mod, {}).get(name)
    if a and a[0] == "name" and a[1] != mod:
        return defining(a[1], a[2])
    return None


def target_of(mod, name):
    kind = mod_defs.get(mod, {}).get(name)
    if kind in ("f", "a"):
        return [f"{mod}:{name}"]
    if kind == "c":
        return [u for u in (f"{mod}:{name}.__init__", f"{mod}:{name}.__post_init__", f"{mod}:{name}.__call__") if u in units]
    a = mod_alias.get(mod, {}).get(name)  # re-export
    if a and a[0] == "name" and a[1] != mod:
        return target_of(a[1], a[2])
    return []


def edges(uid):
    m, qual = uid.split(":", 1)
    node = units[uid]
    cls = qual.split(".")[0] if "." in qual else None
    al = dict(mod_alias[m])
    al.update(aliases_of(m, [x for x in ast.walk(node) if isinstance(x, (ast.Import, ast.ImportFrom))]))
    out = {}

    def add(targets, how):
        for t in targets:
            if t != uid and t in units:
                out.setdefault(t, how)

    def chain(x):
        names = []
        while isinstance(x, ast.Attribute):
            names.append(x.attr)
            x = x.value
        if isinstance(x, ast.Name):
            names.append(x.id)
            return list(reversed(names))
        return None

    called = {id(c.func) for c in ast.walk(node) if isinstance(c, ast.Call)}
    for x in ast.walk(node):
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load):
            a = al.get(x.id)
            if a and a[0] == "name":
                add(target_of(a[1], a[2]), "from-import")
            elif not a:
                add(target_of(m, x.id), "name")
        elif isinstance(x, ast.Attribute) and isinstance(x.ctx, ast.Load):
            c = chain(x)
            if c and c[0] in al and al[c[0]][0] == "mod":
                modn = al[c[0]][1]
                i = 1
                while i < len(c) - 1 and f"{modn}.{c[i]}" in files:
                    modn = f"{modn}.{c[i]}"
                    i += 1
                if modn in files and i == len(c) - 1:
                    add(target_of(modn, c[i]), "module-attr")
                    continue
            if c and len(c) == 2 and c[0] in ("self", "cls") and cls:
                seen, todo = set(), [cls]
                while todo:
                    k = todo.pop()
                    if k in seen or k not in classes[m]:
                        continue
                    seen.add(k)
                    if c[1] in classes[m][k][1]:
                        add([f"{m}:{k}.{c[1]}"], "self")
                        break
                    todo += classes[m][k][0]
                else:
                    if m == "game" and cls == "GameSession":  # GameSession.__getattr__ -> session-bound game helper
                        add(target_of("game", c[1]), "session-getattr")
                continue
            if id(x) not in called:  # by-name fallbacks only for calls: a data attribute is not a method
                continue
            if x.attr not in COMMON and 0 < len(meth_index.get(x.attr, [])) <= FALLBACK_MAX:
                add(meth_index[x.attr], "method-by-name")
            d = defining("game", x.attr) if x.attr not in COMMON else None
            if d and mod_defs[d[0]][d[1]] == "f":  # session.X -> GameSession.__getattr__ -> game.X (or its re-export)
                add([f"{d[0]}:{d[1]}"], "session-getattr")
    return out


def consts(x):
    return {c.value for c in ast.walk(x) if isinstance(c, ast.Constant) and isinstance(c.value, str)}


def root_name(x):
    while isinstance(x, (ast.Subscript, ast.Attribute, ast.Call)):
        x = x.func if isinstance(x, ast.Call) else x.value
    return x.id if isinstance(x, ast.Name) else None


def own_writes(uid):
    node = units[uid]
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        return set()
    taint = {"money": set(), "death": set()}
    # A name bound only to a new literal/constructor is a local value, not world/save state: stores on it do not count.
    bound = {}
    for x in ast.walk(node):
        if isinstance(x, (ast.Assign, ast.AnnAssign)) and x.value is not None:
            for t in (x.targets if isinstance(x, ast.Assign) else [x.target]):
                if isinstance(t, ast.Name):
                    bound.setdefault(t.id, []).append(isinstance(x.value, (ast.Dict, ast.DictComp, ast.List, ast.ListComp, ast.Set)) or (
                        isinstance(x.value, ast.Call) and isinstance(x.value.func, ast.Name) and x.value.func.id in ("dict", "list", "set")))
    fresh = {n for n, v in bound.items() if all(v)}

    def tainted(cat, expr):
        keys = MONEY_KEYS if cat == "money" else DEATH_KEYS
        if consts(expr) & keys or root_name(expr) in taint[cat]:
            return True
        return cat == "money" and any(isinstance(c, ast.Call) and MONEY_CALL.search(
            c.func.id if isinstance(c.func, ast.Name) else c.func.attr if isinstance(c.func, ast.Attribute) else "")
            for c in ast.walk(expr))

    for _ in range(3):
        for x in ast.walk(node):
            pairs = []
            if isinstance(x, (ast.Assign, ast.AnnAssign)) and x.value is not None:
                pairs = [(t, x.value) for t in (x.targets if isinstance(x, ast.Assign) else [x.target])]
            elif isinstance(x, (ast.For, ast.comprehension)):
                pairs = [(x.target, x.iter)]
            for tgt, val in pairs:
                names = [n.id for n in ast.walk(tgt) if isinstance(n, ast.Name)]
                for cat in ("money", "death"):
                    if names and not set(names) <= fresh and tainted(cat, val):
                        taint[cat].update(names)
    hits = set()

    def check_target(t, why, force=False):
        k = consts(t)
        rn = root_name(t)
        if not (force or isinstance(t, (ast.Subscript, ast.Attribute))) or rn in fresh:
            return
        if k & MONEY_KEYS or rn in taint["money"]:
            hits.add(f"money:{why}")
        if k & DEATH_KEYS or rn in taint["death"]:
            hits.add(f"death:{why}")

    for x in ast.walk(node):
        if isinstance(x, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            for t in (x.targets if isinstance(x, (ast.Assign, ast.Delete)) else [x.target]):
                check_target(t, "store")
        elif isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute):
            if x.func.attr in MUTATORS and not (x.func.attr == "setdefault" and len(x.args) < 2):
                check_target(x.func.value, f".{x.func.attr}", force=True)
                if x.func.attr == "setdefault":  # world.setdefault("currency", {}) creates the key
                    check_target(x.args[0], ".setdefault-key", force=True)
            if x.func.attr in ("execute", "executemany") and x.args and any(
                    w in s.upper() for s in consts(x.args[0]) for w in ("INSERT", "UPDATE", "DELETE", "REPLACE")):
                hits.add("save:sql-write")
            if x.func.attr in SAVE_CALLS:
                hits.add(f"save:{x.func.attr}")
            if isinstance(x.func.value, ast.Name) and (x.func.value.id, x.func.attr) in {("os", "replace"), ("json", "dump")}:
                hits.add(f"save:{x.func.value.id}.{x.func.attr}")
        elif isinstance(x, ast.Call) and isinstance(x.func, ast.Name):
            if x.func.id in SAVE_CALLS:
                hits.add(f"save:{x.func.id}")
            if x.func.id == "open":
                mode = x.args[1] if len(x.args) > 1 else next((k.value for k in x.keywords if k.arg == "mode"), None)
                if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(c in mode.value for c in "wax+"):
                    hits.add("save:open-write")
        elif isinstance(x, ast.Dict):
            if any(isinstance(k, ast.Constant) and k.value == "condition_death" for k in x.keys):
                hits.add("death:condition_death-result")
    return hits


writers = {u: w for u in units if (w := own_writes(u))}
for u in sorted(writers):
    if u in TELEMETRY_UNITS or u.split(":")[0].startswith(TELEMETRY_MODULES):
        print("TELEMETRY_NOT_SAVE", u, sorted(writers.pop(u)))
by_mod = {}
for u, w in writers.items():
    by_mod.setdefault(u.split(":")[0], set()).update(c.split(":")[0] for c in w)
print("ENGINE_MODULES", len(files), "UNITS", len(units), "WRITERS", len(writers))
for m in sorted(by_mod):
    print("WRITER_MODULE", m, sorted(by_mod[m]), sum(1 for u in writers if u.startswith(m + ":")))
graph = {}


def nb(u):
    if u not in graph:
        graph[u] = edges(u)
    return graph[u]


held, clean, missing = {}, [], []
for b, d in batches.items():
    for name in d["names"]:
        where = defining("game", name)
        if not where:
            print("MISSING", b, name)
            missing.append(name)
            continue
        uid = f"{where[0]}:{where[1]}"
        starts = [uid] if uid in units else [u for u in units if u.startswith(f"{uid}.")]
        if not starts:
            print("NO_CODE", b, name, "(class with no methods)")
            clean.append(name)
            continue
        prev, q, found = {s: None for s in starts}, deque(starts), None
        while q:
            u = q.popleft()
            if u in writers:
                found = u
                break
            for v, how in nb(u).items():
                if v not in prev:
                    prev[v] = (u, how)
                    q.append(v)
        if found:
            path, u = [], found
            while u:
                p = prev[u]
                path.append(u + (f" [{p[1]}]" if p else ""))
                u = p[0] if p else None
            held[name] = (b, sorted(writers[found]), list(reversed(path)))
        else:
            clean.append(name)
cats = {}
for name, (b, w, path) in held.items():
    cat = "+".join(sorted({x.split(":")[0] for x in w}))
    cats[cat] = cats.get(cat, 0) + 1
    print("HELD", b, name, w, "hops=%d" % (len(path) - 1), " -> ".join(path))
print("SUMMARY held=%d missing=%d clean=%d" % (len(held), len(missing), len(clean)), cats)
print("PY", sys.version.split()[0])
sys.exit(1 if held or missing else 0)
