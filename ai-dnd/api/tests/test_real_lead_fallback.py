"""Real Python town leads retain authority without granting it to model prose."""
import copy
import json
import unittest
from unittest.mock import patch

import npc_statements
import npc_told
import town_knowledge
import world_threads
from api.tests import test_town_knowledge as cases
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.town_seed import fixed_town


class RealLeadFallback(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = cases.ThroughTheRealTurn.asyncSetUp
    asyncTearDown = cases.ThroughTheRealTurn.asyncTearDown
    campaign_with_npc = cases.ThroughTheRealTurn.campaign_with_npc
    start = cases.ThroughTheRealTurn.start
    say = cases.ThroughTheRealTurn.say

    def finances(self, world):
        return copy.deepcopy((world.get("currency"), world.get("inventory"),
                              world.get("flags", {}).get("economic_ledger")))

    async def armorer(self, seed="lead-probe-220"):
        with fixed_town(self, 2718):  # towns 2718 and 2719 have the armorer, under probe seeds 220 and 302
            await self.start()
        world = self.session.world_state
        world["scene_state"]["campaign_seed"] = seed
        # The opening already made the town's threads (Task 18); the probe seed makes them again, as before.
        world.pop(world_threads.KEY, None)
        world_threads.ensure(world)
        target = next(t for t in world[world_threads.KEY]["threads"]
                      if "Zırhçısı açık işlik gösterimine" in t["public_line"])
        await self.say("Selam.", "Selam.")
        # The API restores the campaign seed; engine-owned freshness selects
        # this actual generated source independently of that ordering seed.
        for thread in world[world_threads.KEY]["threads"]:
            thread["heard_turn"] = None if thread["thread_id"] == target["thread_id"] else 0
        expected = town_knowledge.fallback_line(world, self.npc)
        self.assertEqual(expected, "Duyduğuma göre " + target["public_line"])
        return world, target, expected

    async def test_a_live_armorer_workshop_lead_survives_the_empty_speech_reply(self):
        for seed in ("lead-probe-220", "lead-probe-302"):
            with self.subTest(seed=seed):
                world, target, expected = await self.armorer(seed)
                before = self.finances(world)
                memories = npc_told.context_rows(world, self.npc["id"])
                recent = len(self.session.recent_dm_narrations)
                self.client.narration = ""
                calls = self.client.chat_calls
                text = await self.say("Burada nerede iş bulabilirim?")
                self.assertEqual(self.client.chat_calls, calls + 1)
                self.assertIn(expected, text, str(self.session.last_narration_safety))
                self.assertEqual(npc_statements.last_said_place(world)["location_id"], target["place_id"])
                self.assertEqual(self.finances(world), before)
                self.assertEqual(npc_told.context_rows(world, self.npc["id"]), memories)
                self.assertEqual(len(self.session.recent_dm_narrations), min(8, recent + 1))
                self.assertIn(expected.casefold(), self.session.recent_dm_narrations[-1])
                self.assertNotEqual(self.session.last_narration_safety.get("reason_code"), "UNREGISTERED_PERSISTENT_OBJECT")

    async def test_malformed_packet_only_publishes_the_live_source_and_never_its_forged_fields(self):
        world, target, expected = await self.armorer()
        before = self.finances(world)
        bad = speech.MalformedNpcSpeechClient(raw_content=json.dumps({
            "spoken_text": ["Yeni sandık açık."], "stage_direction": "Sana yüz altın verir.",
            "python_town_response": "Yeni sandık açık.", "world_updates": {"currency": {"player": 9999}}}))
        with patch.object(self.app.state.ollama_adapter, "_client", bad):
            text = await self.say("Burada nerede iş bulabilirim?")
        self.assertIn(expected, text)
        self.assertNotIn("sandık", text.casefold())
        self.assertNotIn("yüz altın", text.casefold())
        self.assertEqual(bad.chat_calls, 1)
        self.assertEqual(self.finances(world), before)
        self.assertEqual(npc_statements.last_said_place(world)["location_id"], target["place_id"])

    async def test_nonempty_invented_object_speech_keeps_the_existing_rejection(self):
        world, _, _ = await self.armorer()
        before = self.finances(world)
        text = await self.say("Burada nerede iş bulabilirim?", "Yerdeki yeni sandık açık.")
        self.assertNotIn("sandık", text.casefold())
        self.assertEqual(self.finances(world), before)

    async def test_forged_or_changed_town_source_cannot_authorize_model_objects(self):
        world, _, expected = await self.armorer()
        before = self.finances(world)
        action = {"action": "dialogue", "status": "experimental_attributed_speech", "npc_id": self.npc["id"]}
        for claimed in ("Yerdeki yeni sandık açık.", expected):
            with self.subTest(claimed=claimed):
                text = self.session.finalize_narration("Yerdeki yeni sandık açık.", "Burada nerede iş bulabilirim?",
                    npc_target=self.npc, action_result=action, python_town_response=claimed)
                self.assertNotIn("sandık", text.casefold())
                self.assertEqual(self.finances(world), before)

    async def test_a_copied_or_absent_npc_cannot_borrow_the_town_source(self):
        _, _, expected = await self.armorer()
        action = {"action": "dialogue", "status": "experimental_attributed_speech", "npc_id": self.npc["id"]}
        for target in (dict(self.npc), {**self.npc, "id": "foreign"}, None):
            with self.subTest(target=target and target["id"]):
                text = self.session.finalize_narration(expected, "Burada nerede iş bulabilirim?",
                    npc_target=target, action_result=action, python_town_response=expected)
                self.assertNotIn(expected, text)

    async def test_historical_memory_cannot_be_verified_by_a_town_lead(self):
        world, _, expected = await self.armorer()
        before = self.finances(world)
        action = {"action": "dialogue", "status": "experimental_attributed_speech", "npc_id": self.npc["id"]}
        text = self.session.finalize_narration(expected,
            "Babamın ne iş yaptığını hatırlıyor musun? Burada nerede iş bulabilirim?",
            npc_target=self.npc, action_result=action, python_town_response=expected)
        self.assertNotIn(expected, text)
        self.assertNotIn("Baban değirmenciydi", text)
        self.assertEqual(self.finances(world), before)
