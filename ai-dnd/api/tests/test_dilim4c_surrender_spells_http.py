"""Dilim 4C Task 4a part 1 (D-036) through HTTP: a Magic Missile button at a surrendered foe asks first, the model-free
"evet" casts it once at the asked foe, a replay of that answer casts nothing more, and Undo gives the slot back.

Harness: the C19 Quickened HTTP encounter (fixed street via CampaignApiTests.asyncSetUp, level-2 Sorcerer, guard 'Rakip'),
plus a second foe so the fight goes on after Rakip's accepted surrender."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import monster_combat
from api.tests import test_roadmap_c19_quickened_http as quickened_fixtures


class SurrenderedSpellHttp(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = quickened_fixtures.QuickenedHttpTests.asyncSetUp
    asyncTearDown = quickened_fixtures.QuickenedHttpTests.asyncTearDown
    create_campaign = quickened_fixtures.QuickenedHttpTests.create_campaign
    encounter = quickened_fixtures.QuickenedHttpTests.encounter
    post = quickened_fixtures.QuickenedHttpTests.post
    snapshot = quickened_fixtures.QuickenedHttpTests.snapshot

    async def surrendered(self):
        a, r, command = await self.encounter()
        s = r.game_session
        rakip = command["combat_action"]["steps"][0]["target_id"]
        other = s.create_npc_from_ai({"name": "Haydut", "role": "Guard", "location": "tavern"})
        other.update(current_hp=30, max_hp=30, armor_class=10, hostile=True, distance_ft=5,
                     attack_damage_type="bludgeoning")
        with patch("game.roll_initiative", return_value=1):
            s.join_combat_participants([other["id"]])
        cid = s.world_state["combat"]["combat_id"]
        monster_combat.state(s, rakip).setdefault("proposals", []).append(
            {"proposal_id": f"{cid}:1:{rakip}:0:SURRENDER_PROPOSED", "type": "SURRENDER_PROPOSED",
             "status": "accepted", "actor_id": rakip})
        s._sync_combat_participant_records(s.world_state["combat"])
        self.assertEqual(s.world_state["combat"]["current_actor_id"], "player")
        self.manager.save_campaign(a["campaign_id"])
        return a, r, command, rakip, other

    async def test_button_asks_then_model_free_yes_casts_once_replay_and_undo_hold(self):
        a, r, command, rakip, other = await self.surrendered()
        s = r.game_session
        npc = next(n for n in s.world_state["npcs"] if n["id"] == rakip)
        asked = await self.post(a, command)
        self.assertEqual(asked.status_code, 200, asked.text)
        self.assertIn("teslim olmuş birine saldırıyorsun", asked.json()["narration"])
        self.assertEqual({k: asked.json()["combat_result"][k] for k in ("status", "outcome", "target_id", "slot_spent")},
                         {"status": "clarification", "outcome": "surrendered_target", "target_id": rakip,
                          "slot_spent": None})
        self.assertEqual((s.world_state["spellcasting_v1"]["slots"]["1"], npc["current_hp"]), (3, 100))

        self.app.state.ollama_adapter = None  # answering the engine's own question needs no model
        yes = {"message": "evet", "action_id": str(uuid4()), "target_id": other["id"]}
        with patch("api.tests.test_campaign_api.FakeOllamaClient.chat",
                   side_effect=AssertionError("the answer called the model")) as chat, \
                patch.object(s.rng, "randint", return_value=4):
            cast = await self.post(a, yes)
        chat.assert_not_called()
        self.assertEqual(cast.status_code, 200, cast.text)
        self.assertEqual(cast.json()["combat_result"]["spell"], "Magic Missile")
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], 2)
        self.assertEqual(npc["current_hp"], 100 - 3 * 5)
        self.assertEqual(other["current_hp"], 30)

        before = self.snapshot(r)
        with patch("spell_scope.cast", side_effect=AssertionError("replay recast")):
            replay = await self.post(a, yes)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), cast.json())
        self.assertEqual(self.snapshot(r), before)

        undone = await self.http.post(f"/api/game/sessions/{a['session_id']}/undo",
                                      json={"action_id": str(uuid4()), "target_action_id": yes["action_id"]})
        self.assertEqual(undone.status_code, 200, undone.text)
        s = r.game_session
        npc = next(n for n in s.world_state["npcs"] if n["id"] == rakip)
        self.assertEqual((s.world_state["spellcasting_v1"]["slots"]["1"], npc["current_hp"]), (3, 100))
        again = await self.post(a, {**copy.deepcopy(command), "action_id": str(uuid4())})
        self.assertEqual(again.status_code, 200, again.text)
        self.assertIn("teslim olmuş birine saldırıyorsun", again.json()["narration"])  # asked again, never cast unasked
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], 3)


if __name__ == "__main__":
    unittest.main()
