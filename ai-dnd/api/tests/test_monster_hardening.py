"""Four reviewed mechanics bugs; fixture inputs, real Python owners, no Qwen."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import game
import action_economy as ae
import monster_combat as ai
import monster_capabilities as capabilities
import weapon_attack as attacks
from combat_lifecycle import CombatRequestError
from api.tests import test_monster_combat as fixtures


def snapshot(session):
    return copy.deepcopy((session.world_state, session.character, session.rng.getstate(), session.messages))


def restart(session, npc):
    session.end_combat("hardening_test")
    with patch("game.roll_d20", return_value=10):
        session.start_combat(npc)


class LimitedResourceTests(unittest.TestCase):
    def test_restart_preserves_exhaustion_until_correct_rest(self):
        for restore in ("long_rest", "short_rest", "never"):
            with self.subTest(restore=restore):
                s, n = fixtures.fixture([fixtures.claw(uses=1, restore=restore)])
                fixtures.activate(s, n)
                fixtures.run(s, n)
                restart(s, n)
                memory = ai.state(s, n["id"])
                ai.initialize_resources(s, n["id"], memory, capabilities.capabilities(s, n["id"]))
                self.assertEqual(memory["resources"]["claw"]["remaining"], 0)
                ai.restore_resources(s, n["id"], "short_rest")
                self.assertEqual(memory["resources"]["claw"]["remaining"], int(restore == "short_rest"))
                ai.restore_resources(s, n["id"], "long_rest")
                self.assertEqual(memory["resources"]["claw"]["remaining"], int(restore != "never"))

    def test_id_change_preserves_other_actors_without_rng_or_receipts(self):
        s, n = fixtures.fixture([fixtures.claw(uses=1, restore="long_rest")])
        other = fixtures.add_creature(s, n)
        other["monster_stat_block"] = copy.deepcopy(n["monster_stat_block"])
        for actor in (n["id"], other["id"]):
            memory = ai.state(s, actor)
            ai.initialize_resources(s, actor, memory, capabilities.capabilities(s, actor))
            memory["resources"]["claw"]["remaining"] = 0
            memory["last_turn_result"] = {"old": True}
        rng = s.rng.getstate()
        s.world_state["combat"]["combat_id"] = "another-authoritative-encounter"
        for actor in (other["id"], n["id"]):
            memory = ai.state(s, actor)
            self.assertEqual(memory["resources"]["claw"]["remaining"], 0)
            self.assertIsNone(memory["last_turn_result"])
        self.assertEqual(s.rng.getstate(), rng)
        self.assertEqual(set(s.world_state["monster_combat"]), {"combat_id", "actors"})

    def test_save_resume_between_encounters_preserves_exhaustion(self):
        s, n = fixtures.fixture([fixtures.claw(uses=1, restore="long_rest")])
        fixtures.activate(s, n)
        result = fixtures.run(s, n)
        s.end_combat("hardening_test")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "campaign.json"
            s.save_game(path)
            restored = game.GameSession(seed=456)
            restored.load_game(path)
        before = snapshot(restored)
        self.assertEqual(ai.run_turn(restored, n["id"], expected_turn_id=result["turn_id"]), result)
        self.assertEqual(snapshot(restored), before)
        with patch("game.roll_d20", return_value=10):
            restored.start_combat(attacks.actor_data(restored, n["id"]))
        self.assertEqual(ai.state(restored, n["id"])["resources"]["claw"]["remaining"], 0)
        ai.restore_resources(restored, n["id"], "long_rest")
        self.assertEqual(ai.state(restored, n["id"])["resources"]["claw"]["remaining"], 1)

    def test_encounter_budgets_and_transient_memory_still_reset(self):
        s, n = fixtures.fixture([fixtures.claw(), fixtures.claw("legendary", "legendary")])
        n["monster_stat_block"]["legendary_uses"] = 2
        memory = ai.state(s, n["id"])
        ai.initialize_resources(s, n["id"], memory, capabilities.capabilities(s, n["id"]))
        memory.update(legendary_remaining=0, observations={"player": {"threat": 8}})
        restart(s, n)
        memory = ai.state(s, n["id"])
        ai.initialize_resources(s, n["id"], memory, capabilities.capabilities(s, n["id"]))
        self.assertEqual(memory["legendary_remaining"], 2)
        self.assertEqual(memory["observations"], {})

    def test_actor_removal_rejoin_and_new_session_do_not_refill(self):
        s, n = fixtures.fixture([fixtures.claw(uses=1, restore="long_rest")])
        fixtures.activate(s, n)
        fixtures.run(s, n)
        # Initiative membership is not the canonical actor's recovery owner.
        s.world_state["combat"]["participants"].remove(n["id"])
        self.assertEqual(ai.state(s, n["id"])["resources"]["claw"]["remaining"], 0)
        s.world_state["combat"]["participants"].append(n["id"])
        self.assertEqual(ai.state(s, n["id"])["resources"]["claw"]["remaining"], 0)
        other, creature = fixtures.fixture([fixtures.claw(uses=1, restore="long_rest")])
        fixtures.activate(other, creature)
        self.assertEqual(ai.state(other, creature["id"])["resources"]["claw"]["remaining"], 1)


class MultiattackResourceTests(unittest.TestCase):
    def setup_multi(self, attacks, slots, **multi_fields):
        multi = {"capability_id": "multi", "kind": "multiattack", "action_source": "action",
                 "attack_slots": slots, **multi_fields}
        s, n = fixtures.fixture([*attacks, multi])
        fixtures.activate(s, n)
        return s, n

    def test_two_available_components_spend_each_use_once_and_replay(self):
        s, n = self.setup_multi([fixtures.claw(uses=2, restore="long_rest")],
                               [["claw"], ["claw"]], uses=1, restore="long_rest")
        result = fixtures.run(s, n)
        self.assertEqual(result["decisions"][0]["capability_id"], "multi")
        self.assertEqual(len(result["outcomes"]), 2)
        resources = ai.state(s, n["id"])["resources"]
        self.assertEqual(resources["claw"]["remaining"], 0)
        self.assertEqual(resources["multi"]["remaining"], 0)
        before = snapshot(s)
        self.assertEqual(fixtures.run(s, n), result)
        self.assertEqual(snapshot(s), before)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "campaign.json"
            s.save_game(path)
            restored = game.GameSession(seed=789)
            restored.load_game(path)
        before = snapshot(restored)
        self.assertEqual(ai.run_turn(restored, n["id"], expected_turn_id=result["turn_id"]), result)
        self.assertEqual(snapshot(restored), before)

    def test_exhausted_component_never_executes(self):
        s, n = self.setup_multi([fixtures.claw(uses=1, restore="long_rest")], [["claw"], ["claw"]])
        memory = ai.state(s, n["id"])
        memory["resources"]["claw"]["remaining"] = 0
        result = fixtures.run(s, n)
        self.assertFalse(any(o["action"] == "enemy_attack" for o in result["outcomes"]))
        self.assertEqual(memory["resources"]["claw"]["remaining"], 0)

    def test_one_use_cannot_pay_for_two_identical_slots(self):
        s, n = self.setup_multi([fixtures.claw(uses=1, restore="long_rest")], [["claw"], ["claw"]])
        result = fixtures.run(s, n)
        # Exact slots forbid truncation, but the independently legal attack works.
        self.assertEqual(result["decisions"][0]["capability_id"], "claw")
        self.assertEqual(len(result["outcomes"]), 1)
        self.assertEqual(ai.state(s, n["id"])["resources"]["claw"]["remaining"], 0)

    def test_available_standalone_component_survives_exhausted_exact_slot(self):
        s, n = self.setup_multi([fixtures.claw(), fixtures.claw("bite", uses=1, restore="long_rest")],
                               [["claw"], ["bite"]])
        ai.state(s, n["id"])["resources"]["bite"]["remaining"] = 0
        result = fixtures.run(s, n)
        self.assertEqual(result["decisions"][0]["attack_sequence"], ["claw"])
        self.assertEqual(len(result["outcomes"]), 1)

    def test_permitted_alternative_combination_remains_available(self):
        s, n = self.setup_multi([fixtures.claw(), fixtures.claw("bite", uses=1, restore="long_rest")],
                               [["claw", "bite"], ["claw", "bite"]],
                               allowed_sequences=[["claw", "claw"], ["bite", "claw"]])
        ai.state(s, n["id"])["resources"]["bite"]["remaining"] = 0
        self.assertEqual(fixtures.run(s, n)["decisions"][0]["attack_sequence"], ["claw", "claw"])

    def test_recharge_components_are_checked_and_spent_per_execution(self):
        for slots in ([["claw"], ["claw"]], [["claw"], ["bite"]]):
            with self.subTest(slots=slots):
                s, n = self.setup_multi([fixtures.claw(recharge=[5, 6]), fixtures.claw("bite")], slots)
                result = fixtures.run(s, n)
                sequence = result["decisions"][0]["attack_sequence"]
                self.assertLessEqual(sequence.count("claw"), 1)
                self.assertFalse(ai.state(s, n["id"])["resources"]["claw"]["available"])
        s, n = self.setup_multi([fixtures.claw(recharge=[5, 6]), fixtures.claw("bite")],
                               [["claw"], ["bite"]])
        ai.state(s, n["id"])["resources"]["claw"]["available"] = False
        self.assertEqual(fixtures.run(s, n)["decisions"][0]["attack_sequence"], ["bite"])

    def test_component_condition_requirements_apply_inside_multiattack(self):
        s, n = self.setup_multi([fixtures.claw(requires_conditions=["invisible"]), fixtures.claw("bite")],
                               [["claw"], ["bite"]])
        self.assertEqual(fixtures.run(s, n)["decisions"][0]["attack_sequence"], ["bite"])

    def test_candidate_checks_do_not_mutate_resources_or_rng(self):
        s, n = self.setup_multi([fixtures.claw(uses=1, restore="long_rest")], [["claw"], ["claw"]])
        memory = ai.state(s, n["id"])
        view = fixtures.perception.snapshot(s, n["id"], memory)
        before = copy.deepcopy((memory["resources"], s.rng.getstate()))
        ai.candidates(s, n["id"], memory, capabilities.capabilities(s, n["id"]), view)
        self.assertEqual((memory["resources"], s.rng.getstate()), before)

    def test_component_failure_rolls_back_damage_resources_rng_and_messages(self):
        s, n = self.setup_multi([fixtures.claw(uses=2, restore="long_rest")], [["claw"], ["claw"]])
        before = snapshot(s)
        resolve = attacks.resolve
        calls = []
        def fail_second(*args, **kwargs):
            calls.append(True)
            if len(calls) == 2:
                raise RuntimeError("component owner failure")
            return resolve(*args, **kwargs)
        with patch.object(attacks, "resolve", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "component owner failure"):
                fixtures.run(s, n)
        self.assertEqual(snapshot(s), before)


class RouteEvidenceTests(unittest.TestCase):
    def setup_route(self, enemy_distance=5):
        s, n = fixtures.fixture()
        other = fixtures.add_creature(s, n)
        fixtures.activate(s, n)
        ae.ensure(s)["player"]["reaction_spent"] = True
        s.world_state["attack_environment"]["pairs"][n["id"] + "|" + other["id"]]["distance_ft"] = enemy_distance
        route = {"route_id": "route", "known": True, "clear": True, "destination": "door",
                 "distance_ft": 20, "start_distances": {"player": 5},
                 "target_distances": {"player": 25}, "movement_intent": "RETREAT"}
        s.world_state["monster_routes"] = {n["id"]: [route]}
        return s, n, other, route

    def test_omitted_hostile_rejects_route_without_fabrication_or_mutation(self):
        s, n, other, _ = self.setup_route()
        before = snapshot(s)
        self.assertEqual(ae.monster_routes(s, n["id"], "dash"), [])
        with self.assertRaises(CombatRequestError):
            ae.resolve_monster_route(s, n["id"], "route", "dash")
        self.assertEqual(snapshot(s), before)
        self.assertEqual(attacks.pair(s, n["id"], other["id"])["distance_ft"], 5)
        self.assertFalse(ae.ensure(s)[other["id"]]["reaction_spent"])

    def test_unknown_hostile_distance_is_not_proof_of_safety(self):
        s, n, other, route = self.setup_route()
        del s.world_state["attack_environment"]["pairs"][n["id"] + "|" + other["id"]]
        route["start_distances"][other["id"]] = 5
        route["target_distances"][other["id"]] = 25
        before = snapshot(s)
        self.assertEqual(ae.monster_routes(s, n["id"], "dash"), [])
        self.assertEqual(snapshot(s), before)

    def test_complete_route_checks_oa_and_disengage_normally(self):
        s, n, other, route = self.setup_route()
        route["start_distances"][other["id"]] = 5
        route["target_distances"][other["id"]] = 25
        self.assertEqual(ae.monster_routes(s, n["id"], "dash"), [])
        self.assertEqual(len(ae.monster_routes(s, n["id"], "disengage")), 1)
        ae.resolve_monster_route(s, n["id"], "route", "disengage")
        self.assertEqual(attacks.pair(s, n["id"], other["id"])["distance_ft"], 25)
        self.assertFalse(ae.ensure(s)[other["id"]]["reaction_spent"])
        self.assertTrue(s.world_state["combat"]["active"])

    def test_complete_out_of_reach_hostile_route_remains_legal(self):
        s, n, other, route = self.setup_route(enemy_distance=30)
        route["start_distances"][other["id"]] = 30
        route["target_distances"][other["id"]] = 50
        self.assertEqual(len(ae.monster_routes(s, n["id"], "dash")), 1)
        ae.resolve_monster_route(s, n["id"], "route", "dash")
        self.assertEqual(ae.ensure(s)[n["id"]]["movement_used"], 20)
        self.assertEqual(attacks.pair(s, n["id"], other["id"])["distance_ft"], 50)
        self.assertFalse(ae.ensure(s)[other["id"]]["reaction_spent"])

    def test_complete_route_with_spent_reaction_remains_legal(self):
        s, n, other, route = self.setup_route()
        route["start_distances"][other["id"]] = 5
        route["target_distances"][other["id"]] = 25
        ae.ensure(s)[other["id"]]["reaction_spent"] = True
        self.assertEqual(len(ae.monster_routes(s, n["id"], "dash")), 1)


class FrightenedModifierTests(unittest.TestCase):
    def prepare(self, s, n, target="player"):
        with ae.executing(s, "monster_capability", n["id"]):
            return attacks.prepare(s, n["id"], target, profile=fixtures.claw()["profile"])

    def test_canonical_visible_fear_source_applies_once_without_mutation(self):
        for conditions in (["frightened"], {"frightened": True}):
            for legacy in (False, True):
                with self.subTest(conditions=conditions, legacy=legacy):
                    s, n = fixtures.fixture(conditions=conditions, frightened_by="player")
                    if legacy:
                        n["frightened_until_player_turn"] = 999
                    before = snapshot(s)
                    result = self.prepare(s, n)
                    self.assertEqual(result["disadvantage_sources"].count("frightened"), 1)
                    self.assertEqual(snapshot(s), before)

    def test_unrelated_attack_target_has_no_condition_only_disadvantage(self):
        s, n = fixtures.fixture(conditions=["frightened"], frightened_by="player")
        other = fixtures.add_creature(s, n)
        self.assertNotIn("frightened", self.prepare(s, n, other["id"])["disadvantage_sources"])

    def test_missing_invisible_or_unknown_source_does_not_fabricate_sight(self):
        for change in ("no_source", "no_visibility", "not_visible", "blinded", "hidden", "invisible"):
            with self.subTest(change=change):
                s, n = fixtures.fixture(conditions=["frightened"], frightened_by="player")
                if change == "no_source":
                    n.pop("frightened_by")
                elif change == "no_visibility":
                    s.world_state["attack_environment"]["pairs"][n["id"] + "|player"].pop("attacker_sees_target")
                elif change == "not_visible":
                    s.world_state["attack_environment"]["pairs"][n["id"] + "|player"]["attacker_sees_target"] = False
                elif change == "blinded":
                    n["conditions"].append("blinded")
                elif change == "hidden":
                    s.character["hidden"] = True
                else:
                    s.character["conditions"] = ["invisible"]
                self.assertNotIn("frightened", self.prepare(s, n)["disadvantage_sources"])

    def test_canonical_facts_override_stale_legacy_field(self):
        s, n = fixtures.fixture(conditions=["frightened"], frightened_until_player_turn=999)
        self.assertNotIn("frightened", self.prepare(s, n)["disadvantage_sources"])

    def test_legacy_effect_active_and_expired_compatibility(self):
        s, n = fixtures.fixture(frightened_until_player_turn=2)
        self.assertIn("frightened", self.prepare(s, n)["disadvantage_sources"])
        s.character.setdefault("species_trait_state", {})["player_turn_counter"] = 2
        self.assertNotIn("frightened", self.prepare(s, n)["disadvantage_sources"])

    def test_preexisting_disadvantage_source_is_not_duplicated(self):
        s, n = fixtures.fixture(conditions=["frightened"], frightened_by="player",
                               attack_rules={"disadvantage_sources": ["frightened"]})
        self.assertEqual(self.prepare(s, n)["disadvantage_sources"].count("frightened"), 1)

    def test_existing_resolver_cancels_advantage_with_fear_disadvantage(self):
        s, n = fixtures.fixture(conditions=["frightened"], frightened_by="player",
                               attack_rules={"advantage_sources": ["owner_verified_advantage"]})
        fixtures.activate(s, n)
        with patch.object(s, "roll_d20", return_value=12) as roll:
            with ae.executing(s, "monster_capability", n["id"]):
                result = attacks.resolve(s, n["id"], "player", profile=fixtures.claw()["profile"])
        self.assertEqual(roll.call_count, 1)
        self.assertIn("frightened", result["disadvantage_sources"])
        self.assertIn("owner_verified_advantage", result["advantage_sources"])