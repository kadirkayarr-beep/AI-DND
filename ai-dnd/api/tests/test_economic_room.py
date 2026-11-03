"""A4: a room is a card. The line that asks for it opens the card, moves no coin and does not sleep (C13, D4, D5).

The three ways into a room (`_sleep_after_walk`, `_room_asked`, `_buy`) and the coin handed over with the line all
reach `bold_acts.take_room`, which prepares the card and pays nothing. Coin held out with a room or a purchase line
is its tender when it covers the price and the purse holds it, and is otherwise ignored with a note; it never turns
into a separate gift card. A change of place cancels the cards prepared before this turn. No real model is called.
"""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import bold_acts
import campaign_time
import economic_actions as ea
import game
import world_reactions
from api.core_resolution import resolution_action_scope
from api.tests import test_last_play_blockers as blockers
from api.tests.test_three_plays import PlayClient

HOUR = 3600
WALK_AND_SLEEP = "neyse ben hana dönüp oda tutayım, yarın sabaha kadar uyuyorum"


def gift(recipient, amount, source="earlier-action"):
    return ea.EconomicProposal(purpose="gift", recipient_id=recipient, source_id=None, item_id=None, count=1,
                               amount_cp=amount, tip_cp=0, tender_cp=None, dependency="base_required",
                               source_action_id=source, text_span=None)


class Counter(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.w = self.s.world_state
        self.here = self.w["location"]
        self.w["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": self.here, "current_hp": 10},
            {"id": "guest", "name": "Oren", "role": "Yolcu", "location": self.here, "current_hp": 10},
        ]
        self.w["currency"] = {"player": 500, "barman": 100, "guest": 100}
        self.w.setdefault("flags", {})["turn_index"] = 3
        campaign_time.initialize(self.w)
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)

    def npc(self, npc_id):
        return next(npc for npc in self.w["npcs"] if npc["id"] == npc_id)

    def offers(self):
        return self.w.get("flags", {}).get("economic_offers", {})

    def prepared(self):
        return [data for data in self.offers().values() if data["status"] == "prepared"]

    def money(self):
        flags = self.w.get("flags", {})
        return copy.deepcopy((self.w["currency"], self.w.get("inventory"), flags.get("inn_room"),
                              flags.get("economic_ledger"), self.w.get("campaign_time")))

    def confirm(self, data, action="confirm-room"):
        with resolution_action_scope(action, "session"):
            return ea.confirm_offer(ea.EconomicState(world=self.w, character=self.s.character),
                                    offer_id=data["offer_id"], confirmation_digest=data["confirmation_digest"],
                                    operation_id=f"offer:{action}", check=lambda skill, dc: "BAŞARILI")

    def turn(self, line, **kwargs):
        return self.s.run_player_turn(line, **kwargs)


class TheCardIsTheRoom(Counter):
    def test_take_room_returns_offered_not_rented(self):
        before = self.money()
        self.s._economic_turn_key = "room-turn"
        room = bold_acts.take_room(self.s, "bi oda tutayım usta")
        self.assertEqual((room["status"], room["room"], room["paid"], room["coin_seen"]), ("offered", False, 0, False))
        self.assertEqual(room["offer_id"], self.prepared()[0]["offer_id"])
        self.assertEqual(self.money(), before)
        self.assertIn("50 bakır", room["line"])

    def test_room_and_sleep_without_walk_opens_card_no_sleep(self):
        clock = self.w["campaign_time"]["elapsed_seconds"]
        before = self.money()
        result = self.turn("bi oda tutayım usta, sabaha kadar uyuyacağım")
        self.assertEqual(result["action_result"]["status"], "offered", result["narration"])
        self.assertEqual(self.money(), before)
        self.assertEqual(self.w["campaign_time"]["elapsed_seconds"], clock)
        [card] = self.prepared()
        self.assertEqual(card["proposal"]["purpose"], "room")

    def test_existing_room_right_no_second_charge(self):
        now = self.w["campaign_time"]["elapsed_seconds"]
        self.w["flags"]["inn_room"] = {"place": self.here, "until": now + 12 * HOUR}
        before = self.money()
        room = bold_acts.take_room(self.s, "bi oda tutayım usta")
        self.assertEqual((room["status"], room["room"], room["offer_id"]), ("held", True, None))
        self.assertEqual(self.money(), before)
        result = self.turn("bi oda tutayım usta")
        self.assertEqual(result["action_result"]["status"], "rented", result["narration"])
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.w["currency"], before[0])

    def test_room_status_mapping_per_result(self):
        cases = [
            ({"status": "held", "reason_code": None}, "rented"),
            ({"status": "offered", "reason_code": None}, "offered"),
            ({"status": "refused", "reason_code": "npc_refuses"}, "refused"),
            ({"status": "clarification", "reason_code": "purse_below_base"}, "no_money"),
            ({"status": "clarification", "reason_code": "npc_not_here"}, "clarification"),
        ]
        for room, status in cases:
            with self.subTest(status=room["status"], reason=room["reason_code"]):
                answer = {"line": "Satır.", "paid": 0, "room": room["status"] == "held", "offer_id": None,
                          "coin_seen": False, **room}
                with patch.object(bold_acts, "take_room", return_value=answer):
                    for reply in (bold_acts._room_asked(self.s, "bi oda tutayım"), bold_acts._buy(self.s, "bi oda tutayım")):
                        action = reply["action_result"]
                        self.assertEqual((action["action"], action["status"]), ("lodging", status))
                        self.assertNotIn("currency", action["state_changes"])
                        self.assertEqual(action["price_cp"], 0)
        # The real refusals, as the barman says them.
        self.w["currency"]["player"] = 10
        self.assertEqual(self.turn("bi oda tutayım usta")["action_result"]["status"], "no_money")
        self.w["currency"]["player"] = 500
        with patch.object(world_reactions, "refuses", side_effect=lambda world, npc: npc.get("id") == "barman"):
            refused = self.turn("bi oda tutayım usta")
        self.assertEqual(refused["action_result"]["status"], "refused")
        self.assertIn(world_reactions.refusal_line(self.npc("barman")), refused["narration"])

    def test_room_confirm_grants_inn_room_once(self):
        self.turn("bi oda tutayım usta")
        [card] = self.prepared()
        resolution = self.confirm(card)
        self.assertEqual(resolution.status, "applied")
        self.assertEqual(self.w["currency"]["player"], 450)
        self.assertEqual(self.w["flags"]["inn_room"]["place"], self.here)
        self.assertEqual(self.w["flags"]["economic_ledger"]["sink_totals"], {f"sink:lodging:{self.here}": 50})
        paid = self.money()
        again = self.confirm(card, action="confirm-room-2")
        self.assertEqual((again.status, again.reason_code), ("refused", "offer_not_prepared"))
        self.assertEqual(self.money(), paid)


class CoinWithTheLine(Counter):
    def test_chat_room_with_handed_gold_is_tender(self):
        self.s._coin_paid = (100, self.npc("barman"), self.here)
        result = self.turn("hancıya 1 altın verip oda tutuyorum")
        self.assertEqual(result["action_result"]["coin_seen_by"], "room")
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["tender_cp"]), ("room", 100))
        self.assertEqual(self.w["currency"]["player"], 500)
        resolution = self.confirm(card)
        self.assertEqual((resolution.net_debit_cp, resolution.change_cp, resolution.tender_cp), (50, 50, 100))
        self.assertEqual(self.w["currency"]["player"], 450)

    def test_chat_room_with_coin_above_purse_is_ignored_with_note(self):
        self.w["currency"]["player"] = 60
        self.s._coin_paid = (100, self.npc("barman"), self.here)
        result = self.turn("hancıya 1 altın verip oda tutuyorum")
        [card] = self.prepared()
        self.assertEqual(len(self.offers()), 1)
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["tender_cp"]), ("room", None))
        self.assertIn(bold_acts.COIN_NOT_TENDERED, result["narration"])
        self.assertEqual(self.w["currency"]["player"], 60)

    def test_chat_room_with_coin_below_price_keeps_room_card(self):
        self.s._coin_paid = (10, self.npc("barman"), self.here)
        before = self.money()
        result = self.turn("hancıya 1 gümüş verip oda tutuyorum")
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["tender_cp"]), ("room", None))
        self.assertFalse([data for data in self.offers().values() if data["proposal"]["purpose"] == "gift"])
        self.assertIn(bold_acts.COIN_NOT_TENDERED, result["narration"])
        self.assertIsNone(self.s._coin_paid)
        self.assertEqual(self.money(), before)

    def test_chat_purchase_with_handed_gold_is_tender(self):
        self.s._coin_paid = (100, self.npc("barman"), self.here)
        before = self.money()
        result = self.turn("al şu bi altını, bi bira ver usta")
        self.assertEqual(result["action_result"]["action"], "shop_offer", result["narration"])
        self.assertEqual(result["action_result"]["coin_seen_by"], "purchase")
        self.assertEqual(self.w["flags"]["counter_offer_v1"]["tender_cp"], 100)
        self.assertEqual(self.offers(), {})
        self.assertIsNone(self.s._coin_paid)
        self.assertEqual(self.money(), before)
        # The same coin held out to an offer that is still open.
        self.s._coin_paid = (100, self.npc("barman"), self.here)
        standing = bold_acts.standing_offer(self.s, self.npc("barman"))
        self.assertEqual(standing["action_result"]["coin_seen_by"], "purchase")
        self.assertEqual(self.w["flags"]["counter_offer_v1"]["tender_cp"], 100)
        self.assertIsNone(self.s._coin_paid)
        self.assertEqual(self.offers(), {})

    def test_chat_purchase_with_coin_below_price_has_no_tender(self):
        self.s._coin_paid = (2, self.npc("barman"), self.here)
        result = self.turn("al şu iki bakırı, bi bira ver usta")
        self.assertEqual(result["action_result"]["coin_seen_by"], "purchase")
        self.assertNotIn("tender_cp", self.w["flags"]["counter_offer_v1"])
        self.assertIn(bold_acts.COIN_NOT_TENDERED, result["narration"])
        self.assertEqual(self.offers(), {})

    def test_entered_inn_room_with_handed_gold_is_tender(self):
        # The door was gone through before this turn ran: the planner's result says "enter".
        self.s._economic_turn_key = "entered-turn"
        self.s._coin_paid = (100, self.npc("barman"), self.here)
        walked = {"narration": "İçeridesin.", "action_result": {"action": "enter", "status": "completed",
                                                                 "state_changes": []}}
        before = self.money()
        game._sleep_after_walk(walked, "hancıya 1 altın verip oda tutup uyuyorum", self.here,
                               {"direct_result": {"action": "enter"}}, session=self.s)
        game._tell_the_coin(walked, session=self.s)
        self.assertEqual(walked["action_result"]["coin_seen_by"], "room")
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["tender_cp"]), ("room", 100))
        self.assertEqual(len(self.offers()), 1)
        self.assertEqual(self.money(), before)

    def test_sleep_after_walk_reads_the_card_this_action_prepared(self):
        self.s._economic_turn_key = "spoken-turn"
        bold_acts.take_room(self.s, "bi oda istiyorum")
        self.assertEqual(len(self.prepared()), 1)
        walked = {"narration": "Handasın.", "action_result": {"action": "move", "status": "completed",
                                                              "state_changes": ["location"]}}
        with patch.object(bold_acts, "take_room", side_effect=AssertionError("second prepare")):
            game._sleep_after_walk(walked, "hana gidiyorum, bir oda istiyorum, sabaha kadar uyuyorum", "elsewhere",
                                   None, session=self.s)
        self.assertEqual(len(self.prepared()), 1)
        self.assertIsNotNone(ea.prepared_by_action(self.w, source_action_id="spoken-turn", purpose="room"))
        self.assertIsNone(ea.prepared_by_action(self.w, source_action_id="other-turn", purpose="room"))

    def test_flee_location_change_cancels_prepared_offer(self):
        ea.prepare_from_panel(ea.EconomicState(world=self.w, character=self.s.character), gift("guest", 5),
                              campaign_id="c", actor_id="player", turn_index=3)
        [card] = self.prepared()
        away = next(location for location in self.w["locations"] if location != self.here)
        self.s._economic_turn_key = "flee-turn"
        self.assertTrue(game.commit_location_change(away, session=self.s))
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")


class Walks(unittest.IsolatedAsyncioTestCase):
    asyncSetUp, asyncTearDown = blockers.InnRoomTests.asyncSetUp, blockers.InnRoomTests.asyncTearDown
    post_scene_turn, begin, say = (blockers.InnRoomTests.post_scene_turn, blockers.InnRoomTests.begin,
                                   blockers.InnRoomTests.say)
    add_person, inn, coin = blockers.InnRoomTests.add_person, blockers.InnRoomTests.inn, blockers.InnRoomTests.coin

    def offers(self):
        return self.world.get("flags", {}).get("economic_offers", {})

    def prepared(self):
        return [data for data in self.offers().values() if data["status"] == "prepared"]

    def earlier_card(self, *, then_leaves=False):
        tess = self.add_person("Tess", "Çiftçi")
        ea.prepare_from_panel(ea.EconomicState(world=self.world, character=self.session.character),
                              gift(tess["id"], 5), campaign_id="c", actor_id="player",
                              turn_index=self.world["flags"].get("turn_index", 0))
        [card] = self.prepared()
        if then_leaves:
            tess["location"] = "elsewhere"  # the request in the line is for the innkeeper, not for her
        return card["offer_id"]

    async def test_walk_then_sleep_opens_room_card_no_sleep_before_confirm(self):
        await self.inn(inside=False)
        clock = self.world["campaign_time"]["elapsed_seconds"]
        out = await self.say(WALK_AND_SLEEP)
        self.assertEqual(self.world["location"], self.place["id"], out["narration"])
        [card] = self.prepared()
        self.assertEqual(card["proposal"]["purpose"], "room")
        self.assertEqual(self.coin(), 2400)
        self.assertIsNone(self.world["flags"].get("inn_room"))
        self.assertEqual(self.session.character["current_hp"], 5, out["narration"])
        self.assertLess(self.world["campaign_time"]["elapsed_seconds"], clock + 6 * HOUR)
        self.assertIsNotNone(out["state"]["economic_offer"])
        with resolution_action_scope("confirm-walk", "session"):
            ea.confirm_offer(ea.EconomicState(world=self.world, character=self.session.character),
                             offer_id=card["offer_id"], confirmation_digest=card["confirmation_digest"],
                             operation_id="offer:confirm-walk", check=lambda skill, dc: "BAŞARILI")
        self.assertEqual(self.coin(), 2350)
        self.assertTrue(self.world["flags"]["inn_room"])
        self.assertEqual(self.session.character["current_hp"], 5)  # the confirm does not sleep; a new line does

    async def test_walk_cancel_runs_before_new_prepare(self):
        await self.inn(inside=False)
        old = self.earlier_card()
        out = await self.say(WALK_AND_SLEEP)
        self.assertEqual(self.offers()[old]["status"], "cancelled", out["narration"])
        [card] = self.prepared()
        self.assertEqual(card["proposal"]["purpose"], "room")

    async def test_walk_room_uses_present_innkeeper(self):
        await self.inn(inside=False)
        self.add_person("Kel", "Barmen", location="elsewhere")  # a server somewhere else is not the one at the inn
        await self.say(WALK_AND_SLEEP)
        [card] = self.prepared()
        self.assertEqual(card["proposal"]["recipient_id"], "npc_dorn")
        self.assertEqual(card["lines"][0]["recipient_id"], f"sink:lodging:{self.place['id']}")

    async def test_walk_plus_spoken_request_leaves_one_prepared_offer(self):
        await self.inn(inside=False)
        old = self.earlier_card(then_leaves=True)
        calls = []
        real = ea.prepare_from_turn
        with patch.object(ea, "prepare_from_turn", side_effect=lambda *a, **k: (calls.append(1), real(*a, **k))[1]):
            out = await self.say(WALK_AND_SLEEP)  # the walk line that also asks for the room
        self.assertEqual(self.world["location"], self.place["id"], out["narration"])
        self.assertEqual(self.offers()[old]["status"], "cancelled")
        [card] = self.prepared()
        self.assertEqual(card["proposal"]["purpose"], "room")
        self.assertEqual(len(calls), 1)

    async def test_walk_room_with_handed_gold_is_tender_no_gift_card(self):
        await self.inn(inside=False)
        self.session._coin_paid = (100, None, self.city)
        out = await self.say("neyse ben hana dönüp hancıya 1 altın verip oda tutup uyuyorum")
        self.assertEqual(self.world["location"], self.place["id"], out["narration"])
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["tender_cp"]), ("room", 100))
        self.assertEqual(len(self.offers()), 1)
        self.assertEqual(self.coin(), 2400)
        self.assertEqual(self.session.character["current_hp"], 5)

    async def test_coin_taker_from_before_walk_opens_no_gift_card(self):
        await self.inn(inside=False)
        tess = self.add_person("Tess", "Çiftçi")
        self.session._coin_paid = (5, tess, self.city)
        out = await self.say("neyse hana gidiyorum")
        self.assertEqual(self.world["location"], self.place["id"], out["narration"])
        self.assertEqual(self.offers(), {})
        self.assertIn(game.COIN_LEFT_BEHIND, out["narration"])
        self.assertEqual(self.coin(), 2400)

    async def test_turn_source_key_is_action_id_inside_and_outside_scope(self):
        await self.inn(inside=False)
        seen = []
        real_move, real_sleep = game.commit_location_change, game._sleep_after_walk

        def move(*args, **kwargs):
            seen.append(("move", game.turn_source_key(game._session())))
            return real_move(*args, **kwargs)

        def sleep(*args, **kwargs):
            seen.append(("sleep", game.turn_source_key(game._session())))
            return real_sleep(*args, **kwargs)

        action_id = "0b8f8a4e-6f4e-4d8a-9a51-2f6a3c1d7e90"
        with patch("game.commit_location_change", side_effect=move), patch("game._sleep_after_walk", side_effect=sleep):
            response = await self.post_scene_turn(self.url, PlayClient(),
                                                  {"message": WALK_AND_SLEEP, "action_id": action_id})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(seen)
        self.assertEqual({key for _, key in seen}, {action_id}, seen)
        self.assertIn("sleep", {where for where, _ in seen})
        [card] = self.prepared()
        self.assertEqual(card["proposal"]["source_action_id"], action_id)
        self.assertIsNone(getattr(self.session, "_economic_turn_key", None))

    async def test_unscoped_turn_key_is_stable_within_run(self):
        await self.inn(inside=False)
        stale = self.earlier_card()
        self.offers()[stale]["proposal"]["source_action_id"] = "turn:0000000000000000"  # an earlier failed turn
        seen = []
        real_move = game.commit_location_change

        def move(*args, **kwargs):
            seen.append(game.turn_source_key(game._session()))
            return real_move(*args, **kwargs)

        calls = []
        real_prepare = ea.prepare_from_turn
        with patch("game.ollama.chat", side_effect=PlayClient().chat), patch("game.commit_location_change", side_effect=move), \
                patch.object(ea, "prepare_from_turn",
                             side_effect=lambda *a, **k: (calls.append(game.turn_source_key(a[0])), real_prepare(*a, **k))[1]):
            self.session.run_player_turn(WALK_AND_SLEEP)
        keys = {*seen, *calls}
        self.assertEqual(len(keys), 1, keys)
        self.assertTrue(next(iter(keys)).startswith("turn:"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.offers()[stale]["status"], "cancelled")
        [card] = self.prepared()
        self.assertEqual(card["proposal"]["purpose"], "room")
        self.assertIsNone(getattr(self.session, "_economic_turn_key", None))


if __name__ == "__main__":
    unittest.main()
