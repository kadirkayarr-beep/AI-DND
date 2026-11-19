"""Read-only: cut the T4 move set (map json) into batches and list each batch's header imports.
Rule: per module, names in game.py file order; a name over CAP lines is a batch of its own; the rest fill batches
greedily up to CAP lines, in file order. Usage: python batches.py <ai-dnd root> <map.json> <out.json> [CAP]
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
T4 = ["character_rules", "places", "intent", "dialogue", "lore", "narration", "narration_safety",
      "living_world_turn", "new_game"]
SHORT = {"character_rules": "cr", "places": "places", "intent": "intent", "dialogue": "dialogue", "lore": "lore",
         "narration": "narration", "narration_safety": "nsafety", "living_world_turn": "lwt", "new_game": "newgame"}
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


def reads(name):
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


rows = [r for r in MAP["rows"] if r["module"] in T4 and not r["sensitive"]]
batches = {}
for m in T4:
    names = [r for r in rows if r["module"] == m]
    big = [r for r in names if r["lines"] > CAP]
    rest = [r for r in names if r["lines"] <= CAP]
    cut, cur, total = [], [], 0
    for r in rest:
        if cur and total + r["lines"] > CAP:
            cut.append(cur)
            cur, total = [], 0
        cur.append(r)
        total += r["lines"]
    if cur:
        cut.append(cur)
    cut += [[r] for r in big]
    for i, b in enumerate(cut, 1):
        key = SHORT[m] if len(cut) == 1 else f"{SHORT[m]}-{i}"
        rd = set().union(*(reads(r["name"]) for r in b))
        header = sorted({imported[x] for x in rd if x in imported and census.get(x) not in ("import", "absent")})
        prefixed_imports = sorted(x for x in rd if x in imported and census.get(x) in ("import", "absent"))
        batches[key] = {"module": m, "names": [r["name"] for r in b], "lines": sum(r["lines"] for r in b),
                        "header": header, "census_import_prefixed": prefixed_imports,
                        "census_targets": [r["name"] for r in b if census.get(r["name"])]}
OUT.write_text(json.dumps(batches, ensure_ascii=False, indent=1), encoding="utf-8")
for k, v in batches.items():
    print(f"{k}: {v['module']} names={len(v['names'])} lines={v['lines']} header={v['header']} "
          f"prefixed={v['census_import_prefixed']} census={v['census_targets']}")
