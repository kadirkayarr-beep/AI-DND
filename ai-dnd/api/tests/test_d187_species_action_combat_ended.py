"""D-187: a species action that ends the fight hands `combat_ended` to the adventure hooks.

The species-actions panel route feeds the quest owner its own before/after world (D-105), but its action result said
nothing about the fight ending. So when Inner Radiance dropped the last foe, `adventure/play.py` skipped the aftermath
offer (`_refresh_from_turn`) and the director's combat count (`_note_played_category`), which a play turn or an
economy step that ends the same fight both get. Fixed town seed (`fixed_town`, 10501); the radiance roll is patched.
"""
from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from api.tests import test_species_action_quest_evidence as d105


class SpeciesActionEndingTheFight(unittest.IsolatedAsyncioTestCase):
    # The D-105 fixture (app, fixed town, radiant Aasimar beside a bounty target), without re-running its own tests.
    asyncSetUp = d105.SpeciesActionQuestEvidenceTests.asyncSetUp
    asyncTearDown = d105.SpeciesActionQuestEvidenceTests.asyncTearDown
    radiant_aasimar_facing_the_bounty = d105.SpeciesActionQuestEvidenceTests.radiant_aasimar_facing_the_bounty

    async def heal_beside(self, target_hp):
        session_id, session, foe = await self.radiant_aasimar_facing_the_bounty(target_hp=target_hp)
        with patch.object(session.rng, "randint", return_value=1), patch("adventure.play._offer") as offer:
            response = await self.http.post(f"/api/game/sessions/{session_id}/species-actions",
                                            json={"action": "healing_hands", "action_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        return session, [call.kwargs["reason"] for call in offer.call_args_list]

    async def test_the_radiance_that_ends_the_fight_reaches_the_adventure_hooks(self):
        session, reasons = await self.heal_beside(target_hp=1)
        self.assertFalse(session.world_state["combat"]["active"], "the last foe fell, so the fight is over")
        self.assertEqual(reasons.count("aftermath"), 1)
        self.assertIn("combat", session.world_state.get("adventure_recent_categories", []))

    async def test_a_species_action_that_leaves_the_fight_running_claims_no_ending(self):
        session, reasons = await self.heal_beside(target_hp=50)
        self.assertTrue(session.world_state["combat"]["active"])
        self.assertNotIn("aftermath", reasons)
        self.assertNotIn("combat", session.world_state.get("adventure_recent_categories", []))


if __name__ == "__main__":
    unittest.main()
