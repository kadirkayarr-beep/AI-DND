"""D-527: NPC memory holds only dict entries in a new campaign; the plain-string branches are gone."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import game
import local_dialogue
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.town_seed import fixed_town

TOWN_SEED = 4201


class NewCampaignWritesDictMemory(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def test_every_memory_entry_of_a_new_campaign_is_a_dict(self):
        self.enterContext(patch.dict(os.environ))
        with fixed_town(self, TOWN_SEED):
            _, _, session, _, marek = await self.campaign_with_npc(experimental=False)
        npc = next(n for n in session.world_state["npcs"] if n["id"] == marek["id"])
        game.record_npc_interaction(npc, "Hoş geldin, yolcu.", "Merhaba Marek", npc_target=npc)
        local_dialogue.remember_explicit_player_name(npc, "Carius")
        self.assertTrue(npc["memory"])
        for other in session.world_state["npcs"]:
            for entry in other.get("memory", []):
                self.assertIsInstance(entry, dict, other["id"])


class StringEntriesAreIgnored(unittest.TestCase):
    def test_a_plain_string_entry_is_not_formatted(self):
        self.assertEqual(game._format_npc_memory(["eski satır", {"speaker": "npc", "text": "Merhaba."}]),
                         ["[npc] Merhaba."])

    def test_a_plain_string_entry_never_supports_a_claim(self):
        npc = {"memory": ["Sana beş altın vereceğimi söylemiştim."]}
        self.assertIsNone(game.npc_memory_supporting_entry(npc, "Sen bana beş altın vereceğini söylemiştin."))


if __name__ == "__main__":
    unittest.main()
