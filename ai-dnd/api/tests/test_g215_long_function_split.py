"""G2.15 (D-516, D-549, D-552): the long functions are split without a change in behaviour.

Characterization: the scene-state validator and the weapon attack (prepare / resolve) give the same answers, the
same errors and the same state changes as before the split. The golden answers were taken from the code before the
split (fixed dice, fixed scenes; ids are masked).
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import action_economy as ae
import living_world
import weapon_attack as attack
from api.tests.test_action_economy import step
from api.tests.test_weapon_attack import armed, resolve
from combat_lifecycle import CombatRequestError
from weapon_catalog import lookup

HERE = Path(__file__).resolve().parent
GOLDEN_SCENE = HERE / "g215_scene_state_golden.json"
GOLDEN_WEAPON = HERE / "g215_weapon_attack_golden.json"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def masked(value):
    return json.loads(UUID.sub("<uuid>", json.dumps(value, sort_keys=True, default=str)))


def compare(test, golden_path, actual):
    """Each scenario's masked answer is kept as a sha256 (the full answers are large); a mismatch prints that answer."""
    actual = masked(actual)
    digests = {name: hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
               for name, value in actual.items()}
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    if golden != digests:
        print("G215-DIGESTS " + golden_path.name + " " + json.dumps(digests, sort_keys=True))
    test.assertEqual(set(digests), set(golden))
    for name in sorted(digests):
        with test.subTest(scenario=name):
            if digests[name] != golden[name]:
                print("G215-SCENARIO " + name + " " + json.dumps(actual[name], sort_keys=True, ensure_ascii=False))
            test.assertEqual(digests[name], golden[name])


def valid_scene_state():
    """Two scenes: a BLUE event whose referent link is made by the validator, a referent with an alias, an opening."""
    state = living_world.initial_scene_state()
    state["campaign_seed"] = "g215-seed"
    state["ambient_event_history"] = [{
        "event_id": "ev1", "instance_id": "inst1", "variation_id": "v1", "repeat_group": "g",
        "location_id": "loc_a", "turn_index": 3, "last_seen_turn": 3, "count": 1}]
    state["ambient_event_counts"] = {"ev1": 1}
    state["scenes"] = {
        "loc_a": {"id": "scene:loc_a", "location_id": "loc_a", "referents": [
            {"id": "r1", "description": "a lantern", "aliases": ["lamp"], "lifecycle": "presented",
             "event_instance_id": None, "source_turn": 3}],
            "ambient_event": {"event_id": "ev1", "instance_id": "inst1", "variation_id": "v1",
                              "event_type": "BLUE", "repeat_group": "g", "count": 1},
            "opening": {"text": "Dusk.", "tone": "calm", "event_id": "ev1", "variation_id": "v1"}},
        "loc_b": {"id": "scene:loc_b", "location_id": "loc_b", "referents": []},
    }
    return state


def world(**changes):
    state = valid_scene_state()
    for path, value in changes.items():
        target = state
        keys = path.split("__")
        for key in keys[:-1]:
            target = target[int(key)] if isinstance(target, list) else target[key]
        if isinstance(target, list):
            target[int(keys[-1])] = value
        else:
            target[keys[-1]] = value
    return {"location": "loc_a", "locations": {}, "npcs": [], "features": [], "flags": {}, "scene_state": state}


def entry_reference(**changes):
    ref = {"source_action_id": "act", "source_kind": "local_search", "source_turn_index": 4,
           "expires_after_turn_index": 5, "source_location_id": "loc_a", "location_id": "loc_b", "door_id": "d1"}
    ref.update(changes)
    return ref


SCENE_CASES = {
    "valid": world(),
    "no_state": {"features": []},
    "state_not_dict": {"scene_state": []},
    "bad_schema": world(schema_version=2),
    "scenes_not_dict": world(scenes=[]),
    "seed_too_long": world(campaign_seed="x" * 65),
    "context_not_dict": world(ambient_context=[]),
    "history_not_list": world(ambient_event_history={}),
    "counts_not_dict": world(ambient_event_counts=[]),
    "count_zero": world(ambient_event_counts={"ev1": 0}),
    "count_bool": world(ambient_event_counts={"ev1": True}),
    "count_name_long": world(ambient_event_counts={"k" * 97: 1}),
    "context_extra_field": world(ambient_context={"environment": "a", "time_of_day": "b", "weather": "c",
                                                "background": "d", "origin": "e", "more": "f"}),
    "context_not_str": world(ambient_context={"environment": 1, "time_of_day": "b", "weather": "c",
                                              "background": "d", "origin": "e"}),
    "context_background_long": world(ambient_context={"environment": "a", "time_of_day": "b", "weather": "c",
                                                      "background": "d" * 97, "origin": "e"}),
    "history_seen_mismatch": world(ambient_event_history__0__last_seen_turn=9),
    "history_not_dict": world(ambient_event_history=[1]),
    "counter_zero": world(next_referent_number=0),
    "counter_bool": world(next_feature_number=True),
    "references_not_list": world(proposal_references={}),
    "references_too_many": world(proposal_references=list(range(25))),
    "entry_ok": world(entry_target_reference=entry_reference()),
    "entry_kind_bad": world(entry_target_reference=entry_reference(source_kind="x")),
    "entry_expiry_bad": world(entry_target_reference=entry_reference(expires_after_turn_index=7)),
    "entry_missing_field": world(entry_target_reference={"source_action_id": "act"}),
    "entry_door_empty": world(entry_target_reference=entry_reference(door_id="")),
    "scene_location_mismatch": world(scenes__loc_a__location_id="loc_x"),
    "scene_referents_not_list": world(scenes__loc_b__referents=None),
    "scene_referent_alias_many": world(scenes__loc_a__referents=[
        {"id": "r1", "description": "d", "aliases": list("abcdefghi"), "lifecycle": "presented"}]),
    "scene_referent_lifecycle_bad": world(scenes__loc_a__referents=[
        {"id": "r1", "description": "d", "aliases": [], "lifecycle": "gone"}]),
    "scene_opening_long": world(scenes__loc_a__opening={"text": "x" * 1801, "tone": "t", "event_id": "e",
                                                         "variation_id": "v"}),
    "scene_opening_none": world(scenes__loc_a__opening=None),
    "scene_event_type_bad": world(scenes__loc_a__ambient_event={
        "event_id": "ev1", "instance_id": "inst1", "variation_id": "v1", "event_type": "RED",
        "repeat_group": "g", "count": 1}),
    "scene_event_green": world(scenes__loc_a__ambient_event={
        "event_id": "ev1", "instance_id": "inst1", "variation_id": "v1", "event_type": "GREEN",
        "repeat_group": "g", "count": 1}),
    "scene_event_blue_no_referent": world(scenes__loc_a__referents=[], scenes__loc_a__ambient_event={
        "event_id": "ev1", "instance_id": "inst1", "variation_id": "v1", "event_type": "BLUE",
        "repeat_group": "g", "count": 1}),
    "scene_event_blue_other_turn": world(scenes__loc_a__referents=[
        {"id": "r1", "description": "d", "aliases": [], "lifecycle": "presented", "event_instance_id": None,
         "source_turn": 99}]),
    "scene_event_blue_linked": world(scenes__loc_a__referents=[
        {"id": "r1", "description": "d", "aliases": [], "lifecycle": "presented", "event_instance_id": "inst1"}]),
    "referents_over_total": world(**{f"scenes__s{i}": {"id": f"scene:s{i}", "location_id": f"s{i}",
                                                       "referents": [{"id": f"r{i}{j}", "description": "d",
                                                                      "aliases": [], "lifecycle": "presented"}
                                                                     for j in range(6)]} for i in range(41)}),
    "too_many_scenes": world(**{f"scenes__t{i}": {} for i in range(81)}),
    "state_too_big": world(**{f"scenes__b{i}": {"id": f"scene:b{i}", "location_id": f"b{i}", "referents": [],
                                                "opening": {"text": "x" * 1800, "tone": "t", "event_id": "e",
                                                            "variation_id": "v"}} for i in range(60)}),
    "features_ok": {**world(), "features": [{"id": "feature_7"}, {"id": "other"}]},
    "features_dup": {**world(), "features": [{"id": "feature_1"}, {"id": "feature_1"}]},
    "features_no_id": {**world(), "features": [{"name": "x"}]},
    "features_not_dict": {**world(), "features": [1]},
    "features_not_list": {**world(), "features": {}},
}


def scene_outcome(world_state):
    world_state = copy.deepcopy(world_state)
    try:
        state = living_world.ensure_scene_state(world_state)
    except ValueError as error:
        return {"error": str(error), "world": world_state}
    return {"state": state, "world": world_state}


class SceneStateIsUnchanged(unittest.TestCase):
    def test_every_case_gives_the_same_answer_error_and_mutation(self):
        compare(self, GOLDEN_SCENE, {name: scene_outcome(case) for name, case in SCENE_CASES.items()})


def outcome(s, n, run):
    """Run one attack and keep the answer (or the refusal code) and what the world kept."""
    try:
        answer = run()
    except CombatRequestError as error:
        answer = {"refused": error.code}
    return {"answer": answer, "npc": {k: n.get(k) for k in ("current_hp", "conditions", "combat_status")},
            "player_conditions": s.character.get("conditions"),
            "equipment": s.world_state.get("equipment"), "inventory": s.world_state.get("inventory"),
            "ammunition": s.world_state.get("ammunition"), "spent": s.world_state.get("spent_thrown_weapons"),
            "effects": s.world_state.get("attack_effects"), "history": len(s.world_state.get("attack_results", [])),
            "economy": s.world_state.get("combat", {}).get("turn_resources")}


def context(s, n, weapon, choice=None, origin="action"):
    with patch("game.roll_attack", side_effect=AssertionError("prepare rolled")):
        return attack.prepare(s, "player", n["id"], weapon, choice, origin=origin)


def play(weapon="Longsword", choice=None, *, rolls=(10,), origin="action", mastery=False, distance=5, tweak=None, held=None):
    s, n = armed(held or (weapon if lookup(weapon) else "Longsword"), mastery=mastery, distance=distance)
    if tweak:
        tweak(s, n)
    prepared = outcome(s, n, lambda: context(s, n, weapon, choice, origin))
    result = outcome(s, n, lambda: resolve(s, n, weapon, choice, rolls=(*rolls, 10), origin=origin))
    return {"prepare": prepared["answer"], "resolve": result}


def prone_target(s, n):
    n["conditions"] = ["prone"]


def poisoned(s, n):
    s.character["conditions"] = ["poisoned"]


def half_cover(s, n):
    s.world_state["attack_environment"] = {"pairs": {f"player|{n['id']}": {"distance_ft": 5, "cover": "half"}}}


def total_cover(s, n):
    s.world_state["attack_environment"] = {"pairs": {f"player|{n['id']}": {"distance_ft": 5, "cover": "total"}}}


def underwater(s, n):
    s.world_state["attack_environment"] = {"underwater": True}


def hidden(s, n):
    s.character["hidden"] = True


def no_bolts(s, n):
    s.world_state["ammunition"]["bolt"] = 0


def dart_stack(s, n):
    s.world_state["inventory"] = ["10 Dart"]


def two_daggers(s, n):
    s.world_state["inventory"] = [{"weapon_id": "dagger", "item_id": "first"},
                                  {"weapon_id": "dagger", "item_id": "second"}]
    s.world_state["equipment"] = {"main_hand": "first", "off_hand": "second"}


def light_pair():
    s, n = armed("Shortsword")
    s.world_state["inventory"].append("Dagger")
    s.world_state["equipment"]["off_hand"] = "dagger"
    with patch("game.roll_attack", return_value=10), patch.object(s.rng, "randint", return_value=3):
        step(s, {"kind": "attack", "target_id": n["id"]})
    prepared = outcome(s, n, lambda: context(s, n, "Dagger", None, "light"))
    with patch("game.roll_attack", return_value=10), patch.object(s.rng, "randint", return_value=3):
        result = outcome(s, n, lambda: ae.attack_step(s, n["id"], weapon_id="dagger", origin="light")["result"])
    return {"prepare": prepared["answer"], "resolve": result}


def weapon_scenarios():
    return {
        "hit": lambda: play(),
        "miss": lambda: play(rolls=(2,)),
        "critical": lambda: play(rolls=(20,)),
        "natural_one": lambda: play(rolls=(1,)),
        "target_prone_advantage": lambda: play(rolls=(10, 15), tweak=prone_target),
        "poisoned_disadvantage": lambda: play(rolls=(10, 15), tweak=poisoned),
        "half_cover": lambda: play(tweak=half_cover),
        "total_cover": lambda: play(tweak=total_cover),
        "underwater_sword": lambda: play("Mace", tweak=underwater),
        "hidden_attacker": lambda: play(tweak=hidden),
        "two_handed_grip": lambda: play(choice={"grip": 2}),
        "bad_grip": lambda: play(choice={"grip": 3}),
        "finesse_dex": lambda: play("Rapier", {"ability": "dexterity"}),
        "bad_ability": lambda: play(choice={"ability": "dexterity"}),
        "bow": lambda: play("Shortbow", distance=30),
        "bow_long_range": lambda: play("Shortbow", distance=200, rolls=(10, 15)),
        "bow_no_ammunition": lambda: play("Light Crossbow", distance=30, tweak=no_bolts),
        "bow_out_of_range": lambda: play("Shortbow", distance=500),
        "thrown_javelin": lambda: play("Javelin", {"mode": "thrown"}, distance=20),
        "thrown_dart_stack": lambda: play("Dart", {"mode": "thrown"}, distance=10, tweak=dart_stack),
        "thrown_bad_mode": lambda: play("Longsword", {"mode": "thrown"}),
        "melee_too_far": lambda: play(distance=30),
        "mastery_sap": lambda: play(mastery=True),
        "mastery_none": lambda: play("Warhammer", {"mastery": "none"}, mastery=True),
        "mastery_push": lambda: play("Warhammer", {"push_ft": 5}, mastery=True),
        "mastery_push_bad": lambda: play("Warhammer", {"push_ft": 15}, mastery=True),
        "mastery_topple": lambda: play("Quarterstaff", mastery=True),
        "mastery_vex": lambda: play("Rapier", mastery=True),
        "mastery_graze_miss": lambda: play("Greatsword", mastery=True, rolls=(2,)),
        "mastery_unavailable": lambda: play(choice={"mastery": "sap"}),
        "cleave_unavailable": lambda: play(choice={"cleave_target_id": "nobody"}),
        "unknown_choice": lambda: play(choice={"mana": 5}),
        "knock_out_not_bool": lambda: play(choice={"knock_out": "yes"}),
        "knock_out": lambda: play(choice={"knock_out": True}),
        "reckless_unavailable": lambda: play(choice={"reckless_attack": True}),
        "unknown_weapon": lambda: play("Lightsaber"),
        "weapon_not_held": lambda: play("Dagger", tweak=lambda s, n: s.world_state.update(inventory=[])),
        "draw_weapon": lambda: play("Dagger", {"draw": True}, tweak=lambda s, n: s.world_state["inventory"].append("Dagger")),
        "unequip": lambda: play(choice={"unequip": "longsword"}),
        "bad_origin": lambda: play(origin="mystery"),
        "continuation_without_action": lambda: play(origin="continuation"),
        "nick_without_light": lambda: play("Dagger", origin="nick", mastery=True, tweak=two_daggers),
        "two_daggers_first": lambda: play("Dagger", {"weapon_instance_id": "first"}, tweak=two_daggers),
        "unarmed": lambda: play("unarmed"),
        "unarmed_grapple": lambda: play("unarmed", {"unarmed_option": "grapple"}),
        "unarmed_shove_prone": lambda: play("unarmed", {"unarmed_option": "shove"}),
        "unarmed_shove_push": lambda: play("unarmed", {"unarmed_option": "shove", "shove_option": "push"}),
        "unarmed_bad_option": lambda: play("unarmed", {"unarmed_option": "bite"}),
        "weapon_bad_unarmed_option": lambda: play(choice={"unarmed_option": "grapple"}),
        "light_second_attack": light_pair,
    }


class WeaponAttackIsUnchanged(unittest.TestCase):
    def test_every_attack_gives_the_same_context_result_and_state_changes(self):
        compare(self, GOLDEN_WEAPON, {name: run() for name, run in weapon_scenarios().items()})


__all__ = ["SceneStateIsUnchanged", "WeaponAttackIsUnchanged"]

if __name__ == "__main__":
    unittest.main()
