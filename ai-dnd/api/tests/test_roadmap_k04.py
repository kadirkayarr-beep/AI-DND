"""K04: a long time skip stops BEFORE a player commitment, and simultaneous due items resolve in an explicit order.

The skip must report actual/requested/remaining/interrupted, must not apply the player's decision for them, and a
reload or retry must not resume the remainder by itself. Simultaneous due items (effect expiry, damage, death,
regeneration) use one recorded rule order with the stable event id as the technical tie-break; an unranked kind is an
unresolved conflict that stops (never a call-order guess).
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import event_order
import game
import scheduled_events as events
from api.tests.test_campaign_time import scene, turn

DAY = 86400


def commitment(session, at=3 * DAY):
    # A scheduled event only establishes world reality; the player's answer to it stays a separate, pending decision.
    return events.register_event(
        session.world_state, event_id="heavy-debt", window_start=at, window_end=at + 600, location_id="tavern",
        behavior="INTERRUPTIVE", requires_decision=True, summary="Tefeci ağır bir borç teklif ediyor.", effects=[])


def decided_without_the_player(session):
    return [e["event_id"] for e in session.world_state["scheduled_events"]
            if e.get("decision_status") not in (None, "NONE", "PENDING")]


class TimeSkipTests(unittest.TestCase):
    def test_timeskip_stops_before_player_commitment(self):
        session = scene()
        item = commitment(session)
        inventory_before = copy.deepcopy(session.world_state.get("inventory"))
        result = turn(session, "7 gün bekliyorum.")["action_result"]
        obs = {
            "time_result": result["time_result"],
            "unapproved_commitments": len(decided_without_the_player(session))
            + int(session.world_state.get("inventory") != inventory_before),
        }
        self.assertEqual(obs["time_result"]["elapsed_seconds"], 3 * DAY)
        self.assertEqual(obs["time_result"]["remaining_seconds"], 4 * DAY)
        self.assertIs(obs["time_result"]["interrupted"], True)
        self.assertEqual(obs["unapproved_commitments"], 0, "the world event must not decide the debt for the player")
        self.assertEqual(item["decision_status"], "PENDING")

    def test_reload_and_retry_never_resume_the_remainder_by_themselves(self):
        session = scene()
        commitment(session)
        action_id = str(uuid4())
        session.run_player_turn("7 gün bekliyorum.", action_id=action_id)
        stopped_at = session.world_state["campaign_time"]["elapsed_seconds"]
        self.assertEqual(stopped_at, 3 * DAY)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            path.write_text(json.dumps(session.serialize_game_state(), ensure_ascii=False), encoding="utf-8")
            reloaded = scene()
            reloaded.load_game(str(path))
        self.assertEqual(reloaded.world_state["campaign_time"]["elapsed_seconds"], stopped_at, "nothing advanced on reload")
        self.assertEqual(decided_without_the_player(reloaded), [])
        # A retry of the SAME action must not run the remainder either: the pending decision keeps the clock still.
        retry = session.run_player_turn("7 gün bekliyorum.", action_id=action_id)["action_result"]
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], stopped_at)
        self.assertIsNotNone(retry)


class ProductionLoopTests(unittest.TestCase):
    """The real clock loop obeys the recorded order when an effect expires at the same moment the recovery timer fires."""

    def build(self):
        from api.tests.test_species_traits import make_session
        session = make_session("Aasimar", level=3)
        session.world_state["death_state"]["mode"] = "PERMADEATH"
        session._apply_player_damage(20, took_damage=True)
        with patch.object(session.rng, "randint", return_value=2):
            session.stabilize_player()
        recovery_at = session.world_state["death_state"]["recovery"]["at"]
        now = session.world_state["campaign_time"]["elapsed_seconds"]
        state = session.character["species_trait_state"]
        state.update(active_celestial_form="heavenly_wings", celestial_revelation_turns_remaining=10,
                     effect_clock={"version": 1, "remaining_s": {"celestial_revelation": recovery_at - now}, "last_event": {}})
        return session, recovery_at - now

    def run_order(self, rule_order):
        session, wait = self.build()
        calls = []
        real_heal, real_effects = game.heal_player, game.effect_lifecycle.advance_effects

        def heal(amount):
            calls.append("regeneration")
            return real_heal(amount)

        def effects(*args, **kwargs):
            outcome = real_effects(*args, **kwargs)
            if outcome:
                calls.append("effect_expiry")
            return outcome

        with patch.object(game, "RULE_ORDER", rule_order), patch.object(game, "heal_player", heal), \
                patch.object(game.effect_lifecycle, "advance_effects", effects):
            result = session.advance_campaign_time(wait, "explicit_wait")
        return calls, result

    def test_the_production_clock_loop_obeys_the_recorded_rule_order(self):
        calls, result = self.run_order(event_order.DEFAULT_RULE_ORDER)
        self.assertEqual(calls, ["effect_expiry", "regeneration"], "each ran exactly once, expiry first")
        flipped = {"regeneration": 0, "effect_expiry": 1, "death": 2, "damage": 3}
        calls, _ = self.run_order(flipped)
        self.assertEqual(calls, ["regeneration", "effect_expiry"], "changing the one table changes the real order")
        self.assertEqual(len(result["effect_events"]), 1)


class NonTimedViewsTests(unittest.TestCase):
    def test_reading_state_menus_recaps_and_reloads_advance_no_timed_consumer(self):
        # Out-of-character views (state read, recap, save/reload) never reach a timed consumer.
        from api.tests.test_species_traits import make_session
        session = make_session("Aasimar", level=3)
        session.resolve_species_trait_action("celestial_revelation", form="heavenly_wings")
        before = (copy.deepcopy(session.world_state["campaign_time"]), copy.deepcopy(session.character["species_trait_state"]))
        for _ in range(3):
            session.serialize_game_state()
            game.campaign_time.public_time(session.world_state)
        self.assertEqual(before, (session.world_state["campaign_time"], session.character["species_trait_state"]))


    def test_the_supplies_condition_death_return_still_settles_deferred_effects(self):
        # Flipped order defers the effects until after the death/recovery timer; the early supplies return must not skip them.
        flipped = {"regeneration": 0, "effect_expiry": 1, "death": 2, "damage": 3}
        session, wait = ProductionLoopTests("build").build()
        session.world_state["supplies_policy"] = {"enabled": True}
        with patch.object(game, "RULE_ORDER", flipped), patch("equipment_economy.process_supply_days",
                                                              return_value={"death_results": []}):
            result = session.advance_campaign_time(wait, "explicit_wait")
        self.assertTrue(result.get("condition_death"))
        self.assertEqual([event["trait"] for event in result["effect_events"]], ["celestial_revelation"])
        self.assertIsNone(session.character["species_trait_state"]["active_celestial_form"])

    def test_an_incomplete_rule_table_is_refused_before_the_clock_moves(self):
        session, wait = ProductionLoopTests("build").build()
        before = session.world_state["campaign_time"]["elapsed_seconds"]
        with patch.object(game, "RULE_ORDER", {"death": 0}):
            with self.assertRaises(event_order.UnresolvedRuleOrder):
                session.advance_campaign_time(wait, "explicit_wait")
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], before)


class RuleOrderTests(unittest.TestCase):
    ORDER = event_order.DEFAULT_RULE_ORDER

    def test_simultaneous_items_resolve_once_in_the_recorded_rule_order(self):
        due = [
            {"event_id": "z", "kind": "regeneration", "at": 600},
            {"event_id": "b", "kind": "death", "at": 600},
            {"event_id": "a", "kind": "damage", "at": 600},
            {"event_id": "c", "kind": "effect_expiry", "at": 600},
            {"event_id": "early", "kind": "regeneration", "at": 60},
        ]
        ordered = [item["event_id"] for item in event_order.order_due_events(due, self.ORDER)]
        self.assertEqual(ordered, ["early", "c", "a", "b", "z"])
        self.assertEqual(ordered, [item["event_id"] for item in event_order.order_due_events(list(reversed(due)), self.ORDER)])

    def test_the_stable_event_id_breaks_ties_inside_one_rule_rank(self):
        due = [{"event_id": "m2", "kind": "damage", "at": 5}, {"event_id": "m1", "kind": "damage", "at": 5}]
        self.assertEqual([i["event_id"] for i in event_order.order_due_events(due, self.ORDER)], ["m1", "m2"])

    def test_an_unranked_simultaneous_kind_stops_instead_of_guessing(self):
        due = [{"event_id": "a", "kind": "mystery", "at": 5}, {"event_id": "b", "kind": "damage", "at": 5}]
        with self.assertRaises(event_order.UnresolvedRuleOrder):
            event_order.order_due_events(due, self.ORDER)
        alone = [{"event_id": "a", "kind": "mystery", "at": 5}, {"event_id": "b", "kind": "damage", "at": 9}]
        self.assertEqual([i["event_id"] for i in event_order.order_due_events(alone, self.ORDER)], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
