"""Speech and narration get the real place in plain words, and a stage direction stays in it."""

from __future__ import annotations

import json
import unittest
import uuid

import game
import living_world
from api.tests import test_campaign_api
from api.tests import test_dialogue_runtime as free
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_free_attempts import NarratingClient


class StagingClient(NarratingClient):
    def __init__(self, stage, **kwargs):
        super().__init__(**kwargs)
        self.stage = stage

    def chat(self, *args, **kwargs):
        answer = super().chat(*args, **kwargs)
        if self.kinds[-1] == "speech":
            body = json.loads(answer["message"]["content"])
            body["stage_direction"] = self.stage
            answer = {"message": {"content": json.dumps(body, ensure_ascii=False)}}
        return answer


class StageDirectionTests(unittest.TestCase):
    def street(self, **extra):
        return {
            "location": "city",
            "locations": {"city": {"id": "city", "name": "Neverwinter", "type": "city", "description": ""}},
            "features": [], "npcs": [{"id": "n", "name": "Mira", "role": "Kent sakini", "location": "city"}],
            **extra,
        }

    def test_a_counter_on_the_street_leaves_the_stage_direction(self):
        self.assertEqual(game._shown_stage_direction("Tezgâhın arkasında duruyor.", self.street()), "")

    def test_only_the_unsupported_sentence_goes(self):
        shown = game._shown_stage_direction(
            "Masanın kenarına yaslanıyor. Başını hafifçe sallıyor.", self.street()
        )
        self.assertEqual(shown, "Başını hafifçe sallıyor.")

    def test_a_plain_gesture_stays(self):
        self.assertEqual(game._shown_stage_direction("Omuz silkiyor.", self.street()), "Omuz silkiyor.")

    def test_a_word_that_only_looks_like_a_room_stays(self):
        self.assertEqual(
            game._shown_stage_direction("Bir masal anlatır gibi odaklanıyor.", self.street()),
            "Bir masal anlatır gibi odaklanıyor.",
        )

    def test_a_stall_keeper_on_the_street_keeps_the_counter(self):
        world = self.street()
        world["npcs"][0]["role"] = "Tüccar"
        self.assertEqual(game._shown_stage_direction("Tezgâhına yaslanıyor.", world), "Tezgâhına yaslanıyor.")

    def test_a_recorded_table_stays(self):
        world = self.street(features=[{"location": "city", "name": "Taş masa", "description": ""}])
        self.assertEqual(game._shown_stage_direction("Masaya yaslanıyor.", world), "Masaya yaslanıyor.")

    def test_inside_an_inn_the_counter_stays(self):
        world = self.street()
        world["locations"]["city"]["scene_kind"] = "tavern"
        self.assertEqual(game._shown_stage_direction("Tezgâhın arkasında duruyor.", world), "Tezgâhın arkasında duruyor.")


class PlainPlaceWordsTests(unittest.TestCase):
    def test_the_street_is_said_outright(self):
        world = {"location": "c", "locations": {"c": {"name": "Neverwinter", "type": "city"}}}
        words = living_world.place_in_plain_words(world)
        self.assertIn("Neverwinter sokaklarında", words)
        self.assertIn("açık havada", words)
        self.assertIn("tezgâh", words)

    def test_an_inn_is_said_as_inside(self):
        world = {"location": "t", "locations": {"t": {"name": "Wystan Hanı", "scene_kind": "tavern"}}}
        words = living_world.place_in_plain_words(world)
        self.assertIn("Wystan Hanı içinde", words)
        self.assertNotIn("sokak", words)

    def test_the_scene_facts_carry_it_for_every_speech_route(self):
        world = {"location": "c", "locations": {"c": {"name": "Neverwinter", "type": "city"}},
                 "features": [], "npcs": []}
        self.assertIn("sokaklarında", living_world.visible_scene_facts(world)["where_now"])


class PlaceInPromptTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def play(self, client, message, **extra):
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, self.turn_url, client, {"message": message, "action_id": str(uuid.uuid4()), **extra},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_speech_on_the_street_is_told_the_place_and_loses_the_counter(self):
        _, _, self.session, self.turn_url, self.npc = await self.campaign_with_npc()
        self.npc["name_known_to_player"] = True
        client = StagingClient("Tezgâhın arkasında duruyor.", spoken="Selam sana.")
        shown = (await self.play(client, "Selam, nasılsın?", interaction_mode="say", target_id=self.npc["id"]))["narration"]
        self.assertIn("speech", client.kinds)
        self.assertIn("Selam sana.", shown)
        self.assertNotIn("Tezgâh", shown)
        batch = client.batches[client.kinds.index("speech")]
        self.assertIn("sokaklarında", json.dumps(batch, ensure_ascii=False))

    async def test_narration_is_told_the_place(self):
        _, _, self.session, self.turn_url, _ = await self.campaign_with_npc(experimental=False)
        client = NarratingClient()
        await self.play(client, "Yüksek sesle bir şarkı söylüyorum.")
        batch = client.batches[client.kinds.index("narration")]
        self.assertIn("sokaklarında", json.dumps(batch, ensure_ascii=False))


class FreeSpeechPlaceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = free.DialogueRuntimeTests.asyncSetUp
    asyncTearDown = free.DialogueRuntimeTests.asyncTearDown
    setup_free = free.DialogueRuntimeTests.setup_free
    send = free.DialogueRuntimeTests.send

    async def test_the_free_route_drops_the_counter_too(self):
        await self.setup_free()
        self.npc["role"] = "resident"
        self.world["locations"][self.world["location"]].pop("scene_kind", None)
        self.reply.raw = json.dumps({
            "spoken_text": "Selam.", "stage_direction": "Tezgâhın arkasında duruyor.",
            "place_proposals": [], "job_proposals": [],
        }, ensure_ascii=False)
        response = await self.send("Selam.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("Tezgâh", response.json()["narration"])


if __name__ == "__main__":
    unittest.main()
