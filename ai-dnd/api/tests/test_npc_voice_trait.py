"""People keep a small seeded public voice; narration never writes the player's feelings."""
import json
import unittest
import uuid
from unittest.mock import patch

import game
import living_world
import local_dialogue
from api.tests import test_campaign_api as api
from api.tests import test_dialogue_runtime as free
from api.tests.test_route_focus_regressions import SchemaClient
from api.tests.test_stage10a_gameplay_repairs import city_session


def seeded_world(seed):
    return {"scene_state": {"campaign_seed": seed}}


class VoiceTraitTests(unittest.TestCase):
    def test_trait_comes_from_the_seed_and_reading_changes_nothing(self):
        npc = {"id": "npc_001"}
        first = local_dialogue.voice_trait(seeded_world("a"), npc)
        self.assertEqual(npc, {"id": "npc_001"})
        self.assertEqual(local_dialogue.voice_trait(seeded_world("a"), npc), first)

    def test_a_stored_trait_wins(self):
        npc = {"id": "npc_001", "voice_trait": "Saklı ses."}
        self.assertEqual(local_dialogue.voice_trait(seeded_world("a"), npc), "Saklı ses.")

    def test_people_sound_different_and_not_everyone_is_helpful(self):
        traits = {
            local_dialogue.voice_trait(seeded_world(f"s{i}"), {"id": "npc_001"})
            for i in range(40)
        }
        self.assertGreaterEqual(len(traits), 6)
        joined = " ".join(traits).casefold()
        self.assertIn("kısa", joined)
        self.assertIn("sıcak", joined)
        self.assertIn("yardım", joined)

    def test_new_person_is_stored_with_a_trait(self):
        session = city_session()
        token = game._ACTIVE_SESSION.set(session)
        try:
            npc = game.create_npc_from_ai({
                "name": "Nera", "role": "Kent sakini", "location": session.world_state["location"],
                "appearance": "Sade giyimli.", "personality": "Sakin.", "relationship": "neutral",
            })
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertIn(npc["voice_trait"], local_dialogue.VOICE_TRAITS)


class SpeechUsesVoice(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown

    async def test_speech_prompt_carries_the_trait_and_the_human_touch_rule(self):
        city, _sid, session, url, _venue, _door = await api.create_city_with_locked_tavern(self)
        npc = {
            "id": "npc_voice_marek", "name": "Marek", "role": "resident", "location": city,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION", "name_known_to_player": True,
            "voice_trait": local_dialogue.VOICE_TRAITS[0],
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Kâtibim.", "current_activity": "Yazıyorum.",
                "origin": "Kuzeyliyim.", "reason_for_being_here": "İşim burada.",
            },
            "knowledge": [], "memory": [], "status": "active", "combat_status": "active",
            "current_hp": 12, "relationship": "neutral", "appearance": "", "personality": "",
        }
        session.world_state["npcs"].append(npc)
        seen = []
        client = SchemaClient(npc)
        chat = client.chat

        def capture(*args, **kwargs):
            if "spoken_text" in kwargs.get("format", {}).get("properties", {}):
                seen.append(json.dumps(kwargs["messages"], ensure_ascii=False))
            return chat(*args, **kwargs)

        client.chat = capture
        client.message = "Marek, burada ne yapıyorsun?"
        with patch.object(self.app.state.ollama_adapter, "_client", client):
            response = await self.http.post(url, json={
                "message": client.message, "action_id": str(uuid.uuid4()),
                "interaction_mode": "say", "target_id": npc["id"],
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(seen)
        self.assertIn(local_dialogue.VOICE_TRAITS[0], seen[-1])
        self.assertIn("insani", seen[-1])


class FreeRouteVoice(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = free.DialogueRuntimeTests.asyncSetUp
    asyncTearDown = free.DialogueRuntimeTests.asyncTearDown
    setup_free = free.DialogueRuntimeTests.setup_free
    send = free.DialogueRuntimeTests.send

    async def test_free_speech_prompt_carries_the_trait(self):
        await self.setup_free()
        self.npc["voice_trait"] = local_dialogue.VOICE_TRAITS[1]
        response = await self.send("Nasılsın?")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(local_dialogue.VOICE_TRAITS[1], json.dumps(self.reply.batches, ensure_ascii=False))


class PlayerFeelingTests(unittest.TestCase):
    def test_clause_and_as_if_feelings_are_caught(self):
        for text in (
            "Birkaç kişinin seni fark ettiğini hissediyorsun.",
            "Bir şeylerin ters gittiğini hissedersin.",
            "İzleniyormuş gibi hissediyorsun.",
        ):
            self.assertTrue(game._PLAYER_FEELING_RE.search(text), text)

    def test_a_plain_sensation_stays(self):
        self.assertIsNone(game._PLAYER_FEELING_RE.search("Yüzünde serin bir esinti hissediyorsun."))
