"""Monster Combat: real owners, explicit perception and deterministic scenarios."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import game
import initiative
import action_economy as ae
import weapon_attack as attack
import monster_combat as ai
import monster_capabilities as capabilities
import monster_perception as perception
from combat_lifecycle import CombatRequestError
from api.tests.test_combat_lifecycle import ready
from api.tests import test_combat_lifecycle as lifecycle_tests


def claw(identity="claw", source="action", **extra):
    return {"capability_id": identity, "kind": "attack", "action_source": source,
            "profile": {"weapon_id": identity, "name": identity, "kind": "melee",
                        "category": None, "properties": [], "mastery": None,
                        "attack_bonus": 4, "damage_die": 6, "damage_dice": 1,
                        "damage_modifier": 2, "damage_type": "slashing",
                        "magic_attack_bonus": 0, "magic_damage_bonus": 0}, **extra}


def fixture(caps=None, session=None, **data):
    s, n = ready(session)
    s.character.update(current_hp=1000, max_hp=1000, faction="heroes", conditions=[])
    n.update(armor_class=12, current_hp=100, max_hp=100, intelligence=12, wisdom=10,
             speed_ft=30, languages=["Common"], faction="raiders",
             faction_relationships={"heroes": "enemy"}, **data)
    n["monster_stat_block"] = {"source": "explicit_test_fixture",
                              "capabilities": copy.deepcopy(caps if caps is not None else [claw()])}
    s.world_state["monster_perception"] = {n["id"]: {"player": {"visible": True}}}
    s.world_state["attack_environment"] = {"pairs": {
        n["id"] + "|player": {"distance_ft": 5, "attacker_sees_target": True,
                             "target_sees_attacker": True}}}
    return s, n


def activate(s, n):
    s.advance_combat_turn()
    assert s.world_state["combat"]["current_actor_id"] == n["id"]


def run(s, n, **kwargs):
    with patch("game.roll_attack", return_value=12):
        return ai.run_turn(s, n["id"], **kwargs)


def add_creature(s, n, relation="enemy", **data):
    other = s.create_npc_from_ai({"name": "Other", "role": "Guard", "location": "tavern"})
    other.update(current_hp=100, max_hp=100, armor_class=12, speed_ft=30,
                 attack_damage_type="slashing", distance_ft=5)
    other.update(data)
    n.setdefault("combat_relationships", {})[other["id"]] = relation
    with patch("game.roll_initiative", return_value=1):
        s.join_combat_participants([other["id"]])
    s.world_state["attack_environment"]["pairs"][n["id"] + "|" + other["id"]] = {"distance_ft": 5}
    s.world_state["monster_perception"][n["id"]][other["id"]] = {"visible": True}
    return other


class MonsterTests(unittest.TestCase):
    def assert_rejected_unchanged(self, s, callback):
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        with self.assertRaises((CombatRequestError, ValueError)):
            callback()
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_shared_attack_owner_real_damage_and_resource(self):
        s, n = fixture()
        activate(s, n)
        result = run(s, n)
        self.assertEqual(result["decisions"][0]["target_ids"], ["player"])
        self.assertEqual(len(result["outcomes"]), 1)
        self.assertEqual(s.character["current_hp"], 1000 - result["outcomes"][0]["damage"])
        self.assertTrue(ae.ensure(s)[n["id"]]["base_action_spent"])
        self.assertEqual(result["outcomes"][0]["attack_bonus"], 4)

    def test_wrong_actor_rejected_before_rng_or_resource(self):
        s, n = fixture()
        self.assert_rejected_unchanged(s, lambda: run(s, n))

    def test_stale_turn_rejected(self):
        s, n = fixture()
        activate(s, n)
        self.assert_rejected_unchanged(s, lambda: run(s, n, expected_turn_id="stale"))

    def test_duplicate_turn_no_extra_damage_rng_or_resources(self):
        s, n = fixture()
        activate(s, n)
        result = run(s, n)
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        self.assertEqual(run(s, n), result)
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_save_resume_checkpoint_replay(self):
        s, n = fixture()
        activate(s, n)
        result = run(s, n)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "campaign.json"
            s.save_game(path)
            other = game.GameSession(seed=987)
            other.load_game(path)
        before = copy.deepcopy((other.world_state, other.character, other.rng.getstate()))
        self.assertEqual(ai.run_turn(other, n["id"], expected_turn_id=result["turn_id"]), result)
        self.assertEqual((other.world_state, other.character, other.rng.getstate()), before)

    def test_transaction_failure_restores_full_state(self):
        s, n = fixture([claw(uses=1, restore="long_rest")])
        activate(s, n)
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate(), s.messages))
        def failure():
            raise RuntimeError("forced persistence failure")
        with self.assertRaisesRegex(RuntimeError, "persistence"):
            run(s, n, commit=failure)
        self.assertEqual((s.world_state, s.character, s.rng.getstate(), s.messages), before)

    def test_session_isolation(self):
        a, n = fixture()
        b, _ = fixture()
        before = copy.deepcopy((b.world_state, b.character, b.rng.getstate()))
        activate(a, n)
        run(a, n)
        self.assertEqual((b.world_state, b.character, b.rng.getstate()), before)

    def test_missing_perception_never_assumed(self):
        s, n = fixture()
        s.world_state["monster_perception"] = {}
        s.world_state["attack_environment"]["pairs"][n["id"] + "|player"].pop("attacker_sees_target")
        activate(s, n)
        result = run(s, n)
        self.assertFalse(any(o["action"] == "enemy_attack" for o in result["outcomes"]))

    def test_hidden_target_no_coordinate_or_secret_defense_leak(self):
        s, n = fixture()
        s.character.update(hidden=True, resistances=["fire"], position={"x": 444})
        view = perception.snapshot(s, n["id"], ai.state(s, n["id"]))
        self.assertEqual(view["targets"], [])
        self.assertNotIn("444", repr(view))
        self.assertNotIn("resistances", repr(view))

    def test_invisible_target_not_targeted_without_sense(self):
        s, n = fixture()
        s.character["conditions"] = ["invisible"]
        activate(s, n)
        result = run(s, n)
        self.assertFalse(any(o["action"] == "enemy_attack" for o in result["outcomes"]))

    def test_verified_blindsight_finds_invisible_not_hidden(self):
        s, n = fixture()
        n["senses"] = {"blindsight": 30}
        s.character["conditions"] = ["invisible"]
        s.world_state["monster_perception"][n["id"]]["player"]["verified_senses"] = ["blindsight"]
        view = perception.snapshot(s, n["id"], ai.state(s, n["id"]))
        self.assertEqual([t["id"] for t in view["targets"]], ["player"])
        s.character["hidden"] = True
        self.assertEqual(perception.snapshot(s, n["id"], ai.state(s, n["id"]))["targets"], [])

    def test_hidden_perception_check_owner_can_reveal(self):
        s, n = fixture()
        s.character["hidden"] = True
        s.world_state["monster_perception"][n["id"]]["player"].update(located=True, source="perception_check")
        self.assertEqual(len(perception.snapshot(s, n["id"], ai.state(s, n["id"]))["targets"]), 1)

    def test_last_known_is_not_current_hidden_coordinates(self):
        s, n = fixture()
        fact = s.world_state["monster_perception"][n["id"]]["player"]
        fact.update(position_known=True, position={"x": 1})
        memory = ai.state(s, n["id"])
        perception.snapshot(s, n["id"], memory)
        s.character["hidden"] = True
        fact["position"] = {"x": 999}
        self.assertEqual(perception.snapshot(s, n["id"], memory)["targets"], [])
        self.assertEqual(memory["last_known"]["player"]["position"], {"x": 1})

    def test_secret_resistance_never_in_snapshot(self):
        s, n = fixture()
        s.character["resistances"] = ["fire"]
        memory = ai.state(s, n["id"])
        self.assertEqual(perception.snapshot(s, n["id"], memory)["targets"][0]["beliefs"], {})

    def test_observed_resistance_is_belief_not_exact_target_stats(self):
        s, n = fixture()
        cap = n["monster_stat_block"]["capabilities"][0]
        cap["profile"]["damage_type"] = "fire"
        s.character["resistances"] = ["fire"]
        activate(s, n)
        run(s, n)
        beliefs = ai.state(s, n["id"])["observations"]["player"]["beliefs"]
        self.assertEqual(beliefs, {"fire": "suspected_resistant"})

    def test_neutral_is_not_automatically_enemy(self):
        s, n = fixture()
        n["faction_relationships"]["heroes"] = "neutral"
        activate(s, n)
        self.assertFalse(any(o["action"] == "enemy_attack" for o in run(s, n)["outcomes"]))

    def test_monster_vs_monster_and_friendly_ally(self):
        s, n = fixture()
        other = add_creature(s, n, "enemy")
        n["combat_relationships"]["player"] = "ally"
        activate(s, n)
        result = run(s, n)
        self.assertEqual(result["decisions"][0]["target_ids"], [other["id"]])
        self.assertEqual(s.character["current_hp"], 1000)
        self.assertLess(other["current_hp"], 100)

    def test_high_observed_threat_can_outweigh_equal_distance(self):
        s, n = fixture()
        other = add_creature(s, n)
        ai.state(s, n["id"])["observations"][other["id"]] = {"threat": 12, "beliefs": {}}
        activate(s, n)
        self.assertEqual(run(s, n)["decisions"][0]["target_ids"], [other["id"]])

    def test_objective_protection_uses_visible_canonical_facts(self):
        s, n = fixture(combat_objective={"kind": "guard_objective", "object_id": "door"})
        other = add_creature(s, n)
        s.world_state["monster_perception"][n["id"]][other["id"]]["near_objective"] = True
        activate(s, n)
        self.assertEqual(run(s, n)["decisions"][0]["target_ids"], [other["id"]])

    def test_down_to_zero_reprioritizes_active_threat(self):
        s, n = fixture()
        other = add_creature(s, n)
        other.update(current_hp=0, combat_status="unconscious")
        activate(s, n)
        self.assertEqual(run(s, n)["decisions"][0]["target_ids"], ["player"])

    def test_multiattack_exact_stat_block_slots(self):
        multi = {"capability_id": "multi", "kind": "multiattack", "action_source": "action",
                 "attack_slots": [["claw"], ["claw"], ["claw"]]}
        s, n = fixture([claw(), multi])
        activate(s, n)
        result = run(s, n)
        self.assertEqual(len(result["outcomes"]), 3)
        self.assertEqual(result["decisions"][0]["attack_sequence"], ["claw"] * 3)
        self.assertTrue(ae.ensure(s)[n["id"]]["base_action_spent"])

    def test_multiattack_choice_combinations(self):
        multi = {"capability_id": "multi", "kind": "multiattack", "action_source": "action",
                 "attack_slots": [["claw", "bite"], ["claw", "bite"]]}
        s, n = fixture([claw(), claw("bite"), multi])
        activate(s, n)
        result = run(s, n)
        self.assertIn(result["decisions"][0]["attack_sequence"],
                      capabilities.sequences(multi, capabilities.capabilities(s, n["id"])))
        self.assertEqual(len(result["outcomes"]), 2)

    def test_no_invented_multiattack(self):
        s, n = fixture()
        activate(s, n)
        self.assertEqual(len(run(s, n)["outcomes"]), 1)

    def test_bonus_attack_spends_only_bonus_resource_once(self):
        s, n = fixture([claw(), claw("bonus", "bonus")])
        activate(s, n)
        result = run(s, n)
        self.assertEqual(len(result["outcomes"]), 2)
        r = ae.ensure(s)[n["id"]]
        self.assertTrue(r["base_action_spent"])
        self.assertTrue(r["bonus_action_spent"])
        self.assertEqual(run(s, n), result)

    def test_recharge_used_then_only_start_boundary_roll(self):
        s, n = fixture([claw(recharge=[5, 6])])
        activate(s, n)
        run(s, n)
        memory = ai.state(s, n["id"])
        self.assertFalse(memory["resources"]["claw"]["available"])
        before = s.rng.getstate()
        ai.begin_turn(s, n["id"])
        self.assertEqual(s.rng.getstate(), before)
        s.advance_combat_turn()
        with patch.object(s.rng, "randint", return_value=6) as roll:
            s.advance_combat_turn()
        self.assertEqual(roll.call_count, 1)
        self.assertTrue(memory["resources"]["claw"]["available"])
        self.assertEqual(memory["recharge_rolls"][0]["roll"], 6)

    def test_recharge_unavailable_not_selected(self):
        s, n = fixture([claw(recharge=[5, 6])])
        activate(s, n)
        memory = ai.state(s, n["id"])
        memory["resources"]["claw"]["available"] = False
        self.assertFalse(any(o["action"] == "enemy_attack" for o in run(s, n)["outcomes"]))

    def test_limited_use_not_exceeded_and_rest_restores_exact_rule(self):
        s, n = fixture([claw(uses=1, restore="long_rest")])
        activate(s, n)
        run(s, n)
        memory = ai.state(s, n["id"])
        self.assertEqual(memory["resources"]["claw"]["remaining"], 0)
        ai.restore_resources(s, n["id"], "short_rest")
        self.assertEqual(memory["resources"]["claw"]["remaining"], 0)
        ai.restore_resources(s, n["id"], "long_rest")
        self.assertEqual(memory["resources"]["claw"]["remaining"], 1)

    def test_legendary_after_another_turn_and_one_window(self):
        s, n = fixture([claw(), claw("legendary", "legendary", cost=1)])
        n["monster_stat_block"]["legendary_uses"] = 2
        before = s.character["current_hp"]
        with patch("game.roll_attack", return_value=12):
            ae.monster_event(s, "after_turn", "player")
        self.assertLess(s.character["current_hp"], before)
        event = s.world_state["combat"]["monster_event"]
        old = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        result = ai.window(s, n["id"], "legendary")
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), old)
        self.assertTrue(result["decisions"])
        self.assertEqual(result["window_id"].split(":")[-1], "legendary")
        self.assertEqual(s.world_state["combat"]["monster_event"], event)

    def test_legendary_own_turn_window_rejected(self):
        s, n = fixture([claw("legendary", "legendary")])
        n["monster_stat_block"]["legendary_uses"] = 2
        activate(s, n)
        ae.monster_event(s, "after_turn", n["id"])
        self.assert_rejected_unchanged(s, lambda: ai.window(s, n["id"], "legendary"))

    def test_legendary_lair_budget_uses_authoritative_boolean(self):
        s, n = fixture([claw("legendary", "legendary")])
        n["monster_stat_block"].update(legendary_uses=2, lair_legendary_uses=4, in_lair=False)
        activate(s, n)
        self.assertEqual(ai.state(s, n["id"])["legendary_remaining"], 2)
        n["monster_stat_block"]["in_lair"] = True
        s.advance_combat_turn()
        s.advance_combat_turn()
        self.assertEqual(ai.state(s, n["id"])["legendary_remaining"], 4)

    def test_reaction_trigger_and_no_double_spend(self):
        s, n = fixture([claw(), claw("retaliate", "reaction", trigger="actor_attacks",
                                   target_restriction="trigger_actor")])
        with patch("game.roll_attack", return_value=12):
            ae.publish_event(s, "actor_attacks", "player")
        self.assertTrue(ae.ensure(s)[n["id"]]["reaction_spent"])
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        ai.window(s, n["id"], "reaction")
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_wrong_reaction_trigger_no_spend(self):
        s, n = fixture([claw("retaliate", "reaction", trigger="incoming_hit")])
        ae.publish_event(s, "actor_moves", "player")
        self.assertFalse(ae.ensure(s)[n["id"]]["reaction_spent"])

    def test_legendary_resistance_severe_only_and_bounded(self):
        lr = {"capability_id": "lr", "kind": "legendary_resistance", "action_source": "resistance",
              "uses": 1, "restore": "long_rest"}
        s, n = fixture([claw(), lr])
        ae.monster_event(s, "failed_save", "player", target_id=n["id"], severity="minor")
        self.assertNotIn("save_override", ai.window(s, n["id"], "resistance"))
        ae.monster_event(s, "failed_save", "player", target_id=n["id"], severity="paralysis")
        result = ai.window(s, n["id"], "resistance")
        self.assertEqual(result["save_override"], "SUCCESS")
        before = s.rng.getstate()
        self.assertEqual(ai.window(s, n["id"], "resistance"), result)
        self.assertEqual(s.rng.getstate(), before)
        self.assertEqual(ai.state(s, n["id"])["resources"]["lr"]["remaining"], 0)
        ae.monster_event(s, "failed_save", "player", target_id=n["id"], severity="lethal")
        self.assertNotIn("save_override", ai.window(s, n["id"], "resistance"))

    def test_spell_hook_missing_does_not_fake_damage_or_resource(self):
        spell = {"capability_id": "spells", "kind": "spell", "action_source": "action",
                 "spell_ids": ["shield"], "uses": 1, "restore": "long_rest", "powerful": True}
        s, n = fixture([spell])
        activate(s, n)
        result = run(s, n)
        self.assertEqual(s.character["current_hp"], 1000)
        self.assertEqual(ai.state(s, n["id"])["resources"]["spells"]["remaining"], 1)
        self.assertFalse(any(d["capability_id"] == "spells" for d in result["decisions"]))

    def test_spell_owner_hook_receives_only_listed_intent(self):
        spell = {"capability_id": "spells", "kind": "spell", "action_source": "action",
                 "spell_ids": ["shield"], "powerful": True}
        s, n = fixture([spell])
        def legal(*args):
            return [{"spell_id": "shield", "target_ids": [n["id"]]},
                    {"spell_id": "invented", "target_ids": [n["id"]]}]
        received = []
        def owner(session, actor, cap, intent):
            received.append(intent)
            return {"status": "resolved", "action": "owner_spell_fixture", "damage": 0}
        capabilities.register_executor(s, "spell", legal=legal, resolve=owner)
        activate(s, n)
        run(s, n)
        self.assertEqual([i["spell_id"] for i in received], ["shield"])
        self.assertEqual(s.character["current_hp"], 1000)

    def test_unresolved_owner_rolls_back_without_faked_success(self):
        s, n = fixture([{"capability_id": "breath", "kind": "special", "action_source": "action",
                         "powerful": True, "recharge": [5, 6]}])
        capabilities.register_executor(s, "special", legal=lambda *args: [{"target_ids": ["player"]}],
                                       resolve=lambda *args: {"status": "handoff"})
        activate(s, n)
        self.assert_rejected_unchanged(s, lambda: run(s, n))

    def test_owner_cannot_target_hidden_creature(self):
        s, n = fixture([{"capability_id": "special", "kind": "special", "action_source": "action"}])
        s.character["hidden"] = True
        capabilities.register_executor(s, "special", legal=lambda *args: [{"target_ids": ["player"]}],
                                       resolve=lambda *args: self.fail("hidden target executed"))
        activate(s, n)
        self.assertFalse(any(d["capability_id"] == "special" for d in run(s, n)["decisions"]))

    def test_movement_owner_budget_and_no_teleport(self):
        s, n = fixture([{"capability_id": "move", "kind": "movement", "action_source": "action"}])
        def legal(*args):
            return [{"target_ids": [], "movement_intent": "CLOSE_DISTANCE",
                     "distance_ft": 10, "destination": "known_door"}]
        def owner(session, actor, cap, intent):
            movement = ae.move(session, actor, intent["distance_ft"])
            # This is a fixture owner, not a production geometry implementation.
            return {"status": "resolved", "action": "fixture_movement", **movement}
        capabilities.register_executor(s, "movement", legal=legal, resolve=owner)
        activate(s, n)
        run(s, n)
        self.assertEqual(ae.ensure(s)[n["id"]]["movement_used"], 10)
        self.assertEqual(n["distance_ft"], 5)

    def test_movement_owner_excess_speed_rollback(self):
        s, n = fixture([{"capability_id": "move", "kind": "movement", "action_source": "action"}])
        capabilities.register_executor(s, "movement",
            legal=lambda *args: [{"target_ids": [], "distance_ft": 100}],
            resolve=lambda session, actor, cap, intent: ae.move(session, actor, intent["distance_ft"]))
        activate(s, n)
        self.assert_rejected_unchanged(s, lambda: run(s, n))

    def test_coward_cornered_can_propose_terms_not_end_combat(self):
        s, n = fixture(personality="cowardly")
        n["current_hp"] = 20
        n["conditions"] = ["frightened"]
        activate(s, n)
        result = run(s, n)
        self.assertIn(result["decisions"][0]["decision_type"], {"PARLEY_PROPOSED", "SURRENDER_PROPOSED"})
        self.assertTrue(s.world_state["combat"]["active"])
        proposal = ai.state(s, n["id"])["proposals"][0]
        ai.proposal_response(s, n["id"], proposal["proposal_id"], False)
        self.assertEqual(proposal["status"], "rejected")
        self.assertTrue(s.world_state["combat"]["active"])

    def test_fanatic_keeps_fighting_bloodied_and_frightened(self):
        s, n = fixture(personality="fanatical")
        n.update(current_hp=10, conditions=["frightened"])
        activate(s, n)
        self.assertEqual(run(s, n)["decisions"][0]["decision_type"], "ATTACK")

    def test_bloodied_alone_does_not_force_flee(self):
        s, n = fixture(personality="brave")
        n["current_hp"] = 50
        activate(s, n)
        self.assertEqual(run(s, n)["decisions"][0]["decision_type"], "ATTACK")

    def test_personality_and_objective_not_rerolled(self):
        s, n = fixture(personality="greedy", combat_objective={"kind": "protect_treasure"})
        activate(s, n)
        run(s, n)
        memory = ai.state(s, n["id"])
        s.advance_combat_turn()
        s.advance_combat_turn()
        self.assertEqual(memory["personality"], "greedy")
        self.assertEqual(memory["objective"], {"kind": "protect_treasure"})

    def test_group_communication_no_omniscient_target_sharing(self):
        s, n = fixture()
        leader = add_creature(s, n, "ally", languages=["Common"])
        leader["monster_orders"] = {"target_id": "player"}
        n["monster_relationships"] = {"leader_id": leader["id"]}
        s.world_state["monster_communication"] = {n["id"]: {leader["id"]: {
            "verified": True, "kind": "language", "language": "Common"}}}
        view = perception.snapshot(s, n["id"], ai.state(s, n["id"]))
        self.assertEqual(perception.communicate(s, n["id"], leader["id"], view), "player")
        s.character["hidden"] = True
        self.assertIsNone(perception.communicate(s, n["id"], leader["id"],
                                               perception.snapshot(s, n["id"], ai.state(s, n["id"]))))

    def test_nonshared_language_blocks_coordination(self):
        s, n = fixture()
        leader = add_creature(s, n, "ally", languages=["Draconic"])
        leader["monster_orders"] = {"target_id": "player"}
        s.world_state["monster_communication"] = {n["id"]: {leader["id"]: {
            "verified": True, "kind": "language", "language": "Common"}}}
        self.assertIsNone(perception.communicate(s, n["id"], leader["id"],
                                               perception.snapshot(s, n["id"], ai.state(s, n["id"]))))

    def test_controlled_variation_never_selects_poor_option(self):
        memory = {"recent": []}
        s, _ = fixture()
        choices = [{"capability_id": "a", "target_ids": ["a"], "score": 90},
                   {"capability_id": "b", "target_ids": ["b"], "score": 88},
                   {"capability_id": "flee", "target_ids": [], "score": 20}]
        seen = set()
        for _ in range(30):
            selected, audit = ai.choose(s, choices, memory)
            seen.add(selected["capability_id"])
            self.assertTrue(audit)
        self.assertEqual(seen, {"a", "b"})

    def test_obviously_best_action_can_repeat(self):
        s, n = fixture()
        activate(s, n)
        result = run(s, n)
        s.advance_combat_turn()
        s.advance_combat_turn()
        next_result = run(s, n)
        self.assertEqual(next_result["decisions"][0]["capability_id"], result["decisions"][0]["capability_id"])

    def test_no_hidden_power_scaling(self):
        s, n = fixture()
        original = copy.deepcopy(n["monster_stat_block"])
        hp_ac = (n["max_hp"], n["armor_class"])
        activate(s, n)
        run(s, n)
        self.assertEqual(n["monster_stat_block"], original)
        self.assertEqual((n["max_hp"], n["armor_class"]), hp_ac)

    def test_dodge_owner_modifier_and_expiration(self):
        s, n = fixture([])
        activate(s, n)
        run(s, n)
        self.assertTrue(ae.ensure(s)[n["id"]]["dodging"])
        s.advance_combat_turn()
        s.world_state["attack_environment"]["pairs"]["player|" + n["id"]] = {
            "distance_ft": 5, "target_sees_attacker": True}
        context = attack.prepare(s, "player", n["id"], "Longsword")
        self.assertIn("target_dodging", context["disadvantage_sources"])
        s.advance_combat_turn()
        self.assertNotIn("dodging", ae.ensure(s)[n["id"]])

    def test_decision_metadata_has_no_scores_or_reasoning(self):
        s, n = fixture()
        activate(s, n)
        result = run(s, n)
        self.assertNotIn("score", repr(result))
        self.assertNotIn("thought", repr(result))
        self.assertNotIn("candidate", repr(result))

    def test_native_flee_disengage_moves_only_known_route_and_stays_in_combat(self):
        s, n = fixture(personality="cowardly")
        n.update(current_hp=10, conditions=["frightened"], frightened_by="player")
        s.world_state["monster_routes"] = {n["id"]: [{
            "route_id": "door_route", "known": True, "clear": True,
            "destination": "doorway", "distance_ft": 20, "start_distances": {"player": 5},
            "target_distances": {"player": 25}, "movement_intent": "RETREAT"}]}
        activate(s, n)
        result = run(s, n)
        self.assertEqual(result["decisions"][0]["decision_type"], "FLEE_DECLARED")
        self.assertEqual(n["distance_ft"], 25)
        self.assertEqual(n["position"], "doorway")
        self.assertEqual(ae.ensure(s)[n["id"]]["movement_used"], 20)
        self.assertTrue(ae.ensure(s)[n["id"]]["disengaging"])
        self.assertTrue(s.world_state["combat"]["active"])
        self.assertIn(n["id"], s.world_state["combat"]["participants"])
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        self.assertEqual(run(s, n), result)
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)
        self.assertEqual(ae.monster_routes(s, n["id"], "disengage"), [])

    def test_blocked_escape_is_not_fabricated(self):
        s, n = fixture(personality="cowardly")
        n.update(current_hp=10, conditions=["frightened"])
        s.world_state["monster_routes"] = {n["id"]: [{
            "route_id": "blocked", "known": True, "clear": False, "destination": "exit",
            "distance_ft": 20, "start_distances": {"player": 5}, "target_distances": {"player": 25},
            "movement_intent": "RETREAT"}]}
        activate(s, n)
        self.assertIn(run(s, n)["decisions"][0]["decision_type"], {"PARLEY_PROPOSED", "SURRENDER_PROPOSED"})
        self.assertEqual(n["distance_ft"], 5)

    def test_route_unknown_destination_or_over_speed_not_selected(self):
        for change in ({"known": False}, {"distance_ft": 100, "target_distances": {"player": 105}},
                       {"start_distances": {"player": 6}}, {"mode": "fly"}):
            s, n = fixture()
            route = {"route_id": "route", "known": True, "clear": True, "destination": "door",
                     "distance_ft": 20, "start_distances": {"player": 5},
                     "target_distances": {"player": 25}, "movement_intent": "RETREAT", **change}
            s.world_state["monster_routes"] = {n["id"]: [route]}
            self.assertEqual(ae.monster_routes(s, n["id"], "disengage"), [])

    def test_native_dash_closes_distance_with_correct_extra_budget(self):
        s, n = fixture()
        n["distance_ft"] = 60
        s.world_state["attack_environment"]["pairs"][n["id"] + "|player"]["distance_ft"] = 60
        s.world_state["monster_routes"] = {n["id"]: [{
            "route_id": "close", "known": True, "clear": True, "destination": "near_enemy",
            "distance_ft": 55, "start_distances": {"player": 60},
            "target_distances": {"player": 5}, "movement_intent": "CLOSE_DISTANCE"}]}
        activate(s, n)
        result = run(s, n)
        self.assertEqual(result["decisions"][0]["decision_type"], "DASH")
        self.assertEqual(ae.ensure(s)[n["id"]]["movement_used"], 55)
        self.assertEqual(ae.ensure(s)[n["id"]]["dash_count"], 1)

    def test_native_route_failure_rolls_back_movement_rng_resources(self):
        s, n = fixture(personality="cowardly")
        n.update(current_hp=10, conditions=["frightened"], frightened_by="player")
        s.world_state["monster_routes"] = {n["id"]: [{
            "route_id": "exit", "known": True, "clear": True, "destination": "door",
            "distance_ft": 20, "start_distances": {"player": 5},
            "target_distances": {"player": 25}, "movement_intent": "RETREAT"}]}
        activate(s, n)
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        def failure():
            raise RuntimeError("persistence")
        with self.assertRaises(RuntimeError):
            run(s, n, commit=failure)
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_player_explicit_reject_response_zero_calls(self):
        s, n = fixture(personality="cowardly")
        n.update(current_hp=10, conditions=["frightened"])
        activate(s, n)
        run(s, n)
        s.advance_combat_turn()
        result = s.run_player_turn("Teslim olma teklifini reddediyorum.", target_id=n["id"])
        self.assertEqual(result["model_calls"], 0)
        self.assertTrue(s.world_state["combat"]["active"])
        self.assertEqual(ai.state(s, n["id"])["proposals"][0]["status"], "rejected")

    def test_player_accept_calls_lifecycle_only_when_all_hostiles_agreed(self):
        s, n = fixture(personality="cowardly")
        n.update(current_hp=10, conditions=["frightened"])
        activate(s, n)
        run(s, n)
        s.advance_combat_turn()
        result = s.run_player_turn("Teslim olma teklifini kabul ediyorum.", target_id=n["id"])
        self.assertEqual(result["model_calls"], 0)
        self.assertFalse(s.world_state["combat"]["active"])
        self.assertEqual(s.world_state["combat"]["end_reason"], "parley_accepted")

    def test_question_never_becomes_player_acceptance(self):
        s, n = fixture(personality="cowardly")
        n.update(current_hp=10, conditions=["frightened"])
        activate(s, n)
        run(s, n)
        s.advance_combat_turn()
        before = copy.deepcopy(s.world_state)
        self.assertIsNone(ai.player_response(s, "Teslim olma teklifini kabul ediyorum mu?"))
        self.assertEqual(s.world_state, before)

    def test_dodge_dex_save_advantage_uses_existing_save_owner(self):
        s, n = fixture()
        ae.ensure(s)[n["id"]]["dodging"] = True
        with patch.object(s, "roll_d20", side_effect=[1, 20]) as roll:
            result = attack.save(s, n["id"], ["dexterity"], 12)
        self.assertEqual(roll.call_count, 2)
        self.assertEqual(result["outcome"], "SUCCESS")

    def test_zero_speed_removes_dodge_dex_save_advantage(self):
        s, n = fixture(conditions=["restrained"])
        ae.ensure(s)[n["id"]]["dodging"] = True
        with patch.object(s, "roll_d20", return_value=1) as roll:
            attack.save(s, n["id"], ["dexterity"], 12)
        self.assertEqual(roll.call_count, 1)

    def test_completed_child_replay_precedes_closed_combat_validation(self):
        s, n = fixture()
        activate(s, n)
        result = run(s, n)
        s.end_combat("explicit_end")
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        self.assertEqual(run(s, n, expected_turn_id=result["turn_id"]), result)
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_player_attack_updates_only_observers_without_feature_hook_registration(self):
        s, n = fixture()
        s.world_state["inventory"].append("Longsword")
        s.world_state["equipment"] = {"main_hand": "longsword", "off_hand": None}
        with patch.object(s, "roll_d20", return_value=20):
            attack.resolve(s, "player", n["id"], weapon_id="longsword")
        self.assertGreater(ai.state(s, n["id"])["observations"]["player"]["threat"], 0)
        self.assertFalse(hasattr(s, "_attack_hooks"))

    def test_real_failed_save_owner_applies_lr_without_reroll(self):
        lr = {"capability_id": "lr", "kind": "legendary_resistance", "action_source": "resistance",
              "uses": 1, "restore": "long_rest"}
        s, n = fixture([claw(), lr])
        with patch.object(s, "roll_d20", return_value=1) as roll:
            result = attack.save(s, n["id"], ["wisdom"], 20, effect_context={"severity": "banishment"})
        self.assertEqual(roll.call_count, 1)
        self.assertEqual(result["outcome"], "SUCCESS")
        self.assertEqual(ai.state(s, n["id"])["resources"]["lr"]["remaining"], 0)

    def test_lr_is_passive_not_an_action_while_stunned(self):
        lr = {"capability_id": "lr", "kind": "legendary_resistance", "action_source": "resistance",
              "uses": 1, "restore": "long_rest"}
        s, n = fixture([claw(), lr], conditions=["stunned"])
        with patch.object(s, "roll_d20") as roll:
            result = attack.save(s, n["id"], ["dexterity"], 20, effect_context={"severity": "lethal"})
        self.assertEqual(roll.call_count, 0)
        self.assertEqual(result["outcome"], "SUCCESS")
        self.assertTrue(result["automatic_failure"])
        self.assertFalse(ae.ensure(s)[n["id"]]["base_action_spent"])

    def test_minor_real_failed_save_preserves_lr(self):
        lr = {"capability_id": "lr", "kind": "legendary_resistance", "action_source": "resistance",
              "uses": 1, "restore": "long_rest"}
        s, n = fixture([claw(), lr])
        with patch.object(s, "roll_d20", return_value=1):
            result = attack.save(s, n["id"], ["wisdom"], 20, effect_context={"severity": "minor"})
        self.assertEqual(result["outcome"], "FAILURE")
        self.assertEqual(ai.state(s, n["id"])["resources"]["lr"]["remaining"], 1)

    def test_authoritative_legendary_damage_is_returned_by_scheduler(self):
        special = claw("legendary_claw", action_source="legendary", cost=1)
        s, n = fixture([claw(), special])
        n["monster_stat_block"]["legendary_uses"] = 1
        with patch.object(s, "roll_d20", return_value=20):
            s.advance_combat_turn()
            actions = s._resolve_enemy_turns_until_player()
        self.assertGreaterEqual(len([a for a in actions if a.get("action") == "enemy_attack"]), 2)
        self.assertNotIn("monster_interrupt_results", s.world_state)

    def test_frightened_native_route_cannot_approach_fear_or_guess_missing_source(self):
        s, n = fixture(conditions=["frightened"], frightened_by="player")
        n["distance_ft"] = 30
        s.world_state["attack_environment"]["pairs"][n["id"] + "|player"]["distance_ft"] = 30
        s.world_state["monster_routes"] = {n["id"]: [{
            "route_id": "toward_fear", "known": True, "clear": True, "destination": "close",
            "distance_ft": 25, "start_distances": {"player": 30}, "target_distances": {"player": 5}}]}
        self.assertEqual(ae.monster_routes(s, n["id"], "dash"), [])
        n.pop("frightened_by")
        s.world_state["monster_routes"][n["id"]][0]["target_distances"]["player"] = 55
        self.assertEqual(ae.monster_routes(s, n["id"], "disengage"), [])

    def test_charmed_harmful_special_cannot_target_charmer(self):
        special = {"capability_id": "special", "kind": "special", "action_source": "action", "powerful": True}
        s, n = fixture([claw(), special], conditions=["charmed"], charmed_by="player")
        capabilities.register_executor(s, "special",
            legal=lambda *_: [{"target_ids": ["player"]}],
            resolve=lambda *_: {"status": "resolved"})
        activate(s, n)
        result = run(s, n)
        self.assertNotIn("special", [d.get("capability_id") for d in result["decisions"]])


def condition_test(condition):
    def test(self):
        s, n = fixture()
        n["conditions"] = [condition]
        activate(s, n)
        before = s.character["current_hp"]
        result = run(s, n)
        self.assertEqual(result["decision_type"], "NO_ACTION")
        self.assertEqual(s.character["current_hp"], before)
        self.assertEqual(result["outcomes"], [])
    return test


for _condition in ("incapacitated", "paralyzed", "petrified", "stunned", "unconscious"):
    setattr(MonsterTests, "test_condition_no_action_" + _condition, condition_test(_condition))


def invalid_capability_test(change):
    def test(self):
        s, n = fixture()
        change(n["monster_stat_block"])
        self.assert_rejected_unchanged(s, lambda: ai.run_turn(s, n["id"]))
    return test


class MonsterApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = lifecycle_tests.CombatLifecycleApiTests.asyncSetUp
    asyncTearDown = lifecycle_tests.CombatLifecycleApiTests.asyncTearDown
    request = lifecycle_tests.CombatLifecycleApiTests.request
    post = lifecycle_tests.CombatLifecycleApiTests.post

    async def test_native_decision_http_receipt_replay_no_extra_rng_or_damage(self):
        record = self.manager.get(self.sid)
        s, n = fixture(session=record.game_session)
        command = self.request(s, n, message="Hamle.", target_id=None,
                               combat_action={"steps": [{"kind": "end_turn"}]})
        first = await self.post(command)
        self.assertEqual(first.status_code, 200, first.text)
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate(), record.combat_history))
        retry = await self.post(command)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json(), first.json())
        self.assertEqual((s.world_state, s.character, s.rng.getstate(), record.combat_history), before)

    async def test_unknown_perception_http_native_dodge_not_fabricated_attack(self):
        s, n = fixture(session=self.manager.get(self.sid).game_session)
        s.world_state["monster_perception"] = {}
        s.world_state["attack_environment"]["pairs"][n["id"] + "|player"].pop("attacker_sees_target")
        command = self.request(s, n, message="Hamle.", target_id=None,
                               combat_action={"steps": [{"kind": "end_turn"}]})
        response = await self.post(command)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("monster_dodge", response.text)
        self.assertEqual(s.character["current_hp"], 1000)

    async def test_explicit_player_acceptance_uses_http_and_lifecycle(self):
        s, n = fixture(session=self.manager.get(self.sid).game_session, personality="cowardly")
        n.update(current_hp=10, conditions=["frightened"])
        activate(s, n)
        run(s, n)
        s.advance_combat_turn()
        command = self.request(s, n, message="Teslim olma teklifini kabul ediyorum.")
        response = await self.post(command)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(s.world_state["combat"]["active"])
        self.assertEqual(s.world_state["combat"]["end_reason"], "parley_accepted")


for _name, _change in {
    "missing_source": lambda b: b.pop("source"),
    "invalid_kind": lambda b: b["capabilities"][0].update(kind="invented"),
    "invalid_source": lambda b: b["capabilities"][0].update(action_source="extra_turn"),
    "duplicate_id": lambda b: b["capabilities"].append(copy.deepcopy(b["capabilities"][0])),
    "invalid_recharge": lambda b: b["capabilities"][0].update(recharge=[7, 8]),
    "unlimited_daily": lambda b: b["capabilities"][0].update(uses=-1, restore="long_rest"),
    "missing_rest_rule": lambda b: b["capabilities"][0].update(uses=1),
    "missing_multi_reference": lambda b: b["capabilities"].append(
        {"capability_id": "multi", "kind": "multiattack", "action_source": "action", "attack_slots": [["invented"]]}),
}.items():
    setattr(MonsterTests, "test_invalid_capability_" + _name, invalid_capability_test(_change))