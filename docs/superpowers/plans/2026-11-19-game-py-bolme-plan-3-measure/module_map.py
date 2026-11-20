"""Read-only prototype: map every top-level name of game.py to a spec section 5 target module.

Rule (Ruling R1 in draft-report.md): game.py is ordered by topic. A region starts at an anchor name and runs to the
next anchor (file order). OVERRIDES name single exceptions. Then measurement: callers/callees per name from
inventory.call_graph; a non-sensitive function whose engine callers all sit in ONE other module is reported as a
misfit (and moved there with --apply-misfits). Constants follow their readers' module when every reader agrees.
Usage: python module_map.py <ai-dnd root> <out.json> [--apply-misfits]
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
APPLY = "--apply-misfits" in sys.argv
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from engine_split.inventory import top_level_index, call_graph  # noqa: E402
from engine_split.move_block import NEVER_MOVED  # noqa: E402

REGIONS = [
    ("ResolvedTurn", "turn"), ("get_modifier", "character_rules"), ("is_dialogue_or_emotion", "intent"),
    ("_SOMEONE_ELSES_PURSE", "coin"), ("_stealth_skill", "intent"), ("recent_dm_narrations", "never"),
    ("SAVE_FORMAT_VERSION", "savefile"), ("RULE_ORDER", "never"), ("_new_species_trait_state", "character_rules"),
    ("_origin_choices_valid", "savefile"), ("_tavern_door_notice", "places"), ("_narration_fact_packet", "narration"),
    ("_normalize_ground_items", "places"), ("_death_state_defaults", "combat_flow"), ("location_features", "places"),
    ("_SHOP_ECONOMY_PATTERN", "coin"), ("ensure_npc_combat_stats", "combat_flow"),
    ("validate_world_updates", "narration"), ("_conversation_npcs", "dialogue"), ("_narrator_shop_record", "narration"),
    ("location_display_name", "places"), ("ensure_campaign_clock", "living_world_turn"),
    ("commit_location_change", "places"), ("_intent_scene_npc_candidates", "intent"),
    ("_EXPERIMENTAL_NPC_SPEECH_SCHEMA", "dialogue"), ("_local_place_recommendation_options", "places"),
    ("IntentInfrastructureError", "intent"), ("_explicit_sword_drop", "places"), ("_current_npc_name", "narration"),
    ("_unregistered_persistent_object_claim", "narration_safety"), ("should_generate_npcs", "narration"),
    ("_empty_lore_authority_context", "lore"), ("_feature_refs_are_visible", "narration"),
    ("_record_narration_safety", "narration_safety"), ("_is_player_name_inquiry_to_npc", "dialogue"),
    ("_narrated_money_can_lie", "narration"), ("initialize_game", "new_game"), ("messages", "never"),
    ("DEBUG_MODE", "turn"), ("_commit_travel_action", "places"), ("_names_present_creature", "intent"),
    ("execute_intent", "turn"), ("_unsupported_available_quest_claim", "places"),
    ("_direct_npc_smalltalk_response", "dialogue"), ("_scene_names", "places"),
    ("plan_living_world_turn", "living_world_turn"), ("TurnResolved", "turn"), ("_death_closing", "combat_flow"),
    ("_last_call", "turn"), ("_death_resolution_from_actions", "combat_flow"), ("_owner_module_reply", "turn"),
    ("DEFAULT_SAVE_PATH", "never"), ("_restore_in_place", "turn"), ("GameSession", "never"),
    ("_dynamic_engine_transitions", "turn"), ("_session", "never"),
]
OVERRIDES = {
    "roll_attack": "character_rules", "roll_initiative": "character_rules", "roll_initiative_npc": "character_rules",
    "roll_initiative_player": "character_rules", "calculate_attack_bonus": "character_rules",
    "roll_damage": "character_rules", "execute_intent": "intent", "_said_to_someone_here": "dialogue",
    "_a_walk": "places", "_is_canonical_city_id": "places", "_adventure_travel_reply": "places",
    "_walked_there": "places", "_stock_hearer": "dialogue", "_may_propose_local_place": "places",
    "_accepted_local_place": "places", "_settle_local_place": "places", "_filter_unsupported_lore_paragraphs": "lore",
    "_living_world_prompt_context": "living_world_turn", "_STOCK_SAID": "dialogue",
    "_species_trait_state": "character_rules", "_thread_gate": "turn", "_carry_out_thread_turn": "turn",
    "INITIAL_WORLD_STATE": "never", "is_player_world_assertion": "narration_safety",
    "_narration_is_unsafe": "narration_safety", "_narration_safety_decision": "narration_safety",
}
EXTRA = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")) if len(sys.argv) > 3 and sys.argv[3].endswith(".json") else {}
OVERRIDES.update(EXTRA)

game = ROOT / "game.py"
idx = [d for d in top_level_index(game) if d["kind"] not in ("import", "other")]
order, seen = [], set()
for d in idx:
    if d["name"] not in seen:
        seen.add(d["name"])
        order.append(d)
lines = Counter()
for d in idx:
    lines[d["name"]] += d["end"] - d["start"] + 1
cg = call_graph(game)
sens = json.loads((ROOT / "api/tests/engine_split_locks/sensitive.json").read_text(encoding="utf-8"))["functions"]
lock = json.loads((ROOT / "api/tests/engine_split_locks/patch_census.json").read_text(encoding="utf-8"))
anchors = dict(REGIONS)
missing = [a for a in anchors if a not in seen] + [o for o in OVERRIDES if o not in seen]
assert not missing, missing
module, cur = {}, None
for d in order:
    cur = anchors.get(d["name"], cur)
    module[d["name"]] = "never" if d["name"] in NEVER_MOVED else OVERRIDES.get(d["name"], cur)
callers = {}
for f, reads in cg.items():
    for r in reads:
        if r != f:
            callers.setdefault(r, set()).add(f)
kind = {d["name"]: d["kind"] for d in order}
const_moves = {}
for n in module:
    if kind[n] == "assign" and module[n] != "never" and n not in OVERRIDES:
        mods = {module[c] for c in callers.get(n, ())}
        if len(mods) == 1:
            m = mods.pop()
            if m not in (module[n], "never"):
                const_moves[n] = (module[n], m)
for n, (_, b) in const_moves.items():
    module[n] = b
misfits = {}
for n in module:
    if kind[n] != "function" or n in sens or module[n] == "never" or n in OVERRIDES:
        continue
    mods = {module[c] for c in callers.get(n, ())}
    if len(mods) == 1:
        m = next(iter(mods))
        if m not in (module[n], "never"):
            misfits[n] = (module[n], m, sorted(callers[n]))
if APPLY:
    for n, (_, b, _c) in misfits.items():
        module[n] = b
rows = []
for d in order:
    n = d["name"]
    rows.append({"name": n, "kind": kind[n], "lines": lines[n], "module": module[n], "sensitive": sens.get(n),
                 "callers": sorted(callers.get(n, ())), "reads": cg.get(n, [])})
summary = {}
for r in rows:
    s = summary.setdefault(f"{r['module']}|{'S' if r['sensitive'] else '-'}", {"names": 0, "lines": 0})
    s["names"] += 1
    s["lines"] += r["lines"]
json.dump({"rows": rows, "misfits": misfits, "const_moves": const_moves, "summary": summary,
           "lock_keys": list(lock.keys())}, OUT.open("w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k in sorted(summary):
    print(k, summary[k])
print("misfits", len(misfits))
for n, (a, b, c) in sorted(misfits.items()):
    print(" ", n, a, "->", b, c[:4])
print("const_moves", const_moves)
print("lock keys", list(lock.keys()))
