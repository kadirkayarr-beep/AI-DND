"""Read-only: risk checks on the Plan 3 (T4) move set from module_map.py output.
Usage: python t4_checks.py <ai-dnd root> <map.json> <out.json>
"""
import ast
import builtins
import json
import re
import symtable
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1])
MAP = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
OUT = Path(sys.argv[3])
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from engine_split.inventory import top_level_index, constant_clusters, touching_tests  # noqa: E402
from engine_split.patch_census import scan  # noqa: E402

T4 = ["character_rules", "places", "intent", "dialogue", "lore", "narration", "narration_safety",
      "living_world_turn", "new_game"]
game = ROOT / "game.py"
source = game.read_text(encoding="utf-8")
lines = source.splitlines()
tree = ast.parse(source)
rows = {r["name"]: r for r in MAP["rows"]}
module = {n: r["module"] for n, r in rows.items()}
t4 = {n for n, r in rows.items() if r["module"] in T4 and not r["sensitive"]}
t4_sens = {n for n, r in rows.items() if r["module"] in T4 and r["sensitive"]}
lock = json.loads((ROOT / "api/tests/engine_split_locks/patch_census.json").read_text(encoding="utf-8"))
targets = lock["targets"]
nodes = {}
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        nodes[node.name] = node
    elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        tgts = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in tgts:
            for n in ast.walk(t):
                if isinstance(n, ast.Name):
                    nodes.setdefault(n.id, node)
engine_names = {d["name"] for d in top_level_index(game) if d["kind"] != "other"}
char_globals = {"character_name", "character_race", "character_class", "strength", "dexterity", "constitution",
                "intelligence", "wisdom", "charisma", "proficient_skills", "level", "proficiency_bonus", "max_hp",
                "current_hp", "armor_class", "strength_mod", "dexterity_mod", "constitution_mod",
                "intelligence_mod", "wisdom_mod", "charisma_mod", "modifiers"}
IDENT = {"__name__", "__file__", "globals", "locals", "vars", "__builtins__"}
report = defaultdict(list)
top = symtable.symtable(source, str(game), "exec")


def free_reads(name):
    out = set()
    for child in top.get_children():
        if child.get_name() == name:
            stack = [child]
            while stack:
                t = stack.pop()
                out |= {s.get_name() for s in t.get_symbols() if s.is_global() and s.is_referenced()}
                stack += t.get_children()
    return out


for n in sorted(t4):
    node = nodes.get(n)
    if node is None:
        report["no_node"].append(n)
        continue
    seg = "\n".join(lines[node.lineno - 1:node.end_lineno])
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.decorator_list:
            report["decorated"].append(n)
        defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
        bad = [ast.get_source_segment(source, d) for d in defaults if not isinstance(d, ast.Constant)]
        if bad:
            report["non_constant_default"].append([n, bad])
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Global, ast.Nonlocal)) and isinstance(sub, ast.Global):
                report["global_stmt"].append([n, sub.names])
            if isinstance(sub, ast.Name) and sub.id in IDENT:
                report["identity_name"].append([n, sub.id])
            if isinstance(sub, ast.Attribute) and sub.attr == "modules" and isinstance(sub.value, ast.Name) and sub.value.id == "sys":
                report["identity_name"].append([n, "sys.modules"])
            if isinstance(sub, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in sub.names] if isinstance(sub, ast.Import) else [sub.module or "."]
                report["in_function_import"].append([n, mods])
                if any(m in ("game",) or (m or "").startswith("game_parts") for m in mods):
                    report["imports_engine"].append([n, mods])
        reads = free_reads(n)
        bi = set(dir(builtins))
        cg = reads & char_globals
        if cg:
            report["character_global_read"].append([n, sorted(cg)])
        undefined = sorted(r for r in reads if r not in engine_names and r not in bi and r not in rows)
        if undefined:
            report["free_non_engine_reads"].append([n, undefined])
        census_import = sorted(r for r in reads if targets.get(r) in ("import", "absent"))
        if census_import:
            report["census_import_targets_used"].append([n, census_import])
        if "open" in reads:
            report["builtin_open"].append(n)
        adapter = sorted(reads & {"ask_dungeon_master", "build_world_context", "finalize_narration"})
        if adapter:
            report["calls_adapter_names"].append([n, adapter])
        never = sorted(reads & {"world_state", "messages", "recent_dm_narrations", "_session", "_DEFAULT_SESSION",
                                "_ACTIVE_SESSION", "GameSession", "_ENGINE_NAMESPACE", "_ENGINE_FUNCTIONS",
                                "RULE_ORDER", "_CHARACTER_GLOBALS", "_PART_MODULES", "DEFAULT_SAVE_PATH",
                                "_speech_debug_trail", "create_session", "INITIAL_WORLD_STATE"})
        if never:
            report["reads_never_moved"].append([n, never])
        held_reads = sorted(r for r in reads if r in rows and rows[r]["module"] not in T4 and r != n)
        if held_reads:
            report["reads_later_or_held"].append([n, held_reads])
    else:
        if isinstance(node, ast.AnnAssign):
            report["annotated_assign"].append(n)
    if targets.get(n):
        report["census_target"].append([n, targets[n]])
# clusters split across modules / members staying
for cl in constant_clusters(game):
    mods = {module.get(c) for c in cl}
    if len(cl) > 1 and any(c in t4 for c in cl) and len(mods) > 1:
        report["split_cluster"].append([[c, module.get(c)] for c in cl])
# not-called tests naming a T4 target
nct = lock["not_called_tests"]
report["not_called_tests_count"] = [len(nct)]
# patch census sites for T4 names
surface_names = set(rows) | set(MAP.get("reexported", []))
sites = scan(ROOT, surface_names)
c = Counter(s["target"] for s in sites)
report["patched_sites_t4"] = sorted([[n, c[n]] for n in t4 if c[n]], key=lambda x: -x[1])
report["patched_sites_t4_sens"] = sorted([[n, c[n]] for n in t4_sens if c[n]], key=lambda x: -x[1])
# touching tests per module
touch = {}
for m in T4:
    names = {n for n in t4 if module[n] == m}
    touch[m] = touching_tests(ROOT, names) if names else []
report["touching_counts"] = {m: len(v) for m, v in touch.items()}
report["touching"] = touch
# source readers doc mentions
sr = (ROOT.parent / "docs/engine-split/source-readers.md").read_text(encoding="utf-8")
report["source_readers_mention"] = sorted(n for n in t4 if re.search(r"\b" + re.escape(n) + r"\b", sr))
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
for k, v in report.items():
    if k in ("touching",):
        continue
    print(k, len(v) if isinstance(v, list) else v)
    if isinstance(v, list) and k not in ("in_function_import", "reads_later_or_held", "census_import_targets_used",
                                         "patched_sites_t4", "free_non_engine_reads", "reads_never_moved"):
        for item in v[:40]:
            print("   ", item)
