"""D-217 (and D-187): a turn-economy step that ends the fight says so on its receipt.

Before the fix the action_economy receipt carried no `combat_ended`/`end_reason`, so the UI notice, the aftermath offer
and the director's combat count (`adventure/play.py` `_refresh_from_turn`, `_note_played_category`) all missed a fight
the economy itself had ended. Fixed session seed (`scene()`, seed 11); the d20 is patched so the blow lands."""
from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

from api.tests.test_action_economy_end_turn import opponents
from api.tests.test_campaign_time import scene


def last_foe_standing():
    session = scene()
    npcs = opponents(session)
    for npc in npcs[1:]:
        npc.update(current_hp=0, combat_status="dead")
    session._sync_combat_participant_records(session.world_state["combat"])
    npcs[0]["current_hp"] = 1
    if not session.find_weapon_in_inventory("Kılıç")[0]:
        session.world_state["inventory"].append({"name": "Kılıç"})
    return session, npcs[0]


def strike(session, foe):
    with patch("game.roll_d20", return_value=18):
        return session.run_player_turn("Saldırırım.", action_id=str(uuid4()),
                                       combat_action={"steps": [{"kind": "attack", "target_id": foe["id"]}]})


class EconomyReceiptCarriesTheEnding(unittest.TestCase):
    def test_the_blow_that_ends_the_fight_marks_the_receipt(self):
        session, foe = last_foe_standing()
        combat_id = session.world_state["combat"]["combat_id"]
        result = strike(session, foe)
        self.assertFalse(session.world_state["combat"]["active"])
        receipt = result["action_result"]
        self.assertEqual(receipt["action"], "action_economy")
        self.assertIs(receipt["combat_ended"], True)
        self.assertEqual(receipt["end_reason"], "target_defeated")
        self.assertEqual(receipt["combat_id"], combat_id)

    def test_the_adventure_hooks_count_the_fight(self):
        session, foe = last_foe_standing()
        with patch("adventure.play._offer") as offer:
            strike(session, foe)
        self.assertIn("combat", session.world_state.get("adventure_recent_categories", []))
        self.assertEqual([call.kwargs["reason"] for call in offer.call_args_list].count("aftermath"), 1)

    def test_a_step_that_leaves_the_fight_running_claims_no_ending(self):
        session, foe = last_foe_standing()
        foe["current_hp"] = 100
        with patch("adventure.play._offer") as offer:
            result = strike(session, foe)
        self.assertNotIn("aftermath", [call.kwargs["reason"] for call in offer.call_args_list])
        self.assertTrue(session.world_state["combat"]["active"])
        self.assertNotIn("combat_ended", result["action_result"])
        self.assertNotIn("end_reason", result["action_result"])


if __name__ == "__main__":
    unittest.main()
