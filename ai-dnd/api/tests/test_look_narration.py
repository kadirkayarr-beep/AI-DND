"""A first look is told by the narrator from Python's facts; a repeat stays short."""

from __future__ import annotations

import copy
import unittest
import uuid

import living_world
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_free_attempts import NarratingClient
from api.tests.town_seed import fixed_town

LOOK = "Çevremi gözlemliyorum."


class FailingNarrator(NarratingClient):
    def chat(self, *args, **kwargs):
        if "narration" in ((kwargs.get("format") or {}).get("properties", {})):
            self.kinds.append("narration")
            raise RuntimeError("model down")
        return super().chat(*args, **kwargs)


class LookNarrationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def scene(self):
        with fixed_town(self, 4569):
            _, _, self.session, self.turn_url, self.npc = await self.campaign_with_npc(experimental=False)
        self.npc["appearance"] = "Elindeki defteri karıştırıyor."
        self.npc["name_known_to_player"] = True
        self.world = self.session.world_state

    async def look(self, client, message=LOOK):
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, self.turn_url, client, {"message": message, "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["narration"]

    async def test_a_first_look_is_narrated_once_from_the_engine_facts(self):
        await self.scene()
        client = NarratingClient(narration="Marek defterini karıştırıyor, sokak akıp gidiyor.")
        shown = await self.look(client)
        self.assertEqual(client.kinds.count("narration"), 1)
        self.assertTrue(shown.startswith("Marek defterini karıştırıyor, sokak akıp gidiyor."))
        prompt = client.batches[client.kinds.index("narration")][1]["content"]
        self.assertIn("Elindeki defteri karıştırıyor.", prompt)

    async def test_a_repeat_at_an_unchanged_scene_makes_no_call(self):
        await self.scene()
        await self.look(NarratingClient(narration="Marek defterini karıştırıyor."))
        client = NarratingClient(narration="Bu metin görünmemeli.")
        shown = await self.look(client)
        self.assertEqual(client.kinds.count("narration"), 0)
        self.assertNotIn("Bu metin", shown)
        self.assertIn("Marek", shown)

    async def test_a_changed_scene_is_narrated_again(self):
        await self.scene()
        await self.look(NarratingClient(narration="Marek defterini karıştırıyor."))
        newcomer = copy.deepcopy(self.npc)
        newcomer.update(id="npc_look_sera", name="Sera")
        self.world["npcs"].append(newcomer)
        client = NarratingClient(narration="Marek ve Sera yan yana duruyor.")
        await self.look(client)
        self.assertEqual(client.kinds.count("narration"), 1)

    async def test_a_model_failure_keeps_the_engine_text(self):
        await self.scene()
        # The street draw may add people, and a crowd is named without appearances; this checks one person's line.
        for npc in self.world["npcs"]:
            if npc["id"] != self.npc["id"]:
                npc["hidden"] = True
        client = FailingNarrator()
        shown = await self.look(client)
        self.assertEqual(client.kinds.count("narration"), 1)
        self.assertIn("Marek", shown)
        self.assertIn("Elindeki defteri karıştırıyor.", shown)

    async def test_the_same_people_stay_in_the_scene(self):
        await self.scene()
        engine = FailingNarrator()
        shown = await self.look(engine)
        people = [npc["id"] for npc in self.world["npcs"] if npc.get("location") == self.world["location"]]
        self.world["flags"].pop("last_look_scene")
        client = NarratingClient(narration="Çevrene bakıyorsun, sokak sakin akıyor.")
        retold = await self.look(client)
        self.assertEqual(client.kinds.count("narration"), 1)
        self.assertIn("sokak sakin", retold)
        self.assertIn(living_world.public_npc_name(self.npc), retold)
        self.assertIn(living_world.public_npc_name(self.npc), shown)
        self.assertEqual(
            [npc["id"] for npc in self.world["npcs"] if npc.get("location") == self.world["location"]], people,
        )

    async def test_the_first_look_writes_no_world_fact(self):
        await self.scene()
        before = {key: copy.deepcopy(self.world.get(key)) for key in ("location", "inventory", "gold", "doors")}
        await self.look(NarratingClient(narration="Marek defterini karıştırıyor."))
        self.assertEqual(before, {key: self.world.get(key) for key in before})


if __name__ == "__main__":
    unittest.main()
