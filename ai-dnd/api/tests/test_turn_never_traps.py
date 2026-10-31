"""A player is answered in the world: no HTTP refusal, no stuck turn, no scene from elsewhere."""

from __future__ import annotations

import unittest
import uuid

import combat_lifecycle
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_free_attempts import NarratingClient


class NoTrapTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def scene(self):
        _, _, self.session, self.turn_url, self.npc = await self.campaign_with_npc(experimental=False)
        self.session.world_state["inventory"].append("Kılıç")
        for npc in self.session.world_state["npcs"]:
            self.session.ensure_npc_combat_stats(npc)

    async def play(self, message, client=None, **extra):
        return await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, self.turn_url, client or NarratingClient(),
            {"message": message, "action_id": str(uuid.uuid4()), **extra},
        )

    async def test_a_bare_attack_with_two_people_asks_in_the_world(self):
        await self.scene()
        response = await self.play("Saldırıyorum.")
        self.assertEqual(response.status_code, 200, response.text)
        shown = response.json()["narration"]
        self.assertIn("Kime saldırıyorsun?", shown)
        self.assertIn("Marek", shown)
        self.assertFalse(self.session.world_state["combat"].get("active"))

    async def test_an_attack_on_someone_absent_is_answered_in_the_world(self):
        await self.scene()
        response = await self.play("Gromm'a kılıcımla saldırıyorum.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Kime saldırıyorsun?", response.json()["narration"])

    async def test_the_person_being_talked_to_is_the_target_of_a_bare_attack(self):
        await self.scene()
        flags = self.session.world_state["flags"]
        flags["active_npc_id"] = flags["last_npc_id"] = self.npc["id"]
        flags["active_npc_until_turn"] = flags.get("turn_index", 0) + 5
        self.assertIsNone(combat_lifecycle.unbound_attack_reply(self.session, "Saldırıyorum."))

    async def test_a_forged_target_is_still_a_request_error(self):
        await self.scene()
        response = await self.play("Saldırıyorum.", target_id="npc_does_not_exist")
        self.assertEqual(response.status_code, 400, response.text)

    async def test_nothing_sticks_after_the_name_and_ending_the_conversation(self):
        await self.scene()
        self.npc["name_known_to_player"] = False
        flags = self.session.world_state["flags"]
        for message, mode in (
            ("Selamlar, ismin nedir?", "say"),
            ("Konuşmayı bitiriyorum.", "do"),
            ("Çevreme bakıyorum.", "do"),
            ("Konuşmayı bitiriyorum.", "do"),
            ("Marek'e selam veriyorum.", "do"),
            ("Konuşmayı bitiriyorum.", "do"),
            ("Marek'e kılıcımı gösteriyorum.", "do"),
            ("Saldırıyorum.", "do"),
        ):
            with self.subTest(message=message):
                extra = {"interaction_mode": mode, "target_id": self.npc["id"]} if mode == "say" else {"interaction_mode": mode}
                response = await self.play(message, **extra)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()["narration"].strip())
        self.assertNotEqual(flags.get("turn_index"), None)

    async def test_a_counter_is_not_described_on_the_street(self):
        await self.scene()
        client = NarratingClient(
            narration="Tezgâhın arkasındaki adam sana bakıyor. Sokakta kalabalık akıyor."
        )
        shown = (await self.play("Yan masadakilere yazı tura oynamayı teklif ediyorum.", client)).json()["narration"]
        self.assertNotIn("Tezgâh", shown)
        self.assertIn("Sokakta kalabalık akıyor.", shown)


if __name__ == "__main__":
    unittest.main()
