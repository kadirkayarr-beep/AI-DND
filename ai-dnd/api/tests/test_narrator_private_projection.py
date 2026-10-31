"""Marked secrets stay out of every prompt sent to the model client on real turns."""
import json
import unittest
import uuid
from unittest.mock import patch

import dialogue_commitments
import game
import living_world
import local_dialogue
from api.tests import test_campaign_api as api
from api.tests import test_dialogue_runtime as free
from api.tests.test_route_focus_regressions import SchemaClient

SECRETS = {
    "immediate_goal": "SIRHEDEF7731",
    "personal_detail": "SIRDETAY7732",
    "recent_activity": "SIRGECMIS7733",
    "private_note": "SIREK7734",
    "tag": "SIRETIKET7735",
    "personality": "SIRKARAKTER7736",
    "shop_id": "SIRDUKKAN7737",
    "stranger_name": "SIRAD7738",
}


def profile():
    return {
        "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
        "occupation": "Kayıt tutuyorum.",
        "current_activity": "Kayıtlara bakıyorum.",
        "origin": "Kuzeyden geldim.",
        "reason_for_being_here": "İşim burada.",
        "immediate_goal": SECRETS["immediate_goal"],
        "personal_detail": SECRETS["personal_detail"],
        "recent_activity": SECRETS["recent_activity"],
        "private_note": SECRETS["private_note"],
        "mood": "sakin",
    }


def hidden_person(npc_id, location):
    return {
        "id": npc_id, "name": "Marek", "role": "shopkeeper", "location": location,
        "role_known_to_player": False, "name_known_to_player": True,
        "reality_layer": "PROCEDURAL_LOCAL_FICTION", "personal_profile": profile(),
        "tags": [SECRETS["tag"]], "personality": SECRETS["personality"],
        "shop_id": SECRETS["shop_id"], "knowledge": [], "memory": [], "status": "active",
        "combat_status": "active", "current_hp": 12, "relationship": "neutral", "appearance": "",
    }


def stranger(location):
    person = hidden_person("npc_secret_stranger", location)
    person.update(name=SECRETS["stranger_name"], name_known_to_player=False)
    return person


class CapturingClient(SchemaClient):
    def __init__(self, npc):
        super().__init__(npc)
        self.seen = []

    def chat(self, *args, **kwargs):
        properties = kwargs.get("format", {}).get("properties", {})
        kind = (
            "speech" if "spoken_text" in properties
            else "classifier" if "intent" in properties
            else "narration"
        )
        self.seen.append((kind, json.dumps(kwargs.get("messages"), ensure_ascii=False)))
        return super().chat(*args, **kwargs)


class LegacyRouteSecrets(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown

    async def prepare(self):
        city, _sid, session, url, _venue, door = await api.create_city_with_locked_tavern(self)
        npc = hidden_person("npc_secret_marek", city)
        session.world_state["npcs"].extend([npc, stranger(city)])
        self.session, self.url, self.npc, self.door = session, url, npc, door
        self.client = CapturingClient(npc)

    async def turn(self, text, mode="do", target=None):
        self.client.message = text
        body = {"message": text, "action_id": str(uuid.uuid4()), "interaction_mode": mode}
        if target:
            body["target_id"] = target
        with patch.object(self.app.state.ollama_adapter, "_client", self.client):
            response = await self.http.post(self.url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_no_marked_secret_in_any_prompt(self):
        await self.prepare()
        await self.turn("Çevreme bakıyorum.")
        await self.turn("Marek, burada ne yapıyorsun?", "say", self.npc["id"])
        await self.turn("Peki neden?", "say", self.npc["id"])
        await self.turn("Marek'e dikkatle bakıyorum.")
        await self.turn("Önümdeki adamın kesesine göz atıyorum.")
        kinds = {kind for kind, _ in self.client.seen}
        self.assertTrue({"speech", "classifier", "narration"} <= kinds, kinds)
        for kind, prompt in self.client.seen:
            for label, value in SECRETS.items():
                self.assertNotIn(value, prompt, f"{label} in {kind}")
            self.assertNotIn('"door_locked":true', prompt, kind)
            self.assertNotIn('"locked":true', prompt, kind)

    async def test_context_keeps_an_untested_lock_out_and_a_tested_one_in(self):
        await self.prepare()
        self.session.world_state["flags"].pop("known_locked_door_ids", None)
        token = game._ACTIVE_SESSION.set(self.session)
        try:
            with patch.object(game, "_current_door", return_value=self.door):
                self.assertNotIn("locked", game.build_world_context()["door"])
                self.session.world_state["flags"]["known_locked_door_ids"] = [self.door["id"]]
                self.assertTrue(game.build_world_context()["door"]["locked"])
        finally:
            game._ACTIVE_SESSION.reset(token)


class FreeRouteSecrets(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = free.DialogueRuntimeTests.asyncSetUp
    asyncTearDown = free.DialogueRuntimeTests.asyncTearDown
    setup_free = free.DialogueRuntimeTests.setup_free
    send = free.DialogueRuntimeTests.send

    async def test_free_speech_prompt_has_no_marked_secret(self):
        await self.setup_free()
        secret = hidden_person("npc_free_edric", self.world["location"])
        self.npc.clear()
        self.npc.update(secret)
        self.world["npcs"].append(stranger(self.world["location"]))
        response = await self.send("Burada ne yapıyorsun?")
        self.assertEqual(response.status_code, 200, response.text)
        prompt = json.dumps(self.reply.batches, ensure_ascii=False)
        for label, value in SECRETS.items():
            self.assertNotIn(value, prompt, label)
        self.assertIn("Kayıt tutuyorum.", prompt)


class ParcelTextHidesUnknownNames(unittest.TestCase):
    def test_recipient_phrase_uses_the_name_only_once_it_is_known(self):
        person = stranger("yer")
        self.assertNotIn(SECRETS["stranger_name"], living_world.public_recipient_phrase(person))
        person["name_known_to_player"] = True
        self.assertEqual(
            living_world.public_recipient_phrase(person),
            f"{SECRETS['stranger_name']} adlı kişiye",
        )

    def test_job_card_objective_keeps_an_unknown_recipient_unnamed(self):
        person = stranger("yer")
        world = {"npcs": [person], "locations": {"yer": {"name": "Pazar"}}}
        quest = {
            "quest_id": "q", "title": "Paket", "status": "DISCOVERED",
            "template_id": "DELIVERY",
            "bindings": {"target_npc_id": person["id"], "location_ids": ["yer"]},
            "reward_plan": {"success": {"gold": 1, "xp": 1}},
        }
        card = dialogue_commitments.job_cards(world, [quest])[0]
        self.assertNotIn(SECRETS["stranger_name"], card["objective"])
