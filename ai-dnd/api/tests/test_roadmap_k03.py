"""K03: timed effects are consumed by the ACTUAL elapsed game time, once.

Celestial Revelation lasts 1 minute and Large Form 10 minutes (PHB 2024 PDF p.185 / Goliath). Before K03 a wait, rest or
travel never advanced them (only combat turns did). The clock-driven path takes the actual elapsed seconds reported by
campaign_time (not the requested ones), never counts one source event twice, and leaves combat rounds to the turn-boundary
owner so a round tick plus the player's turn end make ONE decrement.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import effect_lifecycle
import game
import scheduled_events as events
from api.tests.test_species_traits import make_session

MINUTE = 60


def aasimar_with_wings():
    session = make_session("Aasimar", level=3)
    session.resolve_species_trait_action("celestial_revelation", form="heavenly_wings")
    return session


def active(session, key="active_celestial_form"):
    return session.character["species_trait_state"][key] is not None


class ActualElapsedTests(unittest.TestCase):
    def test_effect_uses_actual_elapsed_once(self):
        session = aasimar_with_wings()
        expiry = []

        def wait(seconds):
            result = session.advance_campaign_time(seconds, "explicit_wait")
            expiry.extend(event for event in result.get("effect_events", []) if event.get("expired"))
            return result

        wait(59)
        at_59 = active(session)
        result = wait(1)
        at_60 = active(session)
        wait(1)
        obs = {
            "active_at_59s": at_59,
            "active_at_60s": at_60,
            "expiry_events_at_61s": len(expiry),
            "effect_elapsed_s": expiry[0]["elapsed_s"] if expiry else None,
            "time_result": result,
        }
        self.assertIs(obs["active_at_59s"], True)
        self.assertIs(obs["active_at_60s"], False)
        self.assertEqual(obs["expiry_events_at_61s"], 1)
        self.assertEqual(obs["effect_elapsed_s"], obs["time_result"]["elapsed_seconds"],
                         "the expiring step reports the actual seconds it consumed")

    def test_one_hour_wait_ends_every_timed_effect(self):
        session = make_session("Goliath", ancestry="fire", level=5)
        session.resolve_species_trait_action("large_form")
        self.assertTrue(session.character["species_trait_state"]["large_form_turns_remaining"] > 0)
        result = session.advance_campaign_time(3600, "explicit_wait")
        self.assertEqual(session.character["species_trait_state"]["large_form_turns_remaining"], 0)
        self.assertEqual([event["trait"] for event in result["effect_events"] if event.get("expired")], ["large_form"])

    def test_an_interrupted_long_wait_consumes_only_the_actual_time(self):
        session = make_session("Goliath", ancestry="fire", level=5)
        session.resolve_species_trait_action("large_form")  # 600 s
        events.register_event(
            session.world_state, event_id="visitor", window_start=100, window_end=160, location_id="tavern",
            behavior="INTERRUPTIVE", requires_decision=True, summary="Biri kapıya geldi.", effects=[])
        result = session.advance_campaign_time(7 * 86400, "explicit_wait")
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["elapsed_seconds"], 100)
        self.assertLess(result["elapsed_seconds"], result["requested_seconds"])
        clock = session.character["species_trait_state"]["effect_clock"]
        self.assertEqual(clock["remaining_s"]["large_form"], 500, "600 - the 100 s that really passed, not 600 - 7 days")
        self.assertTrue(session.character["species_trait_state"]["large_form_turns_remaining"] > 0)

    def test_the_same_source_event_never_decrements_twice(self):
        session = aasimar_with_wings()
        first = effect_lifecycle.advance_effects(session, 30, "event:A", "clock")
        again = effect_lifecycle.advance_effects(session, 30, "event:A", "clock")
        self.assertEqual((first, again), ([], []))
        self.assertEqual(session.character["species_trait_state"]["effect_clock"]["remaining_s"]["celestial_revelation"], 30)
        effect_lifecycle.advance_effects(session, 30, "event:B", "clock")
        self.assertFalse(active(session))

    def test_a_combat_round_tick_and_the_turn_end_make_one_decrement(self):
        session = aasimar_with_wings()
        state = session.character["species_trait_state"]
        before = state["celestial_revelation_turns_remaining"]
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            session.world_state["npcs"].append({
                "id": "foe", "name": "Foe", "location": session.world_state["location"], "combat_status": "active",
                "current_hp": 10, "max_hp": 10, "armor_class": 10, "distance_ft": 5})
            session.start_combat(session.world_state["npcs"][-1])
        session._finish_species_player_turn()  # the turn boundary owns this decrement
        session.advance_campaign_time(6, "combat_round")  # the clock tick must not take a second one
        self.assertEqual(state["celestial_revelation_turns_remaining"], before - 1)
        self.assertEqual(state["effect_clock"]["remaining_s"]["celestial_revelation"], (before - 1) * 6)

    def test_the_player_wait_path_really_expires_the_effect(self):
        # The player's "bekliyorum" does not go through game.advance_campaign_time but timed_gameplay._advance.
        from uuid import uuid4
        session = aasimar_with_wings()
        result = session.run_player_turn("2 dakika bekliyorum.", action_id=str(uuid4()))["action_result"]
        self.assertEqual(result["time_result"]["elapsed_seconds"], 120)
        self.assertFalse(active(session), "a two minute wait outlasts a one minute effect")

    def test_walking_and_other_timed_paths_consume_actual_time(self):
        import timed_gameplay
        for reason in ("explicit_wait", "travel_stage", "active_task"):
            with self.subTest(reason=reason):
                session = aasimar_with_wings()
                timed_gameplay._advance(session, 59, reason)
                self.assertTrue(active(session))
                timed_gameplay._advance(session, 1, reason)
                self.assertFalse(active(session))

    def test_a_zero_length_step_does_not_swallow_the_next_real_step(self):
        session = aasimar_with_wings()
        effect_lifecycle.advance_effects(session, 0, "turn:1@0", "clock")
        effect_lifecycle.advance_effects(session, 30, "turn:1@0", "clock")
        self.assertEqual(session.character["species_trait_state"]["effect_clock"]["remaining_s"]["celestial_revelation"], 30)

    def test_clock_time_inside_combat_is_left_to_the_turn_boundary_owner(self):
        session = aasimar_with_wings()
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            session.world_state["npcs"].append({
                "id": "foe", "name": "Foe", "location": session.world_state["location"], "combat_status": "active",
                "current_hp": 10, "max_hp": 10, "armor_class": 10, "distance_ft": 5})
            session.start_combat(session.world_state["npcs"][-1])
        before = session.character["species_trait_state"]["celestial_revelation_turns_remaining"]
        session.advance_campaign_time(12, "explicit_wait")
        self.assertEqual(session.character["species_trait_state"]["celestial_revelation_turns_remaining"], before)

    def test_an_invalid_effect_clock_is_rejected_on_load(self):
        session = aasimar_with_wings()
        state = session.character["species_trait_state"]
        state["effect_clock"]["remaining_s"]["celestial_revelation"] = -1
        with self.assertRaises(ValueError):
            game._validate_species_trait_state(state, "Aasimar")
        state["effect_clock"] = {"version": 2, "remaining_s": {}, "last_event": {}}
        with self.assertRaises(ValueError):
            game._validate_species_trait_state(state, "Aasimar")

    def test_legacy_saves_without_the_effect_clock_load_and_adapt(self):
        session = make_session("Aasimar", level=3)
        state = session.character["species_trait_state"]
        state.update(active_celestial_form="heavenly_wings", celestial_revelation_turns_remaining=4)
        self.assertNotIn("effect_clock", state)
        game._validate_species_trait_state(state, "Aasimar")
        session.advance_campaign_time(23, "explicit_wait")
        self.assertTrue(active(session), "legacy 4 turns = 24 s; 23 s have passed")
        session.advance_campaign_time(1, "explicit_wait")
        self.assertFalse(active(session))
        game._validate_species_trait_state(state, "Aasimar")


if __name__ == "__main__":
    unittest.main()
