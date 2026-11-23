"""D-332: a person's answer the safety check rejects is repaired once by the model, else answered from the question.

Never an unrelated rumour for a question the rumour does not answer. Town seed 7400 (ThroughTheRealTurn.TOWN_SEED).
"""
import copy
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import interaction_adventure
import living_world
import shop_trade
import town_knowledge
import world_threads
from api import model_phase
from api.tests import test_town_knowledge as cases
from api.tests.test_front_proposal import FrontClient

TAVERN = "Tavernaya doğru yürürsün."
BEER = "Sana bir bira ikram eder."


class RepairClient(FrontClient):
    """Counts every call; a call made inside the repair scope answers with `repair`, a speech call with `narration`."""

    def __init__(self):
        super().__init__()
        self.repair = None
        self.repair_calls = 0
        self.repair_schemas = []

    def chat(self, *args, **kwargs):
        schema = kwargs.get("format") or {}
        if "front" not in (schema.get("properties") or {}) and model_phase.in_repair_call():
            self.chat_calls += 1
            self.repair_calls += 1
            self.repair_schemas.append(schema)
            self.message_batches.append(kwargs.get("messages", []))
            return {"message": {"content": json.dumps(self.repair, ensure_ascii=False)}}
        return super().chat(*args, **kwargs)


class SpeechRepair(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = cases.ThroughTheRealTurn.asyncSetUp
    asyncTearDown = cases.ThroughTheRealTurn.asyncTearDown
    campaign_with_npc = cases.ThroughTheRealTurn.campaign_with_npc
    start_plain = cases.ThroughTheRealTurn.start
    say = cases.ThroughTheRealTurn.say
    TOWN_SEED = 7400

    async def ready(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.route_file = Path(folder.name) / "routes.jsonl"
        self.enterContext(patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1",
                                                  "AI_DND_ROUTE_LOG": str(self.route_file)}))
        await self.start_plain()
        self.client = RepairClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.world = self.session.world_state

    def last_route(self):
        return json.loads(self.route_file.read_text(encoding="utf-8").splitlines()[-1])

    def reading(self, asks, place_id="none", npc=None):
        self.client.front = {"kind": "speak_to", "person_id": (npc or self.npc)["id"], "asks": asks,
                             "place_id": place_id}

    def a_town_place(self):
        settlement = town_knowledge._settlement(self.world)
        return next(key for key, value in self.world["locations"].items()
                    if isinstance(value, dict) and value.get("parent_location_id") == settlement and value.get("name"))

    def leads(self):
        return [thread["public_line"] for thread in world_threads.active(self.world, town_knowledge._settlement(self.world))]

    async def ask_rejected(self, question, line, asks, place_id="none", repair=None):
        self.client.repair = repair or {"spoken_text": line, "stage_direction": ""}
        self.reading(asks, place_id)
        return await self.say(question, line)

    async def test_a_rejected_answer_is_repaired_once_by_the_model(self):
        await self.ready()
        self.client.repair = {"spoken_text": "Taverna mı? Meydanın öbür ucunda.", "stage_direction": ""}
        self.reading("place")
        text = await self.say("Taverna nerede?", TAVERN)
        self.assertIn("Meydanın öbür ucunda", text)
        self.assertNotIn("Duyduğuma göre", text)
        self.assertEqual(self.client.repair_calls, 1)
        self.assertEqual(self.client.chat_calls, 3)
        speech = self.last_route()["speech"]
        self.assertIn("safety:INVENTED_PLAYER_ACTION", speech)
        self.assertIn("model_repair", speech)
        self.assertNotIn("python_town_lead", speech)

    async def test_the_repair_asks_for_two_fields_only(self):
        await self.ready()
        self.client.repair = {"spoken_text": "Meydanın öbür ucunda.", "stage_direction": ""}
        self.reading("place")
        await self.say("Taverna nerede?", TAVERN)
        [schema] = self.client.repair_schemas
        self.assertEqual(set(schema["properties"]), {"spoken_text", "stage_direction"})
        self.assertEqual(set(schema["required"]), {"spoken_text", "stage_direction"})

    async def test_an_item_transfer_answer_gets_the_same_repair(self):
        await self.ready()
        self.client.repair = {"spoken_text": "Hanın arka kapısından geç, sağdaki ilk yer.", "stage_direction": ""}
        self.reading("other")
        text = await self.say("Tarif edebilir misin?", BEER)
        self.assertIn("arka kapısından", text)
        speech = self.last_route()["speech"]
        self.assertIn("safety:UNSUPPORTED_ITEM_TRANSFER", speech)
        self.assertIn("model_repair", speech)

    async def test_a_failed_repair_answers_the_question_not_a_rumour(self):
        await self.ready()
        place = self.a_town_place()
        text = await self.ask_rejected("Taverna nerede?", TAVERN, "place", place,
                                       repair={"spoken_text": BEER, "stage_direction": ""})
        self.assertIn(living_world.public_npc_name(self.npc), text)
        self.assertIn(self.world["locations"][place]["name"], text)
        for lead in self.leads():
            self.assertNotIn(lead, text)
        self.assertEqual(self.client.chat_calls, 3)
        self.assertIn("model_repair_failed", self.last_route()["speech"])

    async def test_two_people_asked_where_the_tavern_is_do_not_give_the_same_rumour(self):
        await self.ready()
        other = next(n for n in self.world["npcs"] if n["id"] != self.npc["id"])
        other["location"] = self.npc["location"]
        first = self.npc
        texts = []
        for person in (first, other):
            self.npc = person
            self.world["flags"].update(active_npc_id=person["id"], last_npc_id=person["id"], active_npc_until_turn=99)
            self.client.repair = {"spoken_text": BEER, "stage_direction": ""}
            self.reading("place", npc=person)
            texts.append(await self.say("Taverna nerede?", TAVERN))
        for person, text in zip((first, other), texts):
            self.assertNotIn("Duyduğuma göre", text)
            self.assertIn(living_world.public_npc_name(person), text)
            for line in interaction_adventure._UNKNOWN_LINES:
                self.assertNotIn(line.split("“", 1)[1].rstrip("”"), text)
            self.assertIn("tarafına sor", text)

    async def test_a_rumour_question_still_gets_the_towns_lead(self):
        await self.ready()
        text = await self.ask_rejected("Ne haberler var?", TAVERN, "rumour", repair={"spoken_text": BEER, "stage_direction": ""})
        self.assertIn("Duyduğuma göre", text)

    async def test_a_repaired_answer_moves_no_coin_and_records_no_offer(self):
        await self.ready()
        before = copy.deepcopy((shop_trade.purse_cp(self.world), self.world.get("currency"), self.world["inventory"], self.world[world_threads.KEY]))
        offers = copy.deepcopy(self.session.quest_offers())
        self.client.repair = {"spoken_text": "Sana beş altın veririm, bir de bir kılıç.", "stage_direction": ""}
        self.reading("place")
        await self.say("Taverna nerede?", TAVERN)
        self.assertEqual(before, (shop_trade.purse_cp(self.world), self.world.get("currency"), self.world["inventory"], self.world[world_threads.KEY]))
        self.assertEqual(offers, self.session.quest_offers())

    async def test_front_reading_and_narration_make_two_model_calls_never_three(self):
        await self.ready()
        self.reading("place")
        text = await self.say("Taverna nerede?", "Han meydanda.")
        self.assertIn("Han meydanda", text)
        self.assertEqual(self.client.chat_calls, 2)
        self.assertEqual(self.client.repair_calls, 0)
        self.assertEqual(self.last_route()["speech"], [])

    async def test_a_repaired_turn_is_undone_like_any_turn(self):
        await self.ready()
        await self.say("Selam.", "Selam.")
        before = copy.deepcopy(self.session.world_state)
        action_id = str(uuid.uuid4())
        self.client.repair = {"spoken_text": "Meydanın öbür ucunda.", "stage_direction": ""}
        self.reading("place")
        self.client.narration = TAVERN
        response = await self.http.post(self.turn_url, json={
            "message": "Taverna nerede?", "action_id": action_id, "interaction_mode": "say",
            "target_id": self.npc["id"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.repair_calls, 1)
        undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": action_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.manager.get(self.session_id).game_session.world_state, before)


if __name__ == "__main__":
    unittest.main()
