"""Dilim 4C Task 0 (G1, D-005): a foe whose surrender the player accepted leaves the fight.

The fight's own saved record (the accepted SURRENDER proposal in the foe's monster memory) makes its participant record
read 'surrendered': it no longer counts as an enemy, takes no turn and no reaction, and a player who strikes it is asked
first (repair, never a refusal). XP stays one receipt per creature (combat:foe:<id>), paid by the ending or the knock-out.
Engine tests on the Dilim 4B yield fixture (monster_combat fixture, fixed session seed); the route chain is in
test_dilim4c_surrender_routes."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import action_economy
import game
import xp
from api.tests import test_dilim4b_combat_xp as t1
from api.tests.test_dilim4b_yield_flee_xp import accept, prepared, propose


def two_foes():
    """The surrendering guard and a second guard who keeps fighting."""
    s, n = prepared()
    other = t1.person("brute1", "muhafız", distance_ft=5)
    s.world_state["npcs"].append(other)
    with patch("game.roll_initiative", return_value=1):
        s.join_combat_participants([other["id"]])
    return s, n, other


def record(s, identity):
    return next(r for r in s.world_state["combat"]["participant_records"] if r["id"] == identity)


def surrendered_fight():
    s, n, other = two_foes()
    propose(s, n, "SURRENDER_PROPOSED")
    accept(s, n)
    return s, n, other


class SurrenderedFoeLeavesTheFight(unittest.TestCase):
    def test_an_accepted_surrender_writes_the_surrendered_state(self):
        s, n, other = surrendered_fight()
        self.assertTrue(s.world_state["combat"]["active"])
        self.assertEqual(record(s, n["id"])["status"], "surrendered")
        self.assertEqual(record(s, other["id"])["status"], "active")
        saved = s.serialize_game_state()
        s._validate_save_payload(saved)  # a save taken right now loads
        (written,) = [r for r in saved["world_state"]["combat"]["participant_records"] if r["id"] == n["id"]]
        self.assertEqual(written["status"], "surrendered")

    def test_the_surrendered_foe_takes_no_turn_and_no_reaction(self):
        s, n, other = surrendered_fight()
        self.assertFalse(action_economy.can_act(s, n["id"]))
        self.assertTrue(action_economy.can_act(s, other["id"]))
        self.assertFalse(s._combat_participant_can_act(s.world_state["combat"], n["id"]))
        seen = []
        for _ in range(6):
            s.advance_combat_turn()
            seen.append(s.world_state["combat"]["current_actor_id"])
        self.assertNotIn(n["id"], seen)
        self.assertIn(other["id"], seen)

    def test_a_rejected_surrender_keeps_the_foe_fighting(self):
        s, n, other = two_foes()
        propose(s, n, "SURRENDER_PROPOSED")
        accept(s, n, "Teslim olma teklifini reddediyorum.")
        self.assertEqual(record(s, n["id"])["status"], "active")
        self.assertTrue(action_economy.can_act(s, n["id"]))

    def test_a_parley_does_not_take_the_foe_out(self):
        s, n, other = two_foes()
        propose(s, n, "PARLEY_PROPOSED")
        accept(s, n, "Ateşkes yapalım, kabul ediyorum.")
        self.assertEqual(record(s, n["id"])["status"], "active")

    def test_a_surrender_from_a_previous_fight_does_not_take_the_foe_out(self):
        s, n, other = two_foes()
        propose(s, n, "SURRENDER_PROPOSED", status="accepted", combat_id="combat-old")
        s._sync_combat_participant_records(s.world_state["combat"])
        self.assertEqual(record(s, n["id"])["status"], "active")
        self.assertTrue(action_economy.can_act(s, n["id"]))


class SurrenderAndXp(unittest.TestCase):
    """Today (before 4C.0) the surrendered foe kept the fight open: beating the other guard ended nothing and paid nothing."""

    def test_beating_the_last_resisting_foe_ends_the_fight_and_pays_both_once(self):
        s, n, other = surrendered_fight()
        self.assertEqual(s.character["xp"], 0)
        other.update(current_hp=0, combat_status="dead")
        ended = s._combat_end_if_decided()
        self.assertEqual(ended["reason"], "target_defeated")
        self.assertEqual(s.character["xp"], 50)
        self.assertEqual(sorted(s.world_state["xp_awarded_event_ids"]),
                         sorted(["combat:foe:" + n["id"], "combat:foe:brute1"]))

    def test_a_surrendered_foe_knocked_out_afterwards_is_paid_once(self):
        s, n, other = surrendered_fight()
        import fallen
        fallen.knock_out(s, n)  # the player struck it anyway (after the question) and knocked it out
        self.assertEqual(s.character["xp"], 25)
        s._sync_combat_participant_records(s.world_state["combat"])
        self.assertEqual(record(s, n["id"])["status"], "unconscious")
        other.update(current_hp=0, combat_status="dead")
        self.assertEqual(s._combat_end_if_decided()["reason"], "target_defeated")
        self.assertEqual(s.character["xp"], 50)
        self.assertEqual(s.world_state["xp_awarded_event_ids"].count("combat:foe:" + n["id"]), 1)
        self.assertIsNone(xp.award_defeated_combat({"participants": ["player", n["id"]], "combat_id": "x"},
                                                   s.world_state, s.character))

    def test_the_last_foe_surrendering_still_ends_with_parley_and_pays_once(self):
        s, n = prepared()
        propose(s, n, "SURRENDER_PROPOSED")
        accept(s, n)
        self.assertEqual(s.world_state["combat"]["end_reason"], "parley_accepted")
        self.assertEqual(s.character["xp"], 25)
        self.assertEqual(s.world_state["xp_awarded_event_ids"], ["combat:foe:" + n["id"]])


class OldSaves(unittest.TestCase):
    def test_a_save_written_before_the_surrendered_state_loads_and_reads_surrendered(self):
        """Before 4C.0 the record of an accepted-surrendered foe was saved as 'active' (the proposal was already saved)."""
        s, n, other = surrendered_fight()
        payload = s.serialize_game_state()
        for r in payload["world_state"]["combat"]["participant_records"]:
            if r["id"] == n["id"]:
                r["status"] = "active"  # exactly what the pre-change engine wrote
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = game.GameSession(seed=987)
            loaded.load_game(path)
        loaded.ensure_combat_state()
        self.assertEqual(record(loaded, n["id"])["status"], "surrendered")
        self.assertFalse(action_economy.can_act(loaded, n["id"]))


class AskBeforeStrikingTheSurrendered(unittest.TestCase):
    def player_turn(self, s):
        combat = s.world_state["combat"]
        for _ in range(6):
            if combat["current_actor_id"] == "player":
                return
            s.advance_combat_turn()
        self.fail("the player's turn never came")

    def test_striking_a_surrendered_foe_asks_first_and_changes_nothing(self):
        s, n, other = surrendered_fight()
        self.player_turn(s)
        held = ("combat", "npcs", "monster_combat", "xp_awarded_event_ids")
        before = copy.deepcopy(({k: s.world_state.get(k) for k in held}, s.character))
        result = s.run_player_turn("Muhafıza saldırıyorum", target_id=n["id"])
        self.assertEqual(result["action_result"]["status"], "clarification")
        self.assertEqual(result["action_result"]["outcome"], "surrendered_target")
        self.assertIn("teslim olmuş birine saldırıyorsun", result["narration"])
        self.assertEqual(({k: s.world_state.get(k) for k in held}, s.character), before)

    def test_a_yes_strikes(self):
        s, n, other = surrendered_fight()
        self.player_turn(s)
        s.run_player_turn("Muhafıza saldırıyorum", target_id=n["id"])
        with patch("game.roll_attack", return_value=20):
            result = s.run_player_turn("evet", target_id=n["id"])
        self.assertNotEqual(result["action_result"].get("status"), "clarification")
        self.assertLess(n["current_hp"], 10)

    def test_a_no_strikes_nothing(self):
        s, n, other = surrendered_fight()
        self.player_turn(s)
        s.run_player_turn("Muhafıza saldırıyorum", target_id=n["id"])
        before = n["current_hp"]
        s.run_player_turn("hayır", target_id=n["id"])
        self.assertEqual(n["current_hp"], before)
        self.assertIsNone(getattr(s, "_surrender_strike_asked", None))

    def test_striking_the_fighting_foe_is_not_asked(self):
        s, n, other = surrendered_fight()
        self.player_turn(s)
        with patch("game.roll_attack", return_value=20):
            result = s.run_player_turn("Muhafıza saldırıyorum", target_id=other["id"])
        self.assertNotEqual(result["action_result"].get("outcome"), "surrendered_target")


if __name__ == "__main__":
    unittest.main()
