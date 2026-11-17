"""BM Task 6: the NPC speech call knows the hour, the arrival scene the player was shown, its own work and its last
lines (play findings B4, B5, B6 and the repeated stock lines). The arrival text is saved state: Undo and a reload keep it.

Real app, real adapter, real engine; only the Ollama client is scripted. New campaigns pin the town."""

from __future__ import annotations

import copy
import json
import os
import unittest
import uuid
from unittest.mock import patch

import campaign_time
import talk_front
import town_knowledge
import world_threads
from api.tests import test_arrival_wiring as arrival_tests
from api.tests import test_experimental_npc_dialogue as speech
from api.tests import test_front_proposal as fp
from api.tests import test_thread_gate as gate_tests

MARKER = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
SCENE = "Çizelgede bir isim karalanmış, mürekkep hâlâ taze."


class SpeechExtrasUnit(unittest.TestCase):
    """The function on its own, on small hand-made worlds."""

    def world(self, **extra):
        world = {"location": "place_a", "scene_state": {"arrival_text": None}, "npcs": [], "locations": {}}
        world.update(extra)
        return world

    def test_no_clock_no_time(self):
        self.assertNotIn("zaman", talk_front.speech_extras(self.world(), {"id": "n1"}))

    def test_time_words_follow_the_clock(self):
        with patch.object(campaign_time, "public_time",
                          return_value={"day_index": 3, "hour": 17, "minute": 10, "time_of_day": "evening"}):
            self.assertEqual(talk_front.speech_extras(self.world(), {"id": "n1"})["zaman"],
                             {"gun": 3, "vakit": "akşam", "saat": "17:10"})

    def test_arrival_text_only_at_its_own_place_and_capped(self):
        long_text = "Bir cümle daha geliyor. " * 60
        world = self.world(scene_state={"arrival_text": {"place_id": "place_a", "text": long_text, "turn": 4}})
        scene = talk_front.speech_extras(world, {"id": "n1"})["sahne_anlatimi"]
        self.assertTrue(0 < len(scene) <= 600)
        world["location"] = "place_b"
        self.assertNotIn("sahne_anlatimi", talk_front.speech_extras(world, {"id": "n1"}))

    def test_a_broken_arrival_entry_is_ignored(self):
        for broken in ("x", {"place_id": "place_a"}, {"place_id": "place_a", "text": 5, "turn": 1}, {"text": "a"}):
            world = self.world(scene_state={"arrival_text": broken})
            self.assertNotIn("sahne_anlatimi", talk_front.speech_extras(world, {"id": "n1"}))
        self.assertNotIn("sahne_anlatimi", talk_front.speech_extras({"location": "p"}, {"id": "n1"}))

    def test_last_lines_are_three_newest_last(self):
        log = {"n1": [{"player": f"s{i}", "npc": f"cevap {i}"} for i in range(4)]}
        extras = talk_front.speech_extras(self.world(npc_speech_log=log), {"id": "n1"})
        self.assertEqual(extras["son_sozlerin"], ["cevap 1", "cevap 2", "cevap 3"])
        self.assertNotIn("son_sozlerin", talk_front.speech_extras(self.world(), {"id": "n1"}))


class SceneTimeTable(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    open_job = gate_tests.ThreadTable.open_job
    line = gate_tests.ThreadTable.line
    begin = fp.FrontTable.begin
    routes = fp.FrontTable.routes

    async def say(self, message="Burada neler oluyor?", reply="Pek bir şey yok, yolcu.", *, front_on=True):
        """One line to the person; returns the speech prompt the model saw. Flag off: the old chain, same context."""
        if not front_on:
            os.environ["AI_DND_FRONT_PROPOSAL"] = "0"
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "asks": "rumour", "about_person_id": "none"}
        before = len(self.client.message_batches)
        await self.line(message, reply, mode="say", target=True)
        prompts = [user for batch in self.client.message_batches[before:] for user in
                   [next((m["content"] for m in reversed(batch) if m.get("role") == "user"), "")] if MARKER in user]
        self.assertTrue(prompts)
        return prompts[-1]  # the speech call is the last; the front reading before it carries the same marker

    def context_of(self, prompt):
        return json.JSONDecoder().raw_decode(prompt.split(MARKER, 1)[1].lstrip())[0]

    async def at(self, hour, minute):
        self.world["campaign_time"] = {**self.world["campaign_time"], "start_second": hour * 3600 + minute * 60,
                                        "elapsed_seconds": 0}

    async def test_speech_prompt_has_evening_time(self):
        await self.begin()
        await self.at(17, 10)
        prompt = await self.say()
        zaman = self.context_of(prompt)["zaman"]
        self.assertEqual((zaman["vakit"], zaman["saat"][:5]), ("akşam", "17:10"), zaman)
        self.assertIn("17:10", prompt)
        self.assertIn('"vakit":"akşam"', prompt)
        self.assertIn("saate uydur", prompt)

    async def test_speech_prompt_has_evening_time_with_the_flag_off(self):
        await self.begin()
        await self.at(17, 10)
        prompt = await self.say(front_on=False)
        self.assertEqual(self.context_of(prompt)["zaman"]["vakit"], "akşam")

    async def test_speech_prompt_has_arrival_scene(self):
        await self.begin()
        self.world["scene_state"]["arrival_text"] = {"place_id": self.world["location"], "text": SCENE, "turn": 1}
        prompt = await self.say()
        self.assertEqual(self.context_of(prompt)["sahne_anlatimi"], SCENE)
        self.assertIn("inkâr etme", prompt)
        self.world["scene_state"]["arrival_text"]["place_id"] = "somewhere_else"
        later = await self.say("Peki ya sonra?")
        self.assertNotIn("sahne_anlatimi", self.context_of(later))
        self.assertNotIn(SCENE, later)

    async def test_speech_prompt_has_own_work(self):
        await self.begin(kind="hiring")
        self.thread["status"] = "offered"
        prompt = await self.say("Bugün sana iş var mı?")
        self.assertEqual(self.context_of(prompt)["kendi_isin"], self.thread["public_line"])

    async def test_a_closed_job_is_not_own_work(self):
        await self.begin(kind="hiring")
        self.thread["status"] = "declined"
        self.assertNotIn("kendi_isin", self.context_of(await self.say("Bugün sana iş var mı?")))

    async def test_speech_prompt_has_own_spoken_rumour(self):
        await self.begin()
        settlement = town_knowledge._settlement(self.world)
        self.world["heard_rumours"] = [{"id": "r1", "settlement_id": settlement, "text": "Değirmende bir şeyler dönüyor.",
                                        "place_id": None, "speakers": [self.npc["id"]], "said_by": self.npc["id"]}]
        self.assertIn("Değirmende bir şeyler dönüyor.", self.context_of(await self.say())["kendi_sozlerin"])

    async def test_speech_prompt_has_last_lines(self):
        await self.begin()
        await self.say("Birinci soru?", "Birinci cevap, yolcu.")
        await self.say("İkinci soru?", "İkinci cevap, yolcu.")
        third = self.context_of(await self.say("Üçüncü soru?", "Üçüncü cevap."))
        self.assertEqual(third["son_sozlerin"], ["Birinci cevap, yolcu.", "İkinci cevap, yolcu."])
        self.assertIn("aynı reddi ya da bahaneyi", (await self.say("Dördüncü?", "Dördüncü.")))

    async def test_the_closed_mouthed_line_says_the_excuse_once(self):
        await self.begin()
        with patch.object(town_knowledge, "is_closed_mouthed", return_value=True):
            note = town_knowledge.speech_note(self.world, self.npc)
        self.assertIn("bir kez", note)


class ArrivalTextStored(arrival_tests._ArrivalApi):
    TOWN_SEED = 4411  # no smithy in this town: the walk makes one

    async def undo(self, target):
        reply = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                     json={"action_id": str(uuid.uuid4()), "target_action_id": target})
        self.assertEqual(reply.status_code, 200, reply.text)

    def stored(self):
        return copy.deepcopy(self.session().world_state["scene_state"].get("arrival_text"))

    async def test_arrival_stores_the_shown_text(self):
        self.assertIsNone(self.stored())
        reply = await self.turn("demirhaneye gidiyorum", arrival=SCENE)
        shown = reply.json()["narration"]
        stored = self.stored()
        self.assertEqual(stored["place_id"], self.session().world_state["location"])
        self.assertEqual(stored["text"], shown.strip())
        self.assertIn(SCENE, stored["text"])
        self.assertEqual(stored["turn"], self.session().world_state["flags"]["turn_index"])

    async def test_a_python_arrival_is_stored_too(self):
        await self.turn("demirhaneye gidiyorum", arrival=RuntimeError("down"))
        self.assertEqual(self.stored()["text"], self.last_result()["narration"].strip())

    async def test_undo_drops_arrival_text(self):
        earlier = self.stored()
        action_id = str(uuid.uuid4())
        await self.turn("demirhaneye gidiyorum", arrival=SCENE, action_id=action_id)
        self.assertNotEqual(self.stored(), earlier)
        await self.undo(action_id)
        self.assertEqual(self.stored(), earlier)

    async def test_undo_restores_the_older_arrival_not_none(self):
        await self.turn("demirhaneye gidiyorum", arrival=SCENE)
        first = self.stored()
        action_id = str(uuid.uuid4())
        await self.turn("meyhaneye gidiyorum", arrival="Başka bir sahne.", action_id=action_id)
        if self.stored() == first:
            self.skipTest("the second walk made no arrival in this town")
        await self.undo(action_id)
        self.assertEqual(self.stored(), first)

    async def test_save_load_keeps_arrival_text(self):
        await self.turn("demirhaneye gidiyorum", arrival=SCENE)
        stored = self.stored()
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager
        from api.tests.auth_fixture import TEST_PLAYER
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        fresh_id, *_ = fresh.resume_campaign(self.campaign_id)
        self.assertEqual(fresh.get(fresh_id).game_session.world_state["scene_state"]["arrival_text"], stored)


if __name__ == "__main__":
    unittest.main()
