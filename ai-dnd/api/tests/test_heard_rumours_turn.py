"""Rumour lane wiring: an NPC's optional `mentions` field in a speech turn, over HTTP, with undo and save/reload."""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

import httpx

import game
import heard_rumours
import local_dialogue
import local_places
from api import model_chain
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as fixtures
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.speech_double import routed_chat, speech_packet
from api.tests.test_world_threads import city
from api.tests.town_seed import fixed_town

SPOKEN = "Kuzeyde Eski Mahzen diye bir yer varmış, öyle duydum."
MENTION = {"kind": "place", "name": "Eski Mahzen", "place_kind": "archive", "about": "Kuyunun altında"}


class _Client:
    """Model boundary: answers the one speech call with a fixed packet and keeps the schema it was sent."""

    def __init__(self, mentions, spoken=SPOKEN):
        self.formats = []
        self.prompts = []

        def answer(kwargs):
            self.formats.append(copy.deepcopy(kwargs["format"]))
            self.prompts.append(json.dumps(kwargs.get("messages"), ensure_ascii=False))
            return speech_packet(spoken, "", mentions)

        self._chat = routed_chat({"speech": answer})

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        return self._chat(*args, **kwargs)


class MentionTurnFixture(unittest.IsolatedAsyncioTestCase):
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown

    async def asyncSetUp(self):
        await fixtures.CampaignApiTests.asyncSetUp(self)
        with fixed_town(self, 6240):
            created = await self.http.post("/api/game/campaigns", json={"campaign_start": {
                "setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}})
        self.assertEqual(created.status_code, 200, created.text)
        self.campaign = created.json()
        self.session_id = self.campaign["session_id"]
        self.campaign_id = self.campaign["campaign_id"]
        npc = {"id": "npc_t2_edric", "name": "Edric", "role": "Yolcu", "location": self.world["location"],
               "reality_layer": "PROCEDURAL_LOCAL_FICTION"}
        local_dialogue.ensure_personal_profile(npc)
        self.world["npcs"].append(npc)

    @property
    def world(self):
        return self.manager.get(self.session_id).game_session.world_state

    def rumoured(self):
        return [r for r in self.world["locations"].values() if isinstance(r, dict) and r.get("rumoured")]

    async def say(self, mentions, action_id=None, spoken=SPOKEN):
        client = _Client(mentions, spoken)
        body = {"message": "Buralarda duyduğun bir şey var mı?", "action_id": action_id or str(uuid.uuid4()),
                "target_id": "npc_t2_edric", "interaction_mode": "say"}
        with patch.object(self.app.state.ollama_adapter, "_client", client):
            response = await self.http.post(f"/api/game/sessions/{self.session_id}/turn", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response, client, body["action_id"]


class MentionOverHttp(MentionTurnFixture):
    async def test_npc_mention_is_recorded_on_the_speech_turn(self):
        response, client, _ = await self.say(MENTION)
        self.assertIn(SPOKEN, response.json()["narration"])
        self.assertEqual(len(self.world["heard_rumours"]), 1)
        entry = self.world["heard_rumours"][0]
        self.assertEqual(entry["said_by"], "npc_t2_edric")
        place = self.world["locations"][entry["place_id"]]
        self.assertEqual((place["name"], place["rumoured"]), ("Eski Mahzen", True))
        self.assertEqual(len(self.rumoured()), 1)

    async def test_rejected_mention_shows_no_error(self):
        response, _, _ = await self.say({**MENTION, "place_kind": "dragon_lair"})
        narration = response.json()["narration"]
        self.assertIn(SPOKEN, narration)
        for word in ("hata", "geçersiz", "reddedil", "Error", "mentions"):
            self.assertNotIn(word, narration)
        self.assertEqual(self.world["heard_rumours"], [])
        self.assertEqual(self.rumoured(), [])

    async def test_name_not_said_aloud_records_nothing(self):
        response, _, _ = await self.say(MENTION, spoken="Kuzeyde bir yer varmış, öyle duydum.")
        self.assertIn("Kuzeyde bir yer varmış", response.json()["narration"])
        self.assertEqual(self.world["heard_rumours"], [])
        self.assertEqual(self.rumoured(), [])

    async def test_name_said_with_a_case_suffix_records_the_base_name(self):
        await self.say({**MENTION, "name": "Eski Mahzen'de"}, spoken="Eski Mahzen'de bir kuyu varmış, öyle duydum.")
        self.assertEqual([r["name"] for r in self.rumoured()], ["Eski Mahzen"])
        self.assertEqual(len(self.world["heard_rumours"]), 1)

    async def test_rule_line_is_absent_from_the_prompt_when_the_lane_is_off(self):
        _, on, _ = await self.say(None)
        self.assertIn(game._MENTIONS_PROMPT_RULE, on.prompts[0])
        with patch.dict("os.environ", {"AI_DND_RUMOUR_LANE": "0"}):
            _, off, _ = await self.say(None)
        self.assertNotIn(game._MENTIONS_PROMPT_RULE, off.prompts[0])
        self.assertIn("kind none", on.prompts[0])

    async def test_undo_removes_rumour_and_place(self):
        before = copy.deepcopy(self.world["locations"])
        _, _, action_id = await self.say(MENTION)
        self.assertEqual(len(self.world["heard_rumours"]), 1)
        undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": action_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.world["heard_rumours"], [])
        self.assertEqual(self.rumoured(), [])
        self.assertEqual(self.world["locations"], before)

    async def test_save_load_keeps_rumour_and_place(self):
        await self.say(MENTION)
        rumours = copy.deepcopy(self.world["heard_rumours"])
        place_id = rumours[0]["place_id"]
        place = copy.deepcopy(self.world["locations"][place_id])
        saved = await self.http.post(f"/api/game/campaigns/{self.campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        app = create_app(session_manager=manager, ollama_adapter=AuthenticatedOllamaAdapter(fixtures.FakeOllamaClient()),
                         authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http:
            resumed = await http.post(f"/api/game/campaigns/{self.campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            world = manager.get(resumed.json()["session_id"]).game_session.world_state
        self.assertEqual(world["heard_rumours"], rumours)
        self.assertEqual(world["locations"][place_id], place)

    async def test_lane_off_keeps_old_places_and_drops_schema_field(self):
        await self.say(MENTION)
        place_id = self.world["heard_rumours"][0]["place_id"]
        with patch.dict("os.environ", {"AI_DND_RUMOUR_LANE": "0"}):
            _, client, _ = await self.say({**MENTION, "name": "Kara Kuyu"})
        self.assertNotIn("mentions", client.formats[0]["properties"])
        self.assertEqual([e["place_id"] for e in self.world["heard_rumours"]], [place_id])
        self.assertEqual(len(self.rumoured()), 1)
        live = self.manager.get(self.session_id).game_session
        self.assertEqual(game.resolve_location_reference("Eski Mahzen", session=live), place_id)

    async def test_lane_on_sends_mentions_in_schema_with_place_kind_enum(self):
        _, client, _ = await self.say(None)
        schema = client.formats[0]
        mentions = schema["properties"]["mentions"]
        self.assertEqual(mentions["properties"]["place_kind"]["enum"], list(local_places.PLACE_KINDS))
        self.assertEqual(mentions["properties"]["kind"]["enum"], ["none", "place", "trail"])
        self.assertEqual(mentions["required"], ["kind", "name"])
        self.assertIn("mentions", schema["required"])
        shaped_schema = model_chain._haiku_schema(schema)  # the sent schema survives Haiku shaping
        self.assertIn("mentions", shaped_schema["required"])
        shaped = shaped_schema["properties"]["mentions"]
        self.assertEqual(shaped["properties"]["place_kind"]["enum"], list(local_places.PLACE_KINDS))
        self.assertEqual(shaped["properties"]["kind"]["enum"], ["none", "place", "trail"])

    async def test_lane_off_schema_has_no_mentions_in_required(self):
        with patch.dict("os.environ", {"AI_DND_RUMOUR_LANE": "0"}):
            _, client, _ = await self.say(None)
        self.assertNotIn("mentions", client.formats[0]["properties"])
        self.assertNotIn("mentions", client.formats[0]["required"])
        self.assertEqual(client.formats[0]["required"], ["spoken_text", "stage_direction", "threat"])

    async def test_kind_none_mention_records_nothing(self):
        response, _, _ = await self.say({"kind": "none", "name": ""})
        self.assertIn(SPOKEN, response.json()["narration"])
        self.assertEqual(self.world["heard_rumours"], [])
        self.assertEqual(self.rumoured(), [])

    async def test_packet_without_mentions_key_is_still_accepted(self):
        response, _, _ = await self.say(None)
        self.assertIn(SPOKEN, response.json()["narration"])
        self.assertEqual(self.world["heard_rumours"], [])


class MentionOffline(unittest.TestCase):
    def test_schema_passes_haiku_shaping(self):
        mentions = copy.deepcopy(game._EXPERIMENTAL_NPC_SPEECH_SCHEMA["properties"]["mentions"])
        mentions["properties"]["place_kind"]["enum"] = list(local_places.PLACE_KINDS)  # what the engine fills per turn
        schema = {"type": "object", "properties": {"mentions": mentions}}
        shaped = model_chain._haiku_schema(schema)["properties"]["mentions"]
        self.assertEqual(shaped["properties"]["kind"]["enum"], ["none", "place", "trail"])
        self.assertEqual(shaped["properties"]["place_kind"]["enum"], list(local_places.PLACE_KINDS))
        self.assertEqual(shaped["required"], ["kind", "name"])
        self.assertIs(shaped["additionalProperties"], False)

    def test_prompt_rule_text_is_exact(self):
        self.assertEqual(
            game._MENTIONS_PROMPT_RULE,
            "mentions: Konuşmada adını verdiğin bir yer ya da iz varsa onu yaz (kind place ya da trail, name tam ad, "
            "konuşmada geçtiği gibi); yer için türü listeden seç. Para, ödül, görev ya da eşya yazma. "
            "Adını verdiğin yer ya da iz yoksa kind none, name boş.")


class SubstringAliasDoesNotLink(unittest.TestCase):
    """resolve_location_reference may match an alias inside a longer text; a different place must not link to it."""

    def setUp(self):
        self.world = city("alias-substring")
        self.world["npcs"] = [{"id": "npc_001", "name": "Mira Dalgıç", "location": "city"}]
        patcher = patch.object(game._DEFAULT_SESSION, "world_state", self.world)
        patcher.start()
        self.addCleanup(patcher.stop)

    def mention(self, name, kind):
        return heard_rumours.record_mention(game, self.world, self.world["npcs"][0],
                                            {"kind": "place", "name": name, "place_kind": kind}, 1)

    def test_longer_name_containing_an_existing_name_is_a_new_place(self):
        smithy = local_places.create_local_place(self.world, "city", "smithy")
        entry = self.mention(f"{smithy['name']} Mezarlığı", "graveyard")
        self.assertIsNotNone(entry)
        self.assertNotEqual(entry["place_id"], smithy["id"])

    def test_shorter_name_inside_an_existing_name_is_a_new_place(self):
        smithy = local_places.create_local_place(self.world, "city", "smithy")
        entry = self.mention(smithy["name"].split()[0], "graveyard")
        self.assertIsNotNone(entry)
        self.assertNotEqual(entry["place_id"], smithy["id"])


class SpeechRulesFollowTheLane(unittest.TestCase):
    """Owner decision (2026-11-16): lane on, the speech rules no longer ban place names; person, job and fact bans stay."""

    def build(self, lane):
        session = game.create_session(seed=7)
        world = session.world_state
        world["npcs"] = [{"id": "barman", "name": "Marek", "role": "Barmen", "location": world["location"], "current_hp": 10}]
        with patch.dict("os.environ", {"AI_DND_RUMOUR_LANE": lane}):
            return game._experimental_speech_note(world, world["npcs"][0], None, "Selam", session=session)

    def test_lane_on_has_no_place_ban(self):
        note = self.build("1")
        self.assertNotIn("yer veya", note)
        self.assertNotIn("yeni ad uydurmadan", note)
        self.assertIn("yeni kişi ya da olgu uydurmadan", note)
        self.assertIn("yeni kişi ya da iş adı uydurmadan", note)

    def test_lane_off_keeps_the_old_text_exactly(self):
        note = self.build("0")
        self.assertIn("muhafız, pazar gibi; yeni ad uydurmadan)", note)
        self.assertIn("yeni kişi, yer veya olgu uydurmadan.", note)
        self.assertTrue(note.startswith(game._SPEECH_ANSWER_RULES))


if __name__ == "__main__":
    unittest.main()
