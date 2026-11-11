"""Dilim 4B Task 2: a foe that accepted-surrendered (not a parley) counts as beaten; a retreating foe does not.

Engine tests on the monster-combat fixture; the proposals and the flee decision come from the real monster
memory (`monster_combat.state`, `run_turn`, `player_response`), the ending from the real lifecycle."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import monster_combat as ai
from api.tests import test_dilim4b_combat_xp as t1
from api.tests.test_monster_combat import activate, fixture, run


def prepared(**data):
    s, n = fixture(personality="cowardly", role="muhafız", **data)
    t1.fighter(s)
    s.world_state["location"] = "tavern"
    n["location"] = "tavern"
    n.update(current_hp=10, conditions=["frightened"], frightened_by="player")
    return s, n


def propose(s, n, kind, status="pending", combat_id=None):
    """Put a proposal into the foe's memory the way a monster turn does (id starts with the fight's id)."""
    memory = ai.state(s, n["id"])
    cid = combat_id or s.world_state["combat"]["combat_id"]
    memory.setdefault("proposals", []).append(
        {"proposal_id": f"{cid}:1:{n['id']}:0:{kind}", "type": kind, "status": status, "actor_id": n["id"]})


def accept(s, n, word="Teslim olma teklifini kabul ediyorum."):
    for _ in range(6):
        if s.world_state["combat"]["current_actor_id"] == n["id"]:
            break
        s.advance_combat_turn()
    for _ in range(6):
        s.advance_combat_turn()
        if s.world_state["combat"]["current_actor_id"] == "player":
            break
    return s.run_player_turn(word, target_id=n["id"])


def flee(s, n):
    s.world_state["monster_routes"] = {n["id"]: [{
        "route_id": "door_route", "known": True, "clear": True, "destination": "doorway", "distance_ft": 20,
        "start_distances": {"player": 5}, "target_distances": {"player": 25}, "movement_intent": "RETREAT"}]}
    for _ in range(4):
        if s.world_state["combat"]["current_actor_id"] == n["id"]:
            break
        s.advance_combat_turn()
    result = run(s, n)
    assert result["decisions"][0]["decision_type"] == "FLEE_DECLARED", result["decisions"]
    return result


class YieldAndFleeXp(unittest.TestCase):
    def xp(self, s):
        return s.character["xp"]

    def test_an_accepted_surrender_pays_the_foe(self):
        s, n = prepared()
        propose(s, n, "SURRENDER_PROPOSED")
        accept(s, n)
        self.assertEqual(s.world_state["combat"]["end_reason"], "parley_accepted")
        self.assertEqual(self.xp(s), 25)
        self.assertEqual(s.world_state["xp_awarded_event_ids"], ["combat:foe:" + n["id"]])

    def test_parley_is_not_a_surrender(self):
        s, n = prepared()
        propose(s, n, "PARLEY_PROPOSED")
        accept(s, n, "Ateşkes yapalım, kabul ediyorum.")
        self.assertEqual(s.world_state["combat"]["end_reason"], "parley_accepted")
        self.assertEqual(self.xp(s), 0)
        self.assertEqual(s.world_state["xp_awarded_event_ids"], [])

    def test_rejected_surrender_pays_nothing(self):
        s, n = prepared()
        propose(s, n, "SURRENDER_PROPOSED")
        accept(s, n, "Teslim olma teklifini reddediyorum.")
        self.assertTrue(s.world_state["combat"]["active"])
        self.assertEqual(self.xp(s), 0)

    def test_a_surrender_from_a_previous_fight_does_not_count(self):
        s, n = prepared()
        propose(s, n, "SURRENDER_PROPOSED", status="accepted", combat_id="combat-old")
        self.assertFalse(ai.surrendered_in(s.world_state, s.world_state["combat"]["combat_id"], n["id"]))
        s.end_combat("parley_accepted")
        self.assertEqual(self.xp(s), 0)

    def test_a_retreating_foe_stays_in_the_fight_and_pays_nothing(self):
        """Verified: the native RETREAT route moves position/distance only; the npc keeps its location and the
        fight goes on, so there is no real 'fled the fight' event to pay (J-099 finding 1)."""
        s, n = prepared()
        flee(s, n)
        self.assertEqual(n["location"], s.world_state["location"])
        self.assertEqual(n["position"], "doorway")
        self.assertTrue(s.world_state["combat"]["active"])
        self.assertIsNone(s._combat_end_if_decided())
        self.assertEqual(self.xp(s), 0)
        n.update(current_hp=0, combat_status="dead")        # beaten afterwards: pays once, by the defeat
        s._combat_end_if_decided()
        self.assertEqual(self.xp(s), 25)

    def test_a_beaten_foe_and_a_surrendering_one_end_the_fight_and_pay_both(self):
        """J-099 finding 2: the beaten foe must not hold the ending hostage."""
        s, n = prepared()
        drunk = t1.person("drunk1", "ayyaş")
        s.world_state["npcs"].append(drunk)
        with patch("game.roll_initiative", return_value=1):
            s.join_combat_participants([drunk["id"]])
        drunk.update(current_hp=0, combat_status="dead")
        propose(s, n, "SURRENDER_PROPOSED")
        accept(s, n)
        self.assertFalse(s.world_state["combat"]["active"])
        self.assertEqual(s.world_state["combat"]["end_reason"], "parley_accepted")
        self.assertEqual(self.xp(s), 35)
        self.assertEqual(sorted(s.world_state["xp_awarded_event_ids"]),
                         sorted(["combat:foe:" + n["id"], "combat:foe:drunk1"]))

    def test_a_beaten_foe_and_a_parleying_one_pay_only_the_beaten(self):
        s, n = prepared()
        drunk = t1.person("drunk1", "ayyaş")
        s.world_state["npcs"].append(drunk)
        with patch("game.roll_initiative", return_value=1):
            s.join_combat_participants([drunk["id"]])
        drunk.update(current_hp=0, combat_status="dead")
        propose(s, n, "PARLEY_PROPOSED")
        accept(s, n, "Ateşkes yapalım, kabul ediyorum.")
        self.assertEqual(s.world_state["combat"]["end_reason"], "parley_accepted")
        self.assertEqual(self.xp(s), 10)

    def test_a_beaten_foe_and_a_rejected_surrender_keep_the_fight_going(self):
        s, n = prepared()
        drunk = t1.person("drunk1", "ayyaş")
        s.world_state["npcs"].append(drunk)
        with patch("game.roll_initiative", return_value=1):
            s.join_combat_participants([drunk["id"]])
        drunk.update(current_hp=0, combat_status="dead")
        propose(s, n, "SURRENDER_PROPOSED")
        accept(s, n, "Teslim olma teklifini reddediyorum.")
        self.assertTrue(s.world_state["combat"]["active"])
        self.assertEqual(self.xp(s), 0)

    def test_a_second_resisting_foe_still_blocks_the_ending(self):
        s, n = prepared()
        other = t1.person("brute1", "muhafız")
        s.world_state["npcs"].append(other)
        with patch("game.roll_initiative", return_value=1):
            s.join_combat_participants([other["id"]])
        propose(s, n, "SURRENDER_PROPOSED")
        accept(s, n)
        self.assertTrue(s.world_state["combat"]["active"])
        self.assertEqual(self.xp(s), 0)

    def test_a_dead_foe_and_a_relocated_one_without_a_flee_pays_only_the_dead(self):
        s, n = prepared()
        drunk = t1.person("drunk1", "ayyaş")
        s.world_state["npcs"].append(drunk)
        with patch("game.roll_initiative", return_value=1):
            s.join_combat_participants([drunk["id"]])
        n["location"] = "forest"
        drunk.update(current_hp=0, combat_status="dead")
        ended = s._combat_end_if_decided()
        self.assertEqual(ended["reason"], "opponents_relocated")
        self.assertEqual(self.xp(s), 10)

    def test_player_leaving_pays_nothing(self):
        s, n = prepared()
        s.end_combat("location_changed")
        self.assertEqual(self.xp(s), 0)

    def test_a_moved_foe_without_a_flee_decision_pays_nothing(self):
        s, n = prepared()
        n["location"] = "forest"
        s._combat_end_if_decided()
        self.assertEqual(self.xp(s), 0)


if __name__ == "__main__":
    unittest.main()
