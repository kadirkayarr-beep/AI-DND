"""Task 38: in a fight the player's words are the move made (H241, H123, H124, H131, H132, H239).

A blow asked about is the asked line's blow, never the weapon that happens to be in hand; a shove tells its save; going
on the defensive is Dodge; a readied reaction tells what it did; a fired crossbow at the one being fought rolls; a
long yes still answers the question. Real app, real engine; only the model client is scripted.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import action_economy
import equipment_economy
import game
from api.tests import test_combat_lifecycle as lifecycle
from api.tests import test_front_proposal as front_table
from api.tests.town_seed import fixed_town

CROSSBOW = "Ağır Tatar Yayı & 20 Ok"


class AskedBlowsAreTheAskedMove(unittest.IsolatedAsyncioTestCase):
    # FrontTable's harness without its own tests (a subclass would run them all again)
    asyncSetUp = front_table.FrontTable.asyncSetUp
    asyncTearDown = front_table.FrontTable.asyncTearDown
    campaign_with_npc = front_table.FrontTable.campaign_with_npc
    open_job = front_table.FrontTable.open_job
    line = front_table.FrontTable.line

    async def begin(self, **kwargs):
        with fixed_town(self, 3801):
            await front_table.FrontTable.begin(self, **kwargs)
        self.npc.update(armor_class=10, max_hp=40, current_hp=40)
        self.session.character.update(max_hp=300, current_hp=300)
        self.world["inventory"] = ["Greatsword", CROSSBOW, "Macera Çantası"]
        self.world["equipment"] = {"main_hand": None, "off_hand": None}
        equipment_economy.materialize(self.world)
        crossbow = next(item for item in self.world["inventory"] if item["name"] == CROSSBOW)
        self.world["equipment"]["main_hand"] = crossbow["item_id"]  # the crossbow is what is in hand (H241)

    def players_last_attack(self):
        return [row for row in self.world["attack_results"] if row["actor"] == "player"][-1]

    async def ask(self, line):
        self.client.front = {"kind": "attempt", "strike_to": self.npc["id"]}
        reply = await self.line(line, "Ne yapıyorsun sen?")
        self.assertEqual(reply["turn_outcome"]["status"], "clarification", reply["narration"])
        self.assertIn("kavga", reply["narration"])
        return reply

    async def test_a_long_yes_still_answers_the_question(self):
        # H239: 'Evet, iri yarı adamı itiyorum.' (five words) was lost and became talk.
        await self.begin()
        await self.ask("Marek'i itip yere devirmeye çalışıyorum")
        reply = await self.line("Evet, şu adamı sertçe itiyorum.")
        self.assertEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertEqual(reply["turn_outcome"]["target_name"], self.npc["name"])

    async def test_a_long_answer_that_takes_it_back_starts_nothing(self):
        await self.begin()
        await self.ask("Marek'i itip yere devirmeye çalışıyorum")
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        reply = await self.line("evet ama itmiyorum, sadece bakıyorum", "Peki.")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack", reply["narration"])
        self.assertFalse(self.world["combat"]["active"])

class TheFightsOwnMoves(unittest.TestCase):
    def fight(self):
        session, npc = lifecycle.ready()
        token = game._ACTIVE_SESSION.set(session)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)
        return session, npc

if __name__ == "__main__":
    unittest.main()
