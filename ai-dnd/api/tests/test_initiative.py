"""Initiative Lock: canonical dice, boundaries, membership and HTTP receipts."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import game
import initiative as init
import action_economy as ae
from api.tests.test_campaign_time import scene
from api.tests.test_combat_lifecycle import ready, CombatLifecycleApiTests
from api.persistence.campaign_store import CampaignStore
from api.persistence.campaign_models import CampaignStorageError
from api.session_manager import SessionManager


def actors(configs=None, player=None):
    s = scene()
    s.world_state["npcs"] = []
    s.character.update(current_hp=100, max_hp=100, dexterity_mod=2)
    s.character.update(player or {})
    ns = []
    for i, config in enumerate(configs or [{}]):
        n = s.create_npc_from_ai({"name": f"Rakip {i}", "role": "Guard", "location": "tavern"})
        n.update(id=f"npc-{i}", current_hp=100, max_hp=100, armor_class=20, hostile=True, initiative_modifier=0,
                 distance_ft=5, attack_damage_type="bludgeoning")
        n.update(config)
        ns.append(n)
    return s, ns


def battle(configs=None, player=None, rolls=None):
    s, ns = actors(configs, player)
    with patch("game.roll_d20", side_effect=rolls or [20] + [1] * len(ns)):
        s.start_combat(ns[0])
    return s, ns


def newcomer(s, identity="new", **config):
    n = s.create_npc_from_ai({"name": identity, "role": "Guard", "location": "tavern"})
    n.update(id=identity, current_hp=100, max_hp=100, armor_class=20, initiative_modifier=0,
             distance_ft=5, attack_damage_type="bludgeoning")
    n.update(config)
    return n


class InitiativeTests(unittest.TestCase):
    def test_start_is_existing_lifecycle_only(self):
        s, ns = actors()
        rng = s.rng.getstate()
        with self.assertRaises(ValueError):
            init.initialize(s, ["player", ns[0]["id"]])
        with self.assertRaises(ValueError):
            s.join_combat_participants([ns[0]["id"]])
        self.assertFalse(s.world_state["combat"]["active"])
        self.assertEqual(s.rng.getstate(), rng)

    def test_start_rolls_exactly_once_per_actor(self):
        s, ns = actors([{}, {}])
        with patch("game.roll_d20", side_effect=[10, 8, 6]) as roller:
            result = s.start_combat(ns[0])
        self.assertTrue(result["combat_started"])
        self.assertEqual(roller.call_count, 3)
        self.assertEqual(len(s.world_state["combat"]["initiative_results"]), 3)

    def test_second_start_preserves_rng_and_order(self):
        s, ns = battle()
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        with self.assertRaises(ValueError):
            s.start_combat(ns[0])
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_rounds_do_not_reroll(self):
        s, _ = battle()
        original = copy.deepcopy(s.world_state["combat"]["initiative_results"])
        with patch("game.roll_d20", side_effect=AssertionError("reroll")):
            for _ in range(6):
                s.advance_combat_turn()
        self.assertEqual(s.world_state["combat"]["initiative_results"], original)

    def test_attack_movement_and_dash_do_not_reroll(self):
        s, ns = battle()
        original = copy.deepcopy(s.world_state["combat"]["initiative_results"])
        with patch("game.roll_initiative", side_effect=AssertionError("reroll")), patch("game.roll_initiative_player", side_effect=AssertionError("reroll")), patch("game.roll_attack", return_value=1):
            s.run_player_turn("Hamle.", combat_action={"steps": [
                {"kind": "move", "distance_ft": 5}, {"kind": "attack", "target_id": ns[0]["id"]}]})
        self.assertEqual(s.world_state["combat"]["initiative_results"], original)

    def test_player_dexterity_and_breakdown(self):
        s, _ = battle(player={"dexterity_mod": 3}, rolls=[14, 1])
        r = s.world_state["combat"]["initiative_results"]["player"]
        self.assertEqual((r["selected_roll"], r["base_modifier"], r["final_total"]), (14, 3, 17))

    def test_monster_modifier_is_not_replaced_by_dexterity(self):
        s, ns = battle([{"initiative_modifier": 7, "dexterity_mod": -1}], rolls=[1, 14])
        r = s.world_state["combat"]["initiative_results"][ns[0]["id"]]
        self.assertEqual((r["base_modifier"], r["final_total"]), (7, 21))

    def test_monster_score_is_retained_but_not_used_as_roll(self):
        s, ns = battle([{"initiative_score": 19}], rolls=[20, 3])
        r = s.world_state["combat"]["initiative_results"][ns[0]["id"]]
        self.assertEqual((r["stat_block_score"], r["final_total"], r["mode"]), (19, 3, "rolled"))

    def test_invalid_monster_modifier_fails_without_rng(self):
        s, ns = actors([{"initiative_modifier": "7"}])
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        with self.assertRaises(ValueError):
            s.start_combat(ns[0])
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_sourced_feature_modifiers(self):
        s, _ = battle(player={"initiative_rules": {"modifiers": [
            {"source": "feature-proficiency", "value": 3}, {"source": "feature-wisdom", "value": 2}]}}, rolls=[14, 1])
        r = s.world_state["combat"]["initiative_results"]["player"]
        self.assertEqual(r["final_total"], 21)
        self.assertEqual(len(r["additional_modifiers"]), 2)

    def test_advantage_uses_common_d20_resolver(self):
        s, _ = battle(player={"initiative_rules": {"advantage_sources": ["feature"]}}, rolls=[3, 17, 1])
        r = s.world_state["combat"]["initiative_results"]["player"]
        self.assertEqual((r["raw_rolls"], r["selected_roll"]), ([3, 17], 17))

    def test_disadvantage_uses_common_d20_resolver(self):
        s, _ = battle(player={"initiative_rules": {"disadvantage_sources": ["feature"]}}, rolls=[3, 17, 1])
        self.assertEqual(s.world_state["combat"]["initiative_results"]["player"]["selected_roll"], 3)

    def test_advantage_disadvantage_cancel_with_one_die(self):
        s, ns = actors(player={"initiative_rules": {"advantage_sources": ["a"], "disadvantage_sources": ["d"]}})
        with patch("game.roll_d20", side_effect=[9, 1]) as roller:
            s.start_combat(ns[0])
        self.assertEqual(roller.call_count, 2)
        self.assertTrue(s.world_state["combat"]["initiative_results"]["player"]["advantage_cancelled"])

    def test_surprise_2024_is_disadvantage(self):
        s, _ = battle(player={"surprised_at_combat_start": True}, rolls=[20, 1, 5])
        r = s.world_state["combat"]["initiative_results"]["player"]
        self.assertEqual(r["selected_roll"], 1)
        self.assertIn("surprise_2024", r["disadvantage_sources"])

    def test_surprise_does_not_skip_first_turn(self):
        s, ns = battle([{"surprised_at_combat_start": True}], rolls=[20, 20, 1])
        s.advance_combat_turn()
        self.assertEqual(s.world_state["combat"]["current_actor_id"], ns[0]["id"])
        self.assertTrue(ae.projection(s)["actors"][ns[0]["id"]]["action_available"])

    def test_incapacitated_at_roll_has_disadvantage(self):
        s, ns = battle([{"conditions": ["incapacitated"]}], rolls=[20, 18, 2])
        r = s.world_state["combat"]["initiative_results"][ns[0]["id"]]
        self.assertEqual(r["selected_roll"], 2)
        self.assertIn("incapacitated_2024", r["disadvantage_sources"])

    def test_condition_change_does_not_change_rolled_result(self):
        s, ns = battle()
        before = copy.deepcopy(s.world_state["combat"]["initiative_results"])
        ns[0]["conditions"] = ["incapacitated"]
        s.character["dexterity_mod"] = 10
        s.ensure_combat_state()
        self.assertEqual(s.world_state["combat"]["initiative_results"], before)

    def test_explicit_identical_group_uses_one_roll(self):
        s, ns = actors([{"initiative_group_id": "team", "stat_block_id": "goblin"}] * 2)
        with patch("game.roll_d20", side_effect=[10, 6]) as roller:
            s.start_combat(ns[0])
        self.assertEqual(roller.call_count, 2)
        rs = s.world_state["combat"]["initiative_results"]
        self.assertEqual(rs[ns[0]["id"]]["raw_rolls"], rs[ns[1]["id"]]["raw_rolls"])

    def test_same_statblock_does_not_imply_group(self):
        s, ns = actors([{"stat_block_id": "goblin"}] * 2)
        with patch("game.roll_d20", side_effect=[20, 8, 2]) as roller:
            s.start_combat(ns[0])
        self.assertEqual(roller.call_count, 3)
        self.assertEqual(s.world_state["combat"]["initiative_groups"], {})

    def test_mismatched_group_is_rejected_atomically(self):
        s, ns = actors([{"initiative_group_id": "g", "stat_block_id": "goblin"},
                        {"initiative_group_id": "g", "stat_block_id": "orc"}])
        before = copy.deepcopy((s.world_state, s.rng.getstate()))
        with patch("game.roll_d20", side_effect=AssertionError("must validate first")), self.assertRaises(ValueError):
            s.start_combat(ns[0])
        self.assertEqual((s.world_state, s.rng.getstate()), before)

    def test_high_to_low_order(self):
        s, ns = battle([{}, {}], rolls=[5, 18, 12])
        self.assertEqual(s.world_state["combat"]["initiative_order"], [ns[0]["id"], ns[1]["id"], "player"])

    def test_mixed_tie_player_priority(self):
        s, ns = battle(rolls=[8, 10])
        self.assertEqual(s.world_state["combat"]["initiative_order"], ["player", ns[0]["id"]])

    def test_other_ties_use_stable_actor_id(self):
        s, ns = battle([{}, {}], rolls=[20, 9, 9])
        self.assertEqual(s.world_state["combat"]["initiative_order"], ["player", ns[0]["id"], ns[1]["id"]])

    def test_tie_sort_does_not_consume_rng(self):
        s, ns = actors()
        before = s.rng.getstate()
        with patch("game.roll_d20", side_effect=[8, 10]) as roller:
            s.start_combat(ns[0])
        self.assertEqual(roller.call_count, 2)
        self.assertEqual(s.rng.getstate(), before)

    def test_order_stays_stable_between_rounds(self):
        s, ns = battle([{}, {}], rolls=[20, 8, 5])
        order = list(s.world_state["combat"]["initiative_order"])
        ns[1]["initiative_modifier"] = 100
        for _ in range(6):
            s.advance_combat_turn()
        self.assertEqual(s.world_state["combat"]["initiative_order"], order)

    def test_current_actor_advances(self):
        s, ns = battle([{}, {}])
        self.assertEqual(s.advance_combat_turn()[1], ns[0]["id"])
        self.assertEqual(s.advance_combat_turn()[1], ns[1]["id"])

    def test_last_actor_wraps_once_and_clock_is_existing_rule(self):
        s, _ = battle()
        s.advance_combat_turn()
        self.assertTrue(s.advance_combat_turn()[2])
        self.assertEqual(s.world_state["combat"]["round"], 2)
        self.assertEqual(s.world_state["campaign_time"]["elapsed_seconds"], 6)

    def test_reaction_reset_is_owned_by_action_economy(self):
        s, ns = battle()
        ae.ensure(s)["player"]["reaction_spent"] = True
        with patch("action_economy.begin_turn", wraps=ae.begin_turn) as boundary:
            s.advance_combat_turn()
            self.assertTrue(ae.ensure(s)["player"]["reaction_spent"])
            s.advance_combat_turn()
        self.assertEqual([c.args[1] for c in boundary.call_args_list], [ns[0]["id"], "player"])
        self.assertFalse(ae.ensure(s)["player"]["reaction_spent"])

    def test_zero_hp_retains_slot(self):
        s, _ = battle()
        s.character["current_hp"] = 0
        s.world_state["player_combat_status"] = "unconscious"
        s.ensure_combat_state()
        self.assertIn("player", s.world_state["combat"]["initiative_order"])

    def test_unconscious_retains_slot(self):
        s, _ = battle()
        s.character["current_hp"] = 0
        s.world_state["player_combat_status"] = "unconscious"
        s.advance_combat_turn()
        self.assertEqual(s.advance_combat_turn()[1], "player")

    def test_stable_retains_slot(self):
        s, _ = battle()
        s.character["current_hp"] = 0
        s.world_state["player_combat_status"] = "unconscious"
        s.ensure_death_state()["stable"] = True
        s.advance_combat_turn()
        self.assertEqual(s.advance_combat_turn()[1], "player")

    def test_current_stable_slot_does_not_run_another_enemy(self):
        s, _ = battle()
        s.character["current_hp"] = 0
        s.world_state["player_combat_status"] = "unconscious"
        s.ensure_death_state()["stable"] = True
        with patch("game.resolve_enemy_attack", side_effect=AssertionError("skip")):
            s._resolve_enemy_turns_until_player()
        self.assertEqual(s.world_state["combat"]["current_actor_id"], "player")

    def test_death_save_runs_through_existing_owner(self):
        s, _ = battle()
        s.character["current_hp"] = 0
        s.world_state["player_combat_status"] = "unconscious"
        with patch("game.roll_d20", return_value=20):
            results = s._resolve_enemy_turns_until_player()
        self.assertEqual(results[0]["action"], "death_save")
        self.assertGreater(s.character["current_hp"], 0)

    def test_historical_npc_unconscious_cannot_act_but_does_not_stall(self):
        s, ns = battle([{}, {}])
        ns[0].update(current_hp=0, combat_status="unconscious")
        s.advance_combat_turn()
        with patch("game.resolve_enemy_attack", side_effect=AssertionError("skip")):
            s._resolve_enemy_turns_until_player()
        self.assertEqual(s.world_state["combat"]["current_actor_id"], "player")
        self.assertEqual(ns[0]["combat_status"], "unconscious")
        self.assertIn(ns[0]["id"], s.world_state["combat"]["initiative_order"])

    def test_dead_removal_is_safe_and_idempotent(self):
        s, ns = battle([{}, {}])
        ns[1]["combat_status"] = "dead"
        before_rng = s.rng.getstate()
        self.assertTrue(s.remove_combat_participant(ns[1]["id"]))
        self.assertFalse(s.remove_combat_participant(ns[1]["id"]))
        self.assertEqual(s.rng.getstate(), before_rng)
        self.assertEqual(s.world_state["combat"]["round"], 1)

    def test_newcomer_only_rolls_itself(self):
        s, _ = battle()
        old = copy.deepcopy(s.world_state["combat"]["initiative_results"])
        n = newcomer(s)
        with patch("game.roll_d20", return_value=7) as roller:
            s.join_combat_participants([n["id"]])
        self.assertEqual(roller.call_count, 1)
        for a, result in old.items():
            self.assertEqual(s.world_state["combat"]["initiative_results"][a], result)

    def test_join_is_idempotent(self):
        s, _ = battle()
        n = newcomer(s)
        with patch("game.roll_d20", return_value=7):
            s.join_combat_participants([n["id"]])
        before = copy.deepcopy((s.world_state, s.rng.getstate()))
        self.assertEqual(s.join_combat_participants([n["id"]]), [])
        self.assertEqual((s.world_state, s.rng.getstate()), before)

    def test_newcomer_after_current_can_act_this_round(self):
        s, _ = battle()
        n = newcomer(s)
        with patch("game.roll_d20", return_value=7):
            s.join_combat_participants([n["id"]])
        self.assertEqual(s.advance_combat_turn()[1], n["id"])
        self.assertEqual(s.world_state["combat"]["round"], 1)

    def test_newcomer_before_current_waits_until_next_round(self):
        s, ns = battle([{}, {}], rolls=[10, 8, 1])
        s._mark_combat_action_used("player")
        s.advance_combat_turn()
        before = copy.deepcopy(ae.ensure(s)[ns[0]["id"]])
        n = newcomer(s)
        with patch("game.roll_d20", return_value=20):
            s.join_combat_participants([n["id"]])
        self.assertEqual(s.world_state["combat"]["current_actor_id"], ns[0]["id"])
        self.assertEqual(ae.ensure(s)[ns[0]["id"]], before)
        self.assertIn(n["id"], s.world_state["combat"]["actions_used"])
        self.assertEqual(s.advance_combat_turn()[1], ns[1]["id"])
        self.assertEqual(s.advance_combat_turn()[1], n["id"])
        self.assertEqual(s.world_state["combat"]["round"], 2)

    def test_join_group_newcomers_use_one_new_roll(self):
        s, _ = battle()
        ns = [newcomer(s, str(i), initiative_group_id="g", stat_block_id="goblin") for i in range(2)]
        with patch("game.roll_d20", return_value=7) as roller:
            s.join_combat_participants([n["id"] for n in ns])
        self.assertEqual(roller.call_count, 1)

    def test_join_existing_group_reuses_canonical_group_result(self):
        s, _ = battle([{"initiative_group_id": "g", "stat_block_id": "goblin"}])
        n = newcomer(s, initiative_group_id="g", stat_block_id="goblin")
        with patch("game.roll_d20", side_effect=AssertionError("group reroll")):
            s.join_combat_participants([n["id"]])
        self.assertEqual(s.world_state["combat"]["initiative_results"][n["id"]]["final_total"], 1)

    def test_remove_noncurrent_preserves_current_actor_and_resources(self):
        s, ns = battle([{}, {}])
        before = copy.deepcopy(ae.ensure(s)["player"])
        s.remove_combat_participant(ns[0]["id"])
        self.assertEqual(s.world_state["combat"]["current_actor_id"], "player")
        self.assertEqual(ae.ensure(s)["player"], before)

    def test_remove_current_middle_starts_successor_without_wrap(self):
        s, ns = battle([{}, {}])
        s.advance_combat_turn()
        s.remove_combat_participant(ns[0]["id"])
        self.assertEqual(s.world_state["combat"]["current_actor_id"], ns[1]["id"])
        self.assertEqual(s.world_state["combat"]["round"], 1)
        self.assertEqual(s.world_state["campaign_time"]["elapsed_seconds"], 0)

    def test_remove_current_first_does_not_increment_round(self):
        s, ns = battle([{"initiative_modifier": 30}, {}], rolls=[10, 10, 1])
        self.assertEqual(s.world_state["combat"]["current_actor_id"], ns[0]["id"])
        s.remove_combat_participant(ns[0]["id"])
        self.assertEqual(s.world_state["combat"]["current_actor_id"], "player")
        self.assertEqual(s.world_state["combat"]["round"], 1)

    def test_remove_current_last_wraps_through_scheduler(self):
        s, ns = battle([{}, {}])
        s.advance_combat_turn()
        s.advance_combat_turn()
        s.remove_combat_participant(ns[1]["id"])
        self.assertEqual(s.world_state["combat"]["current_actor_id"], "player")
        self.assertEqual(s.world_state["combat"]["round"], 2)
        self.assertEqual(s.world_state["campaign_time"]["elapsed_seconds"], 6)

    def test_remove_final_enemy_delegates_to_combat_lifecycle(self):
        s, ns = battle()
        self.assertTrue(s.remove_combat_participant(ns[0]["id"]))
        self.assertFalse(s.world_state["combat"]["active"])
        self.assertEqual(s.world_state["combat"]["end_reason"], "participants_left")

    def test_last_enemy_leaves_unconscious_player_death_boundary_intact(self):
        s, ns = battle()
        s.character["current_hp"] = 0
        s.world_state["player_combat_status"] = "unconscious"
        s.remove_combat_participant(ns[0]["id"])
        combat = s.ensure_combat_state()
        self.assertEqual(combat["initiative_order"], ["player"])
        self.assertEqual(combat["status"], "death_resolution")
        self.assertIsNone(combat["target_id"])
        self.assertIsNotNone(s.ensure_death_state()["combat_checkpoint"])
        with patch("game.roll_d20", return_value=20):
            result = s._resolve_enemy_turns_until_player()
        self.assertEqual(result[0]["action"], "death_save")
        self.assertFalse(s.world_state["combat"]["active"])

    def test_last_current_enemy_leaves_and_delegates_round_boundary(self):
        s, ns = battle()
        s.character["current_hp"] = 0
        s.world_state["player_combat_status"] = "unconscious"
        s.advance_combat_turn()
        s.remove_combat_participant(ns[0]["id"])
        self.assertEqual(s.world_state["combat"]["current_actor_id"], "player")
        self.assertEqual(s.world_state["combat"]["round"], 2)
        self.assertEqual(s.world_state["campaign_time"]["elapsed_seconds"], 6)

    def test_last_enemy_leaves_stable_player_uses_existing_exit(self):
        s, ns = battle()
        s.character["current_hp"] = 0
        s.world_state["player_combat_status"] = "unconscious"
        s.ensure_death_state()["stable"] = True
        s.remove_combat_participant(ns[0]["id"])
        self.assertEqual(s.world_state["combat"]["end_reason"], "player_stable")

    def test_departing_ready_target_clears_only_its_opportunity(self):
        s, ns = battle([{}, {}])
        s.run_player_turn("Hazırla.", combat_action={"steps": [{
            "kind": "ready", "trigger": {"event": "actor_attacks", "actor_id": ns[0]["id"]},
            "response": {"kind": "attack", "target_id": ns[0]["id"]}}]})
        s.remove_combat_participant(ns[0]["id"])
        self.assertIsNone(ae.ensure(s)["player"]["ready"])
        self.assertIsNone(ae.ensure(s)["player"]["opportunity"])

    def test_departure_keeps_swapped_counts_and_audit(self):
        s, ns = actors([{}, {}])
        s.register_initiative_hook("AFTER_INITIATIVE_ORDER_INITIALIZED", lambda *_: [
            {"kind": "swap", "source": "feature", "actor_id": ns[0]["id"], "ally_id": ns[1]["id"], "willing": True}])
        with patch("game.roll_d20", side_effect=[20, 9, 2]):
            s.start_combat(ns[0])
        s.remove_combat_participant(ns[0]["id"])
        combat = s.ensure_combat_state()
        count = next(r["initiative"] for r in combat["participant_records"] if r["id"] == ns[1]["id"])
        self.assertEqual(count, 9)
        self.assertEqual(combat["initiative_effects"][0]["prior_effects"][0]["source"], "feature")

    def test_qwen_cannot_mutate_initiative_or_awareness(self):
        s, ns = battle()
        before = copy.deepcopy(s.world_state["combat"])
        candidate = {"combat": {"initiative_order": ["player"], "round": 99},
                     "initiative_results": {"player": {"final_total": 999}},
                     "update_npcs": [{"id": ns[0]["id"], "initiative_modifier": 999,
                                      "surprised_at_combat_start": True, "initiative_rules": {},
                                      "initiative_group_id": "invented", "combat_status": "dead"}]}
        sanitized = s.validate_world_updates(candidate)
        s.merge_world_updates(sanitized)
        self.assertEqual(s.world_state["combat"], before)
        self.assertEqual(ns[0]["initiative_modifier"], 0)
        self.assertNotIn("surprised_at_combat_start", ns[0])

    def test_unknown_world_participant_rejects_join_before_rng(self):
        s, _ = battle()
        before = copy.deepcopy((s.world_state, s.rng.getstate()))
        with patch("game.roll_d20", side_effect=AssertionError("roll")), self.assertRaises(ValueError):
            s.join_combat_participants(["invented"])
        self.assertEqual((s.world_state, s.rng.getstate()), before)

    def test_save_resume_keeps_group_order_cursor_and_rng(self):
        s, _ = battle([{"initiative_group_id": "g", "stat_block_id": "goblin"}] * 2, rolls=[20, 8])
        s.advance_combat_turn()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            s.save_game(path)
            other = scene()
            with patch("game.roll_d20", side_effect=AssertionError("reload reroll")):
                other.load_game(path)
        self.assertEqual(other.world_state["combat"], s.world_state["combat"])
        self.assertEqual(other.rng.getstate(), s.rng.getstate())

    def test_empty_order_fails_safely_without_reroll(self):
        s, _ = battle()
        s.world_state["combat"]["initiative_order"] = []
        with self.assertRaises(ValueError):
            s.advance_combat_turn()

    def test_invalid_cursor_fails_safely(self):
        s, _ = battle()
        s.world_state["combat"]["current_turn_index"] = 100
        with self.assertRaises(ValueError):
            s.advance_combat_turn()

    def test_duplicate_actor_fails_safely(self):
        s, ns = battle()
        s.world_state["combat"]["initiative_order"].append(ns[0]["id"])
        with self.assertRaises(ValueError):
            s.advance_combat_turn()

    def test_missing_world_actor_fails_safely(self):
        s, _ = battle()
        s.world_state["npcs"] = []
        with self.assertRaises(ValueError):
            s.advance_combat_turn()

    def test_corrupt_audit_is_not_silently_repaired(self):
        s, _ = battle()
        s.world_state["combat"]["initiative_results"]["player"]["final_total"] += 1
        with self.assertRaises(ValueError):
            s.ensure_combat_state()

    def test_session_isolation_including_hooks(self):
        left, _ = battle()
        right, _ = battle()
        before = copy.deepcopy(right.world_state)
        n = newcomer(left)
        with patch("game.roll_d20", return_value=8):
            left.join_combat_participants([n["id"]])
        left.register_initiative_hook("ON_INITIATIVE_ROLL", lambda *_: None)
        self.assertFalse(hasattr(right, "_initiative_hooks"))
        self.assertEqual(right.world_state, before)

    def test_generic_feature_event_boundaries(self):
        s, ns = actors()
        events = []
        def before(session, context):
            events.append(("on", context["actor_id"]))
            return {"modifiers": [{"source": "owned-feature", "value": 3}]} if context["actor_id"] == "player" else None
        s.register_initiative_hook("ON_INITIATIVE_ROLL", before)
        s.register_initiative_hook("AFTER_INITIATIVE_ROLL", lambda _, c: events.append(("after", c["actor_id"])))
        s.register_initiative_hook("AFTER_INITIATIVE_ORDER_INITIALIZED", lambda _, c: events.append(("order", tuple(c["initiative_order"]))))
        with patch("game.roll_d20", side_effect=[10, 1]):
            s.start_combat(ns[0])
        self.assertEqual([e[0] for e in events], ["on", "on", "after", "after", "order"])
        self.assertEqual(s.world_state["combat"]["initiative_results"]["player"]["final_total"], 15)

    def test_post_roll_swap_preserves_dice_and_rng(self):
        s, ns = actors([{}, {}])
        s.register_initiative_hook("AFTER_INITIATIVE_ORDER_INITIALIZED", lambda *_: [
            {"kind": "swap", "source": "feature-owned-swap", "actor_id": ns[0]["id"], "ally_id": ns[1]["id"], "willing": True}])
        with patch("game.roll_d20", side_effect=[20, 9, 2]) as roller:
            s.start_combat(ns[0])
        self.assertEqual(roller.call_count, 3)
        self.assertEqual(s.world_state["combat"]["initiative_order"], ["player", ns[1]["id"], ns[0]["id"]])
        self.assertEqual(s.world_state["combat"]["initiative_results"][ns[0]["id"]]["final_total"], 9)
        s.ensure_combat_state()

    def test_swap_disallowed_if_incapacitated_or_unwilling(self):
        for condition, willing in ((["incapacitated"], True), ([], False)):
            s, ns = actors([{"conditions": condition}, {}])
            s.register_initiative_hook("AFTER_INITIATIVE_ORDER_INITIALIZED", lambda *_: [
                {"kind": "swap", "source": "feature", "actor_id": ns[0]["id"], "ally_id": ns[1]["id"], "willing": willing}])
            before = copy.deepcopy((s.world_state, s.rng.getstate()))
            with self.assertRaises(ValueError):
                s.start_combat(ns[0])
            self.assertEqual((s.world_state, s.rng.getstate()), before)

    def test_generic_post_roll_adjustment_is_feature_owned(self):
        s, ns = actors()
        s.register_initiative_hook("AFTER_INITIATIVE_ROLL", lambda _, c: [
            {"kind": "count_adjustment", "source": "feature", "actor_id": c["actor_id"], "value": 3}
        ] if c["actor_id"] == "player" else None)
        with patch("game.roll_d20", side_effect=[10, 1]):
            s.start_combat(ns[0])
        self.assertEqual(s.world_state["combat"]["participant_records"][0]["initiative"], 15)
        s.ensure_combat_state()

    def test_legacy_integer_totals_allow_join_without_invented_dice(self):
        s, _ = battle()
        for key in ("initiative_results", "initiative_groups", "initiative_effects"):
            del s.world_state["combat"][key]
        n = newcomer(s)
        with patch("game.roll_d20", return_value=7) as roller:
            s.join_combat_participants([n["id"]])
        self.assertEqual(roller.call_count, 1)
        self.assertEqual(s.world_state["combat"]["initiative_results"]["player"]["raw_rolls"], [])
        self.assertEqual(s.world_state["combat"]["initiative_results"]["player"]["mode"], "legacy_preserved")

    def test_join_failure_restores_rng_and_membership(self):
        s, _ = battle()
        n = newcomer(s)
        s.register_initiative_hook("AFTER_INITIATIVE_ROLL", lambda *_: [{"kind": "invalid", "source": "bad", "actor_id": n["id"]}])
        before = copy.deepcopy((s.world_state, s.rng.getstate()))
        with self.assertRaises(ValueError):
            s.join_combat_participants([n["id"]])
        self.assertEqual((s.world_state, s.rng.getstate()), before)


class InitiativeApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = CombatLifecycleApiTests.asyncSetUp
    asyncTearDown = CombatLifecycleApiTests.asyncTearDown
    setup_combat = CombatLifecycleApiTests.setup_combat
    request = CombatLifecycleApiTests.request
    post = CombatLifecycleApiTests.post
    assert_rejected_unchanged = CombatLifecycleApiTests.assert_rejected_unchanged

    async def test_duplicate_combat_start_receipt_never_rerolls(self):
        s, npc = self.setup_combat()
        s.end_combat()
        command = self.request(s, npc, combat_id=None, combat_round=None, combat_turn_index=None)
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1), patch("game.roll_attack", return_value=1):
            first = await self.post(command)
        self.assertEqual(first.status_code, 200, first.text)
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        with patch("game.roll_initiative_player", side_effect=AssertionError("reroll")), patch("game.roll_initiative", side_effect=AssertionError("reroll")):
            replay = await self.post(command)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    async def test_turn_receipt_replay_preserves_rng_cursor_and_round(self):
        s, npc = self.setup_combat()
        command = self.request(s, npc, message="Turu bitiriyorum.", target_id=None)
        command["combat_action"] = {"steps": [{"kind": "end_turn"}]}
        with patch("game.roll_d20", return_value=1):
            first = await self.post(command)
        self.assertEqual(first.status_code, 200, first.text)
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        replay = await self.post(command)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)
        self.assertEqual(s.world_state["combat"]["round"], 2)

    async def test_client_cannot_override_initiative(self):
        s, npc = self.setup_combat()
        for key, value in (("initiative_order", ["player"]), ("initiative_modifier", 100), ("surprised", True)):
            command = self.request(s, npc)
            command[key] = value
            await self.assert_rejected_unchanged(s, command, 422)

    async def test_client_cannot_issue_initiative_command(self):
        s, npc = self.setup_combat()
        command = self.request(s, npc)
        command["combat_action"] = {"steps": [{"kind": "initiative", "value": 100}]}
        await self.assert_rejected_unchanged(s, command, 422)

    async def test_save_failure_rolls_back_round_rng_and_receipt(self):
        s, npc = self.setup_combat()
        command = self.request(s, npc, target_id=None)
        command["combat_action"] = {"steps": [{"kind": "end_turn"}]}
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("controlled")), patch("game.roll_d20", return_value=1):
            await self.assert_rejected_unchanged(s, command, 503)

    async def test_campaign_resume_has_exact_cursor_results_and_receipts(self):
        s, npc = self.setup_combat()
        command = self.request(s, npc, target_id=None)
        command["combat_action"] = {"steps": [{"kind": "move", "distance_ft": 5}]}
        response = await self.post(command)
        self.assertEqual(response.status_code, 200, response.text)
        manager = SessionManager(session_factory=scene, campaign_store=CampaignStore(self.store.path))
        _, restored, _, _, _ = manager.resume_campaign(self.created["campaign_id"])
        self.assertEqual(restored.game_session.world_state["combat"], s.world_state["combat"])
        self.assertEqual(manager.get_turn_action(restored, command["action_id"])["response"]["combat_result"], response.json()["combat_result"])

    async def test_corrupt_initiative_cannot_commit_turn_or_reroll(self):
        s, npc = self.setup_combat()
        s.world_state["combat"]["current_turn_index"] = 100
        command = self.request(s, npc, target_id=None)
        command["combat_action"] = {"steps": [{"kind": "move", "distance_ft": 5}]}
        with patch("game.roll_d20", side_effect=AssertionError("reroll")):
            response = await self.post(command)
        self.assertGreaterEqual(response.status_code, 400)