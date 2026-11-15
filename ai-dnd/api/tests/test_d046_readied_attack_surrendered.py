"""D-046: a readied attack (Ready + response.attack) at a surrendered foe is asked about when it lands, like any blow.

The trigger may be another creature (the fighting foe moves) while the response strikes the surrendered one, so the
readied blow can fire today. The question comes when the Reaction is taken (the blow), not when Ready is declared: the
foe may surrender after the Ready, and one gate covers both. Engine tests on the 4C.0 fixture (monster_combat
fixture, fixed session seed)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import action_economy
import combat_lifecycle
from api.tests.test_dilim4c_surrender_spells import caster_fight, held


def ready_at(trigger_actor, target):
    return {"steps": [{"kind": "ready", "trigger": {"event": "actor_moves", "actor_id": trigger_actor},
                       "response": {"kind": "attack", "target_id": target}}]}


def fired(s, n, other, target):
    """Ready an attack at `target`, triggered by the fighting foe moving; return the react command."""
    for pair in s.world_state["attack_environment"]["pairs"].values():
        pair["distance_ft"] = 5  # both foes in reach of the readied punch
    s.run_player_turn("Hamle.", combat_action=ready_at(other["id"], target["id"]))
    action_economy.publish_event(s, "actor_moves", other["id"])
    opportunity = action_economy.ensure(s)["player"]["opportunity"]
    assert opportunity, "the readied trigger must fire"
    return {"steps": [{"kind": "react", "opportunity_id": opportunity["id"]}]}


class ReadiedAttackAtTheSurrenderedIsAsked(unittest.TestCase):
    def test_the_reaction_asks_first_and_changes_nothing(self):
        s, n, other = caster_fight()
        react = fired(s, n, other, n)
        before = held(s)
        result = s.run_player_turn("Hamle.", combat_action=react)
        self.assertEqual(result["action_result"]["status"], "clarification")
        self.assertEqual(result["action_result"]["outcome"], "surrendered_target")
        self.assertEqual(result["action_result"]["target_id"], n["id"])
        self.assertIn("teslim olmuş birine saldırıyorsun", result["narration"])
        self.assertEqual(held(s), before)
        self.assertFalse(action_economy.ensure(s)["player"]["reaction_spent"])

    def test_a_yes_takes_the_readied_blow_once(self):
        s, n, other = caster_fight()
        s.run_player_turn("Hamle.", combat_action=fired(s, n, other, n))
        with patch("game.roll_d20", return_value=19):
            result = s.run_player_turn("evet")
        self.assertNotEqual(result["action_result"].get("status"), "clarification")
        self.assertTrue(action_economy.ensure(s)["player"]["reaction_spent"])
        self.assertIsNone(action_economy.ensure(s)["player"]["ready"])
        self.assertLess(n["current_hp"], 10)
        self.assertEqual(other["current_hp"], 8)
        self.assertIsNone(s._surrender_strike_asked)

    def test_a_typed_reaction_asks_first(self):
        s, n, other = caster_fight()
        fired(s, n, other, n)
        result = s.run_player_turn("Reaksiyonumu kullanıyorum")
        self.assertEqual(result["action_result"]["outcome"], "surrendered_target")
        self.assertEqual(n["current_hp"], 10)

    def test_a_no_strikes_nothing_and_the_reaction_can_still_be_declined(self):
        s, n, other = caster_fight()
        react = fired(s, n, other, n)
        s.run_player_turn("Hamle.", combat_action=react)
        with self.assertRaises(combat_lifecycle.CombatRequestError) as caught:
            s.run_player_turn("hayır")  # the pending Reaction's own rule: take it or decline it
        self.assertEqual(caught.exception.code, "reaction_pending")
        self.assertIsNone(getattr(s, "_surrender_strike_asked", None))
        opportunity = react["steps"][0]["opportunity_id"]
        s.run_player_turn("Hamle.", combat_action={"steps": [{"kind": "decline_reaction", "opportunity_id": opportunity}]})
        self.assertEqual(n["current_hp"], 10)
        self.assertFalse(action_economy.ensure(s)["player"]["reaction_spent"])
        self.assertIsNone(action_economy.ensure(s)["player"]["opportunity"])

    def test_a_readied_attack_at_the_fighting_foe_is_not_asked(self):
        s, n, other = caster_fight()
        with patch("game.roll_d20", return_value=19):
            result = s.run_player_turn("Hamle.", combat_action=fired(s, n, other, other))
        self.assertNotEqual(result["action_result"].get("outcome"), "surrendered_target")
        self.assertLess(other["current_hp"], 8)  # the readied blow landed (it may end the fight)
        self.assertEqual(n["current_hp"], 10)


if __name__ == "__main__":
    unittest.main()
