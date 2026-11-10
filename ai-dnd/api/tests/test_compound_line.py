"""Task 40: a line with two parts does both (H14, H185). The reading points at where the second part starts; the
second part is the player's own words, read as a line of its own when the first part was the player's own doing, and
said to the person when it was a word to them. No new word list; the two calls a turn has stay two."""
import json
import unittest
from unittest.mock import patch

from api.tests import test_front_proposal as front_tests


class OneFrontAfterAnother(front_tests.FrontClient):
    """Each front reading takes the next scripted front; the last one repeats."""

    def __init__(self, fronts, narration="Şimdilik sessiz bir gün."):
        super().__init__(narration)
        self.fronts = list(fronts)
        self.front = self.fronts[0]

    def chat(self, *args, **kwargs):
        schema = kwargs.get("format") or {}
        if "front" in (schema.get("properties") or {}):
            self.front = self.fronts.pop(0) if len(self.fronts) > 1 else self.fronts[0]
        return super().chat(*args, **kwargs)


class ALineWithTwoActsDoesBoth(unittest.IsolatedAsyncioTestCase):
    asyncSetUp, asyncTearDown = front_tests.FrontTable.asyncSetUp, front_tests.FrontTable.asyncTearDown
    campaign_with_npc, open_job, line = (front_tests.FrontTable.campaign_with_npc, front_tests.FrontTable.open_job,
                                         front_tests.FrontTable.line)
    begin, routes = front_tests.FrontTable.begin, front_tests.FrontTable.routes

    async def table(self, *fronts):
        await self.begin()
        import equipment_economy
        for name in ("Tabak yemek", "Şarap"):
            equipment_economy.grant_named_item(self.world, name)
        import front_proposal
        bag = {row["name"]: row["id"] for row in front_proposal._bag(self.world)}
        self.food, self.wine = bag["Tabak yemek"], bag["Şarap"]
        client = OneFrontAfterAnother([front(self) for front in fronts])
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", client))
        self.client = client

    def held(self):
        return [item.get("name") if isinstance(item, dict) else item for item in self.world["inventory"]]

    async def test_eating_and_drinking_in_one_line_eats_and_drinks(self):
        await self.table(lambda t: {"kind": "consume", "item_id": t.food, "also_says": "şarabı içiyorum"},
                         lambda t: {"kind": "consume", "item_id": t.wine})
        turn = self.world["flags"].get("turn_index", 0)
        reply = await self.line("yemeği yiyorum ve şarabı içiyorum")
        self.assertNotIn("Tabak yemek", self.held())
        self.assertNotIn("Şarap", self.held())
        self.assertEqual(self.world["flags"]["turn_index"], turn + 1)  # one line is one turn
        self.assertLessEqual(self.client.chat_calls, 2)
        self.assertNotIn("Marek:", reply["narration"])  # the drink was done, not said to the man standing there

    async def test_one_undo_takes_back_both_parts(self):
        import uuid
        await self.table(lambda t: {"kind": "consume", "item_id": t.food, "also_says": "şarabı içiyorum"},
                         lambda t: {"kind": "consume", "item_id": t.wine})
        action_id = str(uuid.uuid4())
        response = await self.http.post(self.turn_url, json={"message": "yemeği yiyorum ve şarabı içiyorum",
                                                             "action_id": action_id})
        self.assertEqual(response.status_code, 200, response.text)
        undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": action_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        world = self.manager.get(self.session_id).game_session.world_state
        names = [item.get("name") if isinstance(item, dict) else item for item in world["inventory"]]
        self.assertIn("Tabak yemek", names)
        self.assertIn("Şarap", names)

    async def test_the_second_part_alone_is_read_as_the_players_own_words(self):
        await self.table(lambda t: {"kind": "consume", "item_id": t.food, "also_says": "şarabı içiyorum"},
                         lambda t: {"kind": "consume", "item_id": t.wine})
        await self.line("yemeği yiyorum ve şarabı içiyorum")
        last = self.client.message_batches[-1]
        self.assertIn("şarabı içiyorum", str(last))
        self.assertNotIn("yemeği yiyorum", str(last[-1]))

    async def test_one_act_with_no_second_part_does_one_thing(self):
        await self.table(lambda t: {"kind": "consume", "item_id": t.food})
        await self.line("yemeği yiyorum")
        self.assertNotIn("Tabak yemek", self.held())
        self.assertIn("Şarap", self.held())
        self.assertEqual(self.client.chat_calls, 1)

    async def test_a_second_part_the_line_never_said_does_nothing(self):
        await self.table(lambda t: {"kind": "consume", "item_id": t.food, "also_says": "şarabı içiyorum"},
                         lambda t: {"kind": "consume", "item_id": t.wine})
        await self.line("yemeği yiyorum")
        self.assertIn("Şarap", self.held())

    async def test_the_second_part_of_a_word_to_the_person_reaches_the_person(self):
        # H14: "Kendimi tanıtıyorum. Şehri anlat" said to Marek: the person hears both halves in the one answer.
        await self.table(lambda t: {"kind": "speak_to", "person_id": t.npc["id"], "also_says": "Şehri anlat"})
        await self.line("Kendimi tanıtıyorum. Şehri anlat", "Şehir kalabalıktır.")
        self.assertIn("şunu da söyledi: Şehri anlat", str(self.client.message_batches[-1]))
        self.assertLessEqual(self.client.chat_calls, 2)

    async def test_the_reading_asks_for_a_second_act_too(self):
        await self.table(lambda t: {"kind": "consume", "item_id": t.food})
        await self.line("yemeği yiyorum")
        prompt = json.dumps(self.client.message_batches[0], ensure_ascii=False)
        self.assertIn("ikinci bir iş", prompt)


if __name__ == "__main__":
    unittest.main()
