"""Read-only: cut the Plan 5 move set (plan4_map.py output, scope "plan5" = topic `turn`, sensitive or not) into
batches and list each batch's header imports. Plan 4's batches4.py rule unchanged: names in game.py file order; a name
over CAP lines is a batch of its own and comes last; the rest fill batches greedily up to CAP lines. A name that
game.py reads only from never-moved code (GameSession and the session core) stays in game.py (printed as STAY).
Two targets (pre-flight C1): CORE (spec section 5 `turn.py` content) goes to `turn`, every other name to `turn_front`.
Move order: the `turn_front` batches, then the `turn` batches, then the name(s) over CAP (all in CORE) last.
Decorator names count as read by their batch (pre-flight C2: a decorator is evaluated in module scope).
Usage: python batches5.py <ai-dnd root> <p4m-map.json> <out.json> [CAP]
"""
import ast
import json
import symtable
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
MAP = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
OUT = Path(sys.argv[3])
CAP = int(sys.argv[4]) if len(sys.argv) > 4 else 1000
SCOPE = "plan5"
CORE = {"_run_player_turn_internal", "_dispatch_player_turn", "_dispatch_turn_body", "run_player_turn",
        "_run_player_turn_owned", "_run_player_turn", "_run_player_turn_keyed", "turn_source_key",
        "_spoken_rest_of_turn", "_current_procedural_entity_ids", "_keep_town_portrait", "_narrate_resolved_turn",
        "_owner_module_reply", "ResolvedTurn", "TurnResolved", "DEBUG_MODE"}
TARGETS = (("turn_front", "front"), ("turn", "turn"))  # (part module, batch name prefix), in move order
source = (ROOT / "game.py").read_text(encoding="utf-8")
tree = ast.parse(source)
imported = {}
for node in tree.body:
    if isinstance(node, ast.Import):
        for a in node.names:
            imported[a.asname or a.name.split(".")[0]] = ast.get_source_segment(source, node)
    elif isinstance(node, ast.ImportFrom) and not (node.module or "").startswith("game_parts"):
        for a in node.names:
            imported[a.asname or a.name] = ast.get_source_segment(source, node)
census = json.loads((ROOT / "api/tests/engine_split_locks/patch_census.json").read_text(encoding="utf-8"))["targets"]
top = symtable.symtable(source, "game.py", "exec")
by_name = {}
for child in top.get_children():
    by_name.setdefault(child.get_name(), child)


decorators = {}
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.decorator_list:
        decorators[node.name] = {n.id for d in node.decorator_list for n in ast.walk(d) if isinstance(n, ast.Name)}


def reads(name):
    return _body_reads(name) | decorators.get(name, set())


def _body_reads(name):
    t = by_name.get(name)
    if t is None:  # constant: names in its value
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                tg = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(x, ast.Name) and x.id == name for x in tg):
                    return {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
        return set()
    out, stack = set(), [t]
    while stack:
        s = stack.pop()
        out |= {y.get_name() for y in s.get_symbols() if y.is_global() and y.is_referenced()}
        stack += s.get_children()
    return out


rows = [r for r in MAP["rows"] if r["scope"] == SCOPE]
assert {r["module"] for r in rows} <= {"turn"}, {r["module"] for r in rows}
# Misfit rule against never-moved code: plan4_map.py's call graph sees functions only, not methods of the never-moved
# class GameSession. A name read inside game.py only by never-moved top-level nodes stays with them in game.py.
never = {r["name"] for r in MAP["rows"] if r["scope"] == "never"}
scope_names = {r["name"] for r in rows}
refs = {}
for node in tree.body:
    owner = getattr(node, "name", None)
    if owner is None and isinstance(node, (ast.Assign, ast.AnnAssign)):
        tg = node.targets if isinstance(node, ast.Assign) else [node.target]
        owner = next((x.id for x in tg if isinstance(x, ast.Name)), None)
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in scope_names and sub.id != owner:
            refs.setdefault(sub.id, set()).add(owner or "<module>")
stay = {n: sorted(o) for n, o in refs.items() if o and o <= never}
print("NEVER_READERS", sorted((n, sorted(o & never)) for n, o in refs.items() if o & never))
print("STAY", stay)
rows = [r for r in rows if r["name"] not in stay]
big = [r for r in rows if r["lines"] > CAP]
assert all(r["name"] in CORE for r in big), [r["name"] for r in big]
assert CORE <= {r["name"] for r in rows}, CORE - {r["name"] for r in rows}


def greedy(part_rows):
    cut, cur, total = [], [], 0
    for r in part_rows:
        if cur and total + r["lines"] > CAP:
            cut.append(cur)
            cur, total = [], 0
        cur.append(r)
        total += r["lines"]
    if cur:
        cut.append(cur)
    return cut


plan = []  # (part, prefix, rows) in move order
for part, prefix in TARGETS:
    mine = [r for r in rows if (r["name"] in CORE) == (part == "turn") and r["lines"] <= CAP]
    plan += [(part, prefix, b) for b in greedy(mine)]
plan += [("turn", "turn", [r]) for r in big]
batches = {}
count = {}
for part, prefix, b in plan:
    count[prefix] = count.get(prefix, 0) + 1
    key = f"{prefix}-{count[prefix]}"
    rd = set().union(*(reads(r["name"]) for r in b))
    header = sorted({imported[x] for x in rd if x in imported and census.get(x) not in ("import", "absent")})
    prefixed_imports = sorted(x for x in rd if x in imported and census.get(x) in ("import", "absent"))
    from_read = sorted(x for x in rd if x in imported and imported[x].startswith("from ")
                       and census.get(x) not in ("import", "absent"))
    batches[key] = {"module": part, "names": [r["name"] for r in b], "lines": sum(r["lines"] for r in b),
                    "sensitive": [r["name"] for r in b if r["sensitive"]],
                    "header": header, "from_import_names_read": from_read, "census_import_prefixed": prefixed_imports,
                    "census_targets": [[r["name"], census[r["name"]]] for r in b if census.get(r["name"])]}
OUT.write_text(json.dumps(batches, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"BATCHES {len(batches)} NAMES {sum(len(v['names']) for v in batches.values())} "
      f"LINES {sum(v['lines'] for v in batches.values())}")
for k, v in batches.items():
    print(f"{k}: {v['module']} names={len(v['names'])} lines={v['lines']} sensitive={len(v['sensitive'])}")
    print(f"  names: {', '.join(v['names'])}")
    print(f"  sensitive: {', '.join(v['sensitive'])}")
    print(f"  header: {v['header']}")
    print(f"  from-import names read (M5 Ruling: list only these): {v['from_import_names_read']}")
    print(f"  prefixed: {v['census_import_prefixed']}  census: {v['census_targets']}")
