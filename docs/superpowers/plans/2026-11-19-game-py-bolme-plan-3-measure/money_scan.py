# Read-only (Plan 3 fix wave): batch names that call equipment_economy/economic_actions/bold_acts (N8 two-hop blind spot,
# D-355 class) and module-level walrus statements. Usage: python money_scan.py <repo root> <batches.json>
import ast, json, pathlib, sys
ROOT = pathlib.Path(sys.argv[1])
batches = json.load(open(sys.argv[2], encoding="utf-8"))
src = (ROOT / "ai-dnd" / "game.py").read_text(encoding="utf-8")
tree = ast.parse(src)
top = {}
for n in tree.body:
    for t in ([n.name] if hasattr(n, "name") else [x.id for x in getattr(n, "targets", []) if isinstance(x, ast.Name)] + ([n.target.id] if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) else [])):
        top[t] = n
MODS = {"equipment_economy", "economic_actions", "bold_acts"}
# names imported from those modules via from-import
from_imported = {}
for n in tree.body:
    if isinstance(n, ast.ImportFrom) and n.module in MODS:
        for a in n.names:
            from_imported[a.asname or a.name] = n.module
print("FROM_IMPORTED", sorted(from_imported.items()))
for b, d in batches.items():
    for name in d["names"]:
        node = top.get(name)
        if node is None:
            print("MISSING", b, name); continue
        hits = set()
        for x in ast.walk(node):
            if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id in MODS:
                hits.add(f"{x.value.id}.{x.attr}")
            if isinstance(x, ast.Name) and x.id in from_imported:
                hits.add(f"{from_imported[x.id]}:{x.id}")
        if hits:
            print("MONEYCALL", b, name, f"L{node.lineno}-{node.end_lineno}", sorted(hits))
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if any(isinstance(x, ast.NamedExpr) for x in ast.walk(node)):
                print("MODULE_LEVEL_WALRUS", b, name)
        if name in ("create_npc_from_ai", "commit_location_change", "advance_campaign_time"):
            print("SPAN", b, name, node.lineno, node.end_lineno, node.end_lineno - node.lineno + 1)
# module-level walrus anywhere at top level of game.py (outside defs)
def walk_no_defs(n):
    for c in ast.iter_child_nodes(n):
        if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield c
        yield from walk_no_defs(c)
mw = [x.lineno for x in walk_no_defs(tree) if isinstance(x, ast.NamedExpr)]
print("GAMEPY_MODULE_LEVEL_WALRUS_LINES", mw)
print("PY", sys.version.split()[0])
