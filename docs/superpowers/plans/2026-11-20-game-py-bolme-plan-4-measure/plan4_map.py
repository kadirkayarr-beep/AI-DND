"""Read-only: Plan 4 scope on the current tree. Every top-level name still in game.py gets the topic module that
Plan 3's module_map.py gave it on P3BASE (5ea18cc7), run with overrides-p4.json (Plan 3's overrides minus the twelve
held_plan4 entries, so the held names show their topic module) and --apply-misfits. Names missing from that map are NEW.
Usage: python plan4_map.py <ai-dnd root now> <topic-map.json> <out.json>
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1])
TOPIC = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
OUT = Path(sys.argv[3])
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from engine_split.inventory import top_level_index, call_graph  # noqa: E402
from engine_split.move_block import NEVER_MOVED  # noqa: E402

HELD_P3 = ["create_npc_from_ai", "commit_location_change", "advance_campaign_time", "generate_npc_id",
           "_ensure_location_entities", "_commit_travel_action", "_adventure_travel_reply", "_promote_scene_referent",
           "_handle_query", "update_world_state_from_player", "_settle_spoken_commitment",
           "_fallback_for_action_result", "_states_the_failed_check", "_fallback_narration", "_stands_by_their_words"]
T4 = {"character_rules", "places", "intent", "dialogue", "lore", "narration", "narration_safety",
      "living_world_turn", "new_game"}
T5 = {"combat_flow", "coin", "savefile", "schemas"}
topic = {r["name"]: r["module"] for r in TOPIC["rows"]}
game = ROOT / "game.py"
idx = [d for d in top_level_index(game) if d["kind"] not in ("import", "other")]
order, seen, lines, kind = [], set(), Counter(), {}
for d in idx:
    lines[d["name"]] += d["end"] - d["start"] + 1
    if d["name"] not in seen:
        seen.add(d["name"])
        order.append(d)
        kind[d["name"]] = d["kind"]
sens = json.loads((ROOT / "api/tests/engine_split_locks/sensitive.json").read_text(encoding="utf-8"))["functions"]
cg = call_graph(game)
callers = {}
for f, reads in cg.items():
    for r in reads:
        if r != f:
            callers.setdefault(r, set()).add(f)
rows = []
for d in order:
    n = d["name"]
    m = "never" if n in NEVER_MOVED else topic.get(n, "NEW")
    held = n in HELD_P3
    if m in T5 or (m in T4 and (n in sens or held)):
        scope = "plan4"
    elif m == "turn":
        scope = "plan5"
    elif m == "never":
        scope = "never"
    else:
        scope = "other"
    rows.append({"name": n, "kind": kind[n], "lines": lines[n], "module": m, "sensitive": n in sens,
                 "held_p3": held, "scope": scope, "start": d["start"], "callers": sorted(callers.get(n, ()))})
summary = {}
for r in rows:
    key = f"{r['scope']}|{r['module']}|{'S' if r['sensitive'] else '-'}{'H' if r['held_p3'] else ''}"
    s = summary.setdefault(key, {"names": 0, "lines": 0})
    s["names"] += 1
    s["lines"] += r["lines"]
json.dump({"rows": rows, "summary": summary}, OUT.open("w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"game.py names={len(rows)} lines={sum(1 for _ in game.open(encoding='utf-8'))}")
for k in sorted(summary):
    print(k, summary[k])
for k in sorted({(r["scope"], r["module"]) for r in rows if r["scope"] in ("plan4", "other")} | {("x", "NEW")}):
    names = [r["name"] for r in rows if (r["scope"], r["module"]) == k] if k[0] != "x" else \
        [r["name"] for r in rows if r["module"] == "NEW"]
    print(f"NAMES {k[0]}|{k[1]} ({len(names)}): {', '.join(names)}")
missing = [n for n in HELD_P3 if n not in seen]
print("HELD_P3_MISSING", missing)
