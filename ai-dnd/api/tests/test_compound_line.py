"""Task 40: a line with two parts does both (H14, H185). The reading points at where the second part starts; the
second part is the player's own words, read as a line of its own when the first part was the player's own doing, and
said to the person when it was a word to them. No new word list; the two calls a turn has stay two."""
import copy
import json
import unittest
import uuid
from unittest.mock import patch

import game
from api.tests import test_front_proposal as front_tests
from api.tests.town_seed import fixed_town


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

    async def test_eating_then_asking_the_person_here_gets_their_answer(self):
        # Review I1: the second part names someone here, so it is said to them and their answer is the model's.
        await self.table(lambda t: {"kind": "consume", "item_id": t.food, "also_says": "Marek'e şehri soruyorum"},
                         lambda t: {"kind": "speak_to", "person_id": t.npc["id"]})
        reply = await self.line("yemeği yiyorum, Marek'e şehri soruyorum", "Şehir kalabalıktır.")
        self.assertNotIn("Tabak yemek", self.held())
        self.assertIn("Şehir kalabalıktır.", reply["narration"])
        self.assertNotIn("Yavaş ol", reply["narration"])
        self.assertLessEqual(self.client.chat_calls, 2)

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


Q020 = "I leave the guard behind and walk to Yolcu Turna Hanı, then ask the innkeeper for a room for one night."  # QA #020
Q020_REST = "ask the innkeeper for a room for one night"


class AWalkThenTheRest(unittest.IsolatedAsyncioTestCase):
    """Dilim 3D Task 4 (#020): a walk with more said after it. When the walk got there, the rest of the line is read
    as a line of its own at the place walked to, under the one turn index, with one Undo; a walk that did not get
    there drops it."""
    asyncSetUp, asyncTearDown = front_tests.FrontTable.asyncSetUp, front_tests.FrontTable.asyncTearDown
    campaign_with_npc, open_job = front_tests.FrontTable.campaign_with_npc, front_tests.FrontTable.open_job
    front_calls = front_tests.FrontTable.front_calls

    async def town(self, *, locked=False):
        with fixed_town(self, 4531):
            await front_tests.FrontTable.begin(self)
        import living_world
        self.inn = next(key for key, value in self.world["locations"].items()
                        if isinstance(value, dict) and value.get("parent_location_id") == self.world["location"]
                        and living_world.scene_kind(self.world, key) == "tavern")
        door = next(item for item in self.world["doors"] if item.get("id") == f"venue-door:{self.inn}")
        door.update(locked=locked, open=False)
        self.barmen = "npc_t4_barmen"
        self.world["npcs"].append({"id": self.barmen, "name": "Osman", "role": "Barmen", "current_hp": 10,
                                   "location": self.inn, "place_role_of": self.inn})
        self.world["currency"] = {**self.world.get("currency", {}), "player": 500, self.barmen: 0}

    def room_ask(self):
        return [{"kind": "go_to", "place_id": self.inn, "inside": True, "also_says": Q020_REST},
                {"kind": "speak_to", "person_id": self.barmen, "economic_intent": "room_quote"}]

    async def turn(self, line, fronts, *, action_id=None, reply="Buyrun."):
        if not hasattr(self, "client") or not isinstance(self.client, OneFrontAfterAnother):
            self.client = OneFrontAfterAnother(fronts, reply)
            self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        else:
            self.client.fronts, self.client.front = list(fronts), fronts[0]
        response = await self.http.post(self.turn_url, json={"message": line, "action_id": action_id or str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def live(self):
        return self.manager.get(self.session_id).game_session

    def location(self):
        return self.live().world_state["location"]

    def purse_cp(self):
        return self.live().world_state["currency"]["player"]

    def room_price_text(self):
        import bold_acts
        world = self.live().world_state
        barmen = next(npc for npc in world["npcs"] if npc.get("id") == self.barmen)
        price = bold_acts.room_price(world, barmen)
        return f"Gecelik {price // 10} gümüş" if price % 10 == 0 else f"Gecelik {price} bakır"

    def snapshot(self):
        session = self.live()
        return copy.deepcopy({"world": session.world_state, "messages": session.messages,
                              "purse": session.world_state["currency"]["player"]})

    async def test_020_walk_then_room_ask_reaches_the_barmen(self):
        await self.town()
        before, turn = self.purse_cp(), self.world["flags"].get("turn_index", 0)
        reply = await self.turn(Q020, self.room_ask())
        self.assertEqual(self.location(), self.inn)
        self.assertEqual(len(self.front_calls()), 2)  # the rest had its own reading, at the inn
        self.assertIn(Q020_REST, str(self.client.message_batches[-1]))
        self.assertEqual(self.purse_cp(), before)  # a price asked moves no coin
        self.assertIn(self.room_price_text(), reply.json()["narration"])
        self.assertEqual(self.live().world_state["flags"]["turn_index"], turn + 1)  # one line is one turn
        self.assertLessEqual(self.client.chat_calls, 2)

    async def test_a_locked_door_drops_the_rest(self):
        await self.town(locked=True)
        for npc in self.world["npcs"]:  # Marek alone stays in the street, the one a word there would go to
            if npc.get("id") != self.npc["id"] and npc.get("location") == self.world["location"]:
                npc["location"] = self.inn
        reply = await self.turn(Q020, [{"kind": "go_to", "place_id": self.inn, "inside": True,
                                        "also_says": Q020_REST}])
        self.assertNotEqual(self.location(), self.inn)
        self.assertEqual(len(self.front_calls()), 1)
        self.assertEqual(self.client.chat_calls, 1)  # nobody left in the street is asked for the room
        self.assertNotIn("Marek", reply.json()["narration"])
        self.assertNotIn("Buyrun.", reply.json()["narration"])
        self.assertNotIn(self.room_price_text(), reply.json()["narration"])

    async def test_a_locked_door_reached_from_outside_drops_the_rest(self):
        # Review I-1: "walk to the inn" read as going up to it (inside: false) stops at the locked door; standing at
        # a locked door is no arrival, so the guard left in the street is not asked for the innkeeper's room.
        await self.town(locked=True)
        for npc in self.world["npcs"]:
            if npc.get("id") != self.npc["id"] and npc.get("location") == self.world["location"]:
                npc["location"] = self.inn
        reply = await self.turn(Q020, [{"kind": "go_to", "place_id": self.inn, "inside": False,
                                        "also_says": Q020_REST},
                                       {"kind": "speak_to", "person_id": self.npc["id"]}], reply="Öyle olsun bakalım.")
        self.assertNotEqual(self.location(), self.inn)
        self.assertEqual(len(self.front_calls()), 1)
        self.assertEqual(self.client.chat_calls, 1)
        self.assertNotIn("Marek", reply.json()["narration"])
        self.assertNotIn("Öyle olsun bakalım.", reply.json()["narration"])

    async def test_a_walk_then_sleep_sleeps_once(self):
        # Review I-2: the walk's own sleep owner already slept the line's sleep; the rest is not slept again.
        import bold_acts
        import grounded_action
        await self.town()
        world = self.live().world_state
        now = world["campaign_time"]["elapsed_seconds"]
        world["flags"]["inn_room"] = {"place": self.inn, "until": now + bold_acts._ROOM_DAY}
        reply = await self.turn("hana gidiyorum ve uyuyorum",
                                [{"kind": "go_to", "place_id": self.inn, "inside": True, "also_says": "uyuyorum"},
                                 {"kind": "wait"}])
        self.assertEqual(self.location(), self.inn)
        elapsed = self.live().world_state["campaign_time"]["elapsed_seconds"] - now
        self.assertEqual(elapsed, grounded_action.LOCAL_WALK_SECONDS + 8 * 3600, reply.json()["narration"])
        self.assertNotIn("Daha yeni dinlenmiştin", reply.json()["narration"])
        self.assertEqual(len(self.front_calls()), 1)

    async def test_one_undo_takes_back_both_parts(self):
        await self.town()
        before = self.snapshot()
        action_id = str(uuid.uuid4())
        await self.turn(Q020, self.room_ask(), action_id=action_id)
        self.assertEqual(self.location(), self.inn)
        undone = await self.http.post(f"/api/game/sessions/{self.session_id}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": action_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.snapshot(), before)

    async def test_walk_then_pay_opens_one_card_for_the_coin(self):
        # Money moves only through a confirmed card: the tip said at the inn opens one card of 5 silver, once.
        await self.town()
        before = self.purse_cp()
        reply = await self.turn("hana gidiyorum, barmene 5 gümüş veriyorum",
                                [{"kind": "go_to", "place_id": self.inn, "inside": True,
                                  "also_says": "barmene 5 gümüş veriyorum"},
                                 {"kind": "speak_to", "person_id": self.barmen, "economic_intent": "tip",
                                  "coin_cp": 50}])
        self.assertEqual(self.location(), self.inn)
        card = reply.json()["state"]["economic_offer"]
        self.assertIsNotNone(card, reply.json()["narration"])
        self.assertEqual(card["max_total_cp"], 50)
        offers = self.live().world_state["flags"].get("economic_offers", {}).values()
        self.assertEqual([row["status"] for row in offers].count("prepared"), 1)
        self.assertEqual(self.purse_cp(), before)

    async def test_coin_read_with_the_walk_is_not_read_again_in_the_rest(self):
        # The walk's own reading already held the coin out (a room deal on arrival): the rest names the same coin, so
        # it is not read a second time and at most one card is open.
        await self.town()
        before = self.purse_cp()
        await self.turn("hana gidiyorum, barmene 5 gümüş veriyorum",
                        [{"kind": "go_to", "place_id": self.inn, "inside": True, "person_id": self.barmen,
                          "coin_cp": 50, "deal": "room", "also_says": "barmene 5 gümüş veriyorum"},
                         {"kind": "speak_to", "person_id": self.barmen, "economic_intent": "tip", "coin_cp": 50}])
        self.assertEqual(self.location(), self.inn)
        self.assertEqual(len(self.front_calls()), 1)
        offers = self.live().world_state["flags"].get("economic_offers", {}).values()
        self.assertEqual([row["status"] for row in offers].count("prepared"), 0)  # a walk's coin opens no card here
        self.assertEqual(self.purse_cp(), before)

    async def test_replayed_action_id_does_not_say_the_rest_again(self):
        await self.town()
        action_id = str(uuid.uuid4())
        first = await self.turn(Q020, self.room_ask(), action_id=action_id)
        calls, turn = self.client.chat_calls, self.live().world_state["flags"]["turn_index"]
        again = await self.turn(Q020, self.room_ask(), action_id=action_id)
        self.assertEqual(again.json()["narration"], first.json()["narration"])
        self.assertEqual(self.client.chat_calls, calls)
        self.assertEqual(self.live().world_state["flags"]["turn_index"], turn)

    async def test_no_call_left_keeps_the_walk(self):
        await self.town()
        real = game._the_rest_of_the_line

        def starved(*args, **kwargs):  # the budget is spent only at the moment the rest would be read
            with patch("api.ollama_adapter.model_calls_left", return_value=0):
                return real(*args, **kwargs)

        with patch.object(game, "_the_rest_of_the_line", starved):
            reply = await self.turn(Q020, self.room_ask())
        self.assertEqual(self.location(), self.inn)
        self.assertEqual(len(self.front_calls()), 1)
        self.assertNotIn(self.room_price_text(), reply.json()["narration"])


class WhatCountsAsGettingThere(unittest.TestCase):
    """Review minors 4 and 6: the walk's receipt alone, without a turn around it."""

    def there(self, read, action_result, *, here="inn", before="street"):
        session = game.create_session(seed=7)
        session.world_state["location"] = here
        return game._walked_there(read, action_result, before, session=session)

    def test_an_old_chain_walk_already_inside_has_got_there(self):
        receipt = {"action": "travel", "status": "already_here", "target_id": "inn"}
        self.assertTrue(self.there({}, receipt, before="inn"))
        self.assertFalse(self.there({}, {**receipt, "target_id": "smithy"}, before="inn"))

    def test_a_walk_with_no_place_named_gets_nowhere(self):
        receipt = {"action": "grounded_action", "status": "completed", "target_id": None,
                   "steps": [{"verb": "go", "status": "completed"}]}
        self.assertFalse(self.there({"kind": "go_to", "id": None}, receipt, here="street"))

    def test_a_locked_door_is_no_arrival_an_open_one_is(self):
        step = {"verb": "go", "status": "completed", "target_id": "inn", "position": "at_door",
                "door_state": {"open": False, "locked": True, "broken": False}}
        receipt = {"action": "grounded_action", "status": "completed", "target_id": "inn", "steps": [step]}
        self.assertFalse(self.there({"kind": "go_to", "id": "inn"}, receipt, here="street"))
        unlocked = {**step, "door_state": {"open": False, "locked": False, "broken": False}}
        self.assertTrue(self.there({"kind": "go_to", "id": "inn"}, {**receipt, "steps": [unlocked]}, here="street"))


if __name__ == "__main__":
    unittest.main()
