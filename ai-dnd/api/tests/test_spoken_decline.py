"""An NPC's spoken no (plan Task 10, item 103): the decline is the part it names, and it ends only by an explicit yes.

Design §3b, §12 D25, D26: the speech schema carries three optional fields (`coin_answer`, `coin_answer_for`,
`remember_player_line`); `coin_answer_for` is picked from the parts the engine lists for that NPC this turn
(`money_owner.parts_for`). After the reply, `money_owner.open_card_after_reply` reads the answer first: a decline of a
listed part stops that part (its open cards cancelled, a counter tip dropped, a goods offer closed); a decline whose
part is unclear stops every payment to that NPC; only an explicit `takes` of that part lifts it. A missing, `none` or
broken answer keeps the decline. The model never moves coin: it can only stop a card. No real model is called.
"""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

import bold_acts
import economic_actions as ea
import game
import money_owner
import shop_trade
from api.core_resolution import resolution_action_scope
from api.tests import test_front_proposal as front_tests
from money_owner import Deal

DECLINED = "az önce parayı geri çevirdi"


class Spoken(unittest.TestCase):
    """One session, a barman and a caravaner; each `turn` is a line, the person's answer and the card after it."""

    def setUp(self):
        self.s = game.create_session(seed=7)
        self.w = self.s.world_state
        self.here = self.w["location"]
        self.w["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": self.here, "current_hp": 10},
            {"id": "osman", "name": "Osman", "role": "Kervancı", "location": self.here, "current_hp": 10},
        ]
        self.w["currency"] = {"player": 100, "barman": 0, "osman": 0}
        money_owner.forget_turn(self.s)
        token = game._ACTIVE_SESSION.set(self.s)  # the engine's helpers below read this session, as a turn does
        self.addCleanup(game._ACTIVE_SESSION.reset, token)
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)

    def npc(self, npc_id):
        return next(npc for npc in self.w["npcs"] if npc["id"] == npc_id)

    def hold_out(self, npc_id, amount, deal=None):
        """What the reading leaves for a line that held out coin: the money owner's decision and the coin in hand."""
        person = self.npc(npc_id)
        self.s._coin_decision = money_owner.decide(self.w, person=person, amount_cp=amount, deal=deal, arrester=None)
        self.s._coin_paid = (amount, person, self.here) if amount else None

    def turn(self, npc_id, packet, *, amount=0, deal=None):
        """A line to `npc_id` and their answer `packet` as the speech path reads it, then the card after the reply.

        Returns the result and this turn's notes; the next turn starts clean, as `front_proposal.begin` makes it.
        """
        if amount or deal is not None:
            self.hold_out(npc_id, amount, deal)
        money_owner.read_answer(self.s, packet, npc_id, money_owner.parts_for(self.w, self.s, npc_id))
        result = {"narration": "Başını kaldırıyor.",
                  "action_result": {"action": "dialogue", "status": "resolved", "state_changes": [],
                                    "npc_id": npc_id}}
        game._tell_the_coin(result)
        notes = list(self.s._turn_notes)
        money_owner.forget_turn(self.s)
        return result, notes

    def declined(self, npc_id, part):
        return ea.declined(self.w, npc_id, part, day=ea.game_day(self.w))

    def prepared(self):
        return [data for data in self.w.get("flags", {}).get("economic_offers", {}).values()
                if data["status"] == "prepared"]

    def prepare(self, purpose, npc_id, **fields):
        return ea.prepare_from_turn(self.s, ea.turn_proposal(purpose, npc_id, **fields))

    def prepare_purchase(self, npc_id, key):
        proposal = ea.EconomicProposal(purpose="purchase", recipient_id=npc_id, source_id=npc_id, item_id=key,
                                       count=1, amount_cp=None, tip_cp=0, tender_cp=None, dependency="base_required",
                                       source_action_id="", text_span=None)
        return ea.prepare_from_turn(self.s, proposal)

    def confirm(self, card, action):
        with resolution_action_scope(action, "session"):
            return ea.confirm_offer(ea.EconomicState(world=self.w, character=self.s.character),
                                    offer_id=card["offer_id"], confirmation_digest=card["confirmation_digest"],
                                    operation_id=f"offer:{action}", check=lambda skill, dc: "BAŞARILI")

    def open_counter(self, *, amount=5, keep_change=True, goods="bira"):
        """The counter's offer as a coin line opens it (the decision is the reading's), then the turn ends."""
        self.hold_out("barman", amount, Deal("goods", goods, keep_change))
        try:
            return bold_acts.resolve(self.s, "bir bira, 5 bakır, üstü kalsın")
        finally:
            money_owner.forget_turn(self.s)
            self.s._coin_paid = None

    def counter(self):
        return (self.w.get("flags") or {}).get("counter_offer_v1")

    def money(self):
        return copy.deepcopy((self.w["currency"], self.w.get("inventory"),
                              (self.w.get("flags") or {}).get("economic_ledger")))

    def commit_refused(self, reason, total):
        before = copy.deepcopy(self.w)
        with self.assertRaises(shop_trade.TradeRefused) as raised:
            shop_trade.commit(self.w, "barman", "bira", 1, 0, total)
        self.assertEqual(raised.exception.args[0], reason, total)
        self.assertEqual(self.w, before, total)  # a refusal changes nothing


class TheSchemaAndTheParts(Spoken):
    def test_speech_schema_shows_the_answer_fields_but_requires_none(self):
        schema = game._EXPERIMENTAL_NPC_SPEECH_SCHEMA  # the dict at game.py:7938
        for key in ("coin_answer", "coin_answer_for", "remember_player_line"):
            self.assertIn(key, schema["properties"])
            self.assertNotIn(key, schema["required"])
        names = list(schema["properties"])
        self.assertLess(max(names.index(key) for key in ("coin_answer", "coin_answer_for", "remember_player_line")),
                        names.index("commitment"))  # ahead of commitment: a small model leaves late fields out
        self.assertEqual(schema["properties"]["coin_answer"], {"type": "string", "enum": ["takes", "declines", "none"]})
        self.assertEqual(schema["properties"]["coin_answer_for"]["type"], "string")
        self.assertEqual(schema["properties"]["remember_player_line"], {"type": "boolean"})

    def test_parts_for_lists_what_is_open_to_that_npc(self):
        # The decision: goods bira, keep the change of 5 → the goods and the tip.
        self.hold_out("barman", 5, Deal("goods", "bira", True))
        self.assertEqual(money_owner.parts_for(self.w, self.s, "barman"), ["goods:bira", "tip"])
        self.assertEqual(money_owner.parts_for(self.w, self.s, "osman"), [])  # another person's business is not listed
        money_owner.forget_turn(self.s)
        # The counter's open offer carries the same parts once the decision is gone.
        self.open_counter()
        self.assertEqual(self.counter()["tip_cp"], 1)
        self.assertEqual(money_owner.parts_for(self.w, self.s, "barman"), ["goods:bira", "tip"])
        self.w["flags"].pop("counter_offer_v1")
        # A room card to the barman → ["room"]; an open gift card to Osman → ["gift"].
        self.assertEqual(self.prepare("room", "barman").status, "prepared")
        self.assertEqual(money_owner.parts_for(self.w, self.s, "barman"), ["room"])
        self.assertEqual(self.prepare("gift", "osman", amount_cp=5).status, "prepared")
        self.assertEqual(money_owner.parts_for(self.w, self.s, "osman"), ["gift"])
        # A decision lists its own part; an unclear one lists none; nothing is listed twice.
        self.hold_out("osman", 5, Deal("gift", None, False))
        self.assertEqual(money_owner.parts_for(self.w, self.s, "osman"), ["gift"])
        self.hold_out("osman", 5)  # no deal, and Osman serves nothing: unclear
        self.assertEqual(money_owner.current(self.s).kind, "unclear")
        self.assertEqual(money_owner.parts_for(self.w, self.s, "osman"), ["gift"])  # only the open card's part

    def test_the_answer_is_read_only_from_the_listed_values(self):
        parts = ["gift"]
        for packet, expected in (
                ({"coin_answer": "declines", "coin_answer_for": "gift"}, ("declines", "gift")),
                ({"coin_answer": "takes", "coin_answer_for": "unclear"}, ("takes", "unclear")),
                ({"coin_answer": "declines", "coin_answer_for": "room"}, ("declines", "unclear")),  # not listed
                ({"coin_answer": "declines"}, ("declines", "unclear")),
                ({"coin_answer": "none", "coin_answer_for": "gift"}, ("none", "gift")),
                ({"coin_answer": 7, "coin_answer_for": ["gift"]}, (None, "unclear")),
                ({"coin_answer": "DECLINES"}, (None, "unclear")),
                ({}, (None, "unclear")),
                ("not a packet", (None, "unclear"))):
            with self.subTest(packet=packet):
                money_owner.read_answer(self.s, packet, "osman", parts)
                self.assertEqual((self.s._coin_answer, self.s._coin_answer_for), expected)
                self.assertEqual(self.s._coin_answer_npc, "osman")
        money_owner.forget_turn(self.s)
        self.assertIsNone(self.s._coin_answer)
        self.assertIsNone(self.s._coin_answer_for)
        self.assertIsNone(self.s._coin_answer_npc)


class ASpokenNoStopsItsPart(Spoken):
    def test_a_declined_coin_opens_no_card_and_cancels_open_cards_of_that_part(self):
        # An earlier gift card to Osman is open; now he is held out 5 as a gift again and says no to the gift.
        self.assertEqual(self.prepare("gift", "osman", amount_cp=5).status, "prepared")
        [card] = self.prepared()
        before = self.money()
        result, notes = self.turn("osman", {"coin_answer": "declines", "coin_answer_for": "gift"},
                                  amount=5, deal=Deal("gift", None, False))
        self.assertEqual(self.prepared(), [])  # the open card is cancelled and no new one opens
        self.assertEqual(self.w["flags"]["economic_offers"][card["offer_id"]]["status"], "cancelled")
        self.assertIn(("osman", "Osman az önce parayı geri çevirdi."), notes)
        self.assertTrue(self.declined("osman", "gift"))
        self.assertFalse(self.declined("osman", "tip"))  # only the part named
        self.assertEqual(self.money(), before)
        self.assertNotIn("teklif hazır", result["narration"])
        # Confirming the cancelled card moves nothing; preparing a new one is refused while the decline holds.
        refused = self.confirm(card, "gift-after-no")
        self.assertEqual((refused.status, refused.net_debit_cp), ("refused", 0))
        again = self.prepare("gift", "osman", amount_cp=5)
        self.assertEqual((again.status, again.reason_code), ("refused", "npc_declined"))
        self.assertIn(DECLINED, again.public_message)
        self.assertEqual(self.money(), before)

    def test_a_missing_or_broken_answer_keeps_the_decline(self):
        self.turn("osman", {"coin_answer": "declines", "coin_answer_for": "gift"}, amount=5,
                  deal=Deal("gift", None, False))
        self.assertTrue(self.declined("osman", "gift"))
        for packet in ({}, {"coin_answer": "none"}, {"coin_answer": 7}, {"coin_answer": "takes", "coin_answer_for": 7},
                       {"coin_answer": "takes", "coin_answer_for": "unclear"}, {"coin_answer": "takes"}):
            with self.subTest(packet=packet):
                result, _ = self.turn("osman", packet, amount=5, deal=Deal("gift", None, False))
                self.assertEqual(self.prepared(), [])
                self.assertEqual(self.w["currency"]["player"], 100)
                self.assertEqual(self.w["currency"]["osman"], 0)
                self.assertTrue(self.declined("osman", "gift"))
                self.assertIn("Osman az önce parayı geri çevirdi.", result["narration"])  # the card does not open

    def test_a_tip_only_decline_still_sells_the_goods(self):
        self.open_counter()
        self.assertEqual((self.counter()["tip_cp"], self.counter()["tender_cp"]), (1, 5))
        self.turn("barman", {"coin_answer": "declines", "coin_answer_for": "tip"})
        self.assertNotIn("tip_cp", self.counter())  # tip_cp 0: the tip is gone, the beer's offer stands
        self.assertEqual(self.counter()["tender_cp"], 4)
        self.assertTrue(self.declined("barman", "tip"))
        self.assertFalse(self.declined("barman", "goods:bira"))
        self.commit_refused("price_changed", 5)  # the tip can no longer be paid with the beer
        line = shop_trade.commit(self.w, "barman", "bira", 1, 0, 4)
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["barman"]), (96, 4))
        self.assertEqual([item.get("name") for item in self.w["inventory"]].count("Bira"), 1)
        self.assertNotIn("bahşiş", line)

    def test_an_explicit_room_decline_charges_nothing_on_confirm(self):
        prepared = self.prepare("room", "barman")
        self.assertEqual(prepared.status, "prepared")
        [card] = self.prepared()
        self.assertEqual(card["proposal"]["purpose"], "room")
        self.turn("barman", {"coin_answer": "declines", "coin_answer_for": "room"})
        self.assertEqual(self.w["flags"]["economic_offers"][card["offer_id"]]["status"], "cancelled")
        refused = self.confirm(card, "room-after-no")
        self.assertEqual((refused.status, refused.net_debit_cp), ("refused", 0))
        self.assertEqual(self.w["currency"]["player"], 100)
        self.assertFalse((self.w.get("flags") or {}).get("inn_room"))
        again = self.prepare("room", "barman")
        self.assertEqual((again.status, again.reason_code), ("refused", "npc_declined"))
        self.assertEqual(self.w["currency"]["player"], 100)

    def test_an_unclear_decline_moves_no_payment_to_that_npc(self):
        self.open_counter(amount=0, keep_change=False)  # the beer's offer, no coin on it
        self.assertEqual(self.prepare("room", "barman").status, "prepared")
        [card] = self.prepared()
        before = self.money()
        result, notes = self.turn("barman", {"coin_answer": "declines", "coin_answer_for": "unclear"})
        self.assertEqual(self.w["flags"]["economic_offers"][card["offer_id"]]["status"], "cancelled")
        self.assertIsNone(self.counter())  # the counter's offer is closed
        self.assertIn(("barman", "Marek az önce parayı geri çevirdi."), notes)
        for purpose, fields in (("gift", {"amount_cp": 5}), ("tip", {"amount_cp": 1}), ("room", {})):
            with self.subTest(purpose=purpose):
                answer = self.prepare(purpose, "barman", **fields)
                self.assertEqual((answer.status, answer.reason_code), ("refused", "npc_declined"))
        bought = self.prepare_purchase("barman", "bira")
        self.assertEqual((bought.status, bought.reason_code), ("refused", "npc_declined"))
        self.commit_refused("npc_declined", 4)  # the counter's own trade takes nothing either
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.money(), before)
        # A part the engine did not list for that NPC is an unclear decline too.
        self.turn("osman", {"coin_answer": "declines", "coin_answer_for": "room"}, amount=5,
                  deal=Deal("gift", None, False))
        self.assertTrue(self.declined("osman", "gift"))
        self.assertTrue(self.declined("osman", "tip"))
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.money(), before)

    def test_a_goods_decline_closes_that_offer_and_its_trade(self):
        self.open_counter(amount=0, keep_change=False)
        self.turn("barman", {"coin_answer": "declines", "coin_answer_for": "goods:bira"})
        self.assertIsNone(self.counter())
        self.assertTrue(self.declined("barman", "goods:bira"))
        self.assertFalse(self.declined("barman", "goods:sarap"))
        self.commit_refused("npc_declined", 4)
        bought = self.prepare_purchase("barman", "bira")
        self.assertEqual((bought.status, bought.reason_code), ("refused", "npc_declined"))
        self.assertEqual(self.w["currency"]["player"], 100)

    def test_only_an_explicit_takes_for_that_part_ends_the_decline(self):
        self.turn("osman", {"coin_answer": "declines", "coin_answer_for": "unclear"}, amount=5)
        self.assertTrue(self.declined("osman", "gift"))
        self.assertTrue(self.declined("osman", "tip"))
        # takes + unclear keeps it, whatever the coin is for now.
        self.turn("osman", {"coin_answer": "takes", "coin_answer_for": "unclear"}, amount=5,
                  deal=Deal("tip", None, False))
        self.assertEqual(self.prepared(), [])
        self.assertTrue(self.declined("osman", "tip"))
        # takes + "tip" (listed: the coin is a tip) lifts the tip alone, and the tip card opens in that turn.
        result, _ = self.turn("osman", {"coin_answer": "takes", "coin_answer_for": "tip"}, amount=5,
                              deal=Deal("tip", None, False))
        self.assertFalse(self.declined("osman", "tip"))
        self.assertTrue(self.declined("osman", "gift"))
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["amount_cp"]), ("tip", 5))
        self.assertIn("teklif hazır", result["narration"])
        self.assertEqual(self.w["currency"]["player"], 100)  # the card only waits for its confirmation
        paid = self.confirm(card, "tip-taken")
        self.assertEqual((paid.status, paid.net_debit_cp), ("applied", 5))
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["osman"]), (95, 5))
        gift = self.prepare("gift", "osman", amount_cp=5)
        self.assertEqual((gift.status, gift.reason_code), ("refused", "npc_declined"))

    def test_the_first_npcs_decline_survives_declines_to_thirty_two_others(self):
        day = ea.game_day(self.w)
        for number in range(ea.DECLINE_CAP):
            self.assertEqual(ea.record_decline(self.w, f"npc_{number:02d}", "gift", 5, day=day, turn=1).status,
                             "written")
        before = self.money()
        with self.assertLogs("economic_actions", level="WARNING") as logged:
            self.turn("osman", {"coin_answer": "declines", "coin_answer_for": "gift"}, amount=5,
                      deal=Deal("gift", None, False))
        self.assertTrue(any("decline_cap_full" in line for line in logged.output), logged.output)
        self.assertEqual(self.prepared(), [])  # no card opens that turn, though the decline could not be written
        self.assertEqual(self.money(), before)
        self.assertTrue(ea.declined(self.w, "npc_00", "gift", day=day))
        self.assertEqual(len(self.w["flags"]["money_declined"]), ea.DECLINE_CAP)

    def test_a_tip_decline_drops_both_counter_tips(self):
        # Path A: the tip rides on the offer (tip_cp 1).
        self.open_counter()
        self.assertEqual(self.counter()["tip_cp"], 1)
        self.turn("barman", {"coin_answer": "declines", "coin_answer_for": "tip"})
        self.assertNotIn("tip_cp", self.counter())
        self.assertNotIn("tip_after_cp", self.counter())
        # Path B: the tip waits for after the goods (tip_after_cp 1).
        ea.clear_decline(self.w, "barman", "tip")
        self.w["flags"].pop("counter_offer_v1")
        self.open_counter(amount=4, keep_change=False)
        self.counter()["tip_after_cp"] = 1
        self.assertEqual(money_owner.parts_for(self.w, self.s, "barman"), ["goods:bira", "tip"])
        self.turn("barman", {"coin_answer": "declines", "coin_answer_for": "tip"})
        self.assertNotIn("tip_cp", self.counter())
        self.assertNotIn("tip_after_cp", self.counter())
        self.assertEqual(self.counter()["key"], "bira")  # the beer's offer stands
        self.assertEqual(self.w["currency"]["player"], 100)


class SpeechClient(front_tests.FrontClient):
    """The front reading as scripted, and NPC speech with this turn's answer fields added as written."""

    def __init__(self):
        super().__init__()
        self.answer = {}
        self.speech_schemas = []

    def chat(self, *args, **kwargs):
        properties = (kwargs.get("format") or {}).get("properties") or {}
        if "spoken_text" in properties and "intent" not in properties and "front" not in properties:
            self.chat_calls += 1
            self.speech_schemas.append(copy.deepcopy(kwargs.get("format")))
            self.message_batches.append(kwargs.get("messages", []))
            packet = {"spoken_text": self.narration, "stage_direction": "", **self.answer}
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        return super().chat(*args, **kwargs)


class TheSpeechPathReadsTheAnswer(unittest.IsolatedAsyncioTestCase):
    """Real app and engine, scripted model: the speech call is offered the listed parts and its answer is read."""

    asyncSetUp = front_tests.FrontTable.asyncSetUp
    asyncTearDown = front_tests.FrontTable.asyncTearDown
    campaign_with_npc = front_tests.FrontTable.campaign_with_npc
    open_job = front_tests.FrontTable.open_job
    begin = front_tests.FrontTable.begin
    line = front_tests.FrontTable.line

    async def ready(self):
        await self.begin(kind="hiring")
        self.client = SpeechClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.world.setdefault("currency", {})["player"] = 100

    def prepared(self):
        return [data for data in self.world.get("flags", {}).get("economic_offers", {}).values()
                if data["status"] == "prepared"]

    def declined(self, part):
        return ea.declined(self.world, self.npc["id"], part, day=ea.game_day(self.world))

    async def test_the_speech_call_lists_the_parts_and_a_spoken_no_holds_until_an_explicit_yes(self):
        await self.ready()
        gift = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 5, "deal": "gift"}
        self.client.front = gift
        self.client.answer = {"coin_answer": "declines", "coin_answer_for": "gift", "remember_player_line": False}
        await self.line("bu beş bakır senin, al", "İstemem, sakla onu.")
        schema = self.client.speech_schemas[-1]
        self.assertEqual(schema["properties"]["coin_answer_for"]["enum"], ["gift", "unclear"])
        self.assertNotIn("coin_answer_for", schema["required"])
        prompt = str(self.client.message_batches[-1])
        self.assertIn("`coin_answer_for`: parayı hangi kalem için alıyor ya da reddediyorsun; emin değilsen "
                      "`unclear`.", prompt)
        self.assertEqual(self.prepared(), [])
        self.assertTrue(self.declined("gift"))
        self.assertIsNone(self.session._coin_answer)  # the answer is this turn's only
        self.assertEqual(self.world["currency"]["player"], 100)
        # No answer on the next coin: the decline holds and no card opens.
        self.client.answer = {}
        await self.line("yine de al şu beş bakırı", "Hm.")
        self.assertEqual(self.prepared(), [])
        self.assertTrue(self.declined("gift"))
        # An explicit yes to the gift lifts it, and the Hediye card opens in that turn; nothing is paid yet.
        self.client.answer = {"coin_answer": "takes", "coin_answer_for": "gift"}
        await self.line("peki, al şu beş bakırı", "Peki, sağ ol.")
        self.assertFalse(self.declined("gift"))
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["amount_cp"]), ("gift", 5))
        self.assertEqual(self.world["currency"]["player"], 100)

    async def test_a_line_with_no_coin_offers_only_unclear_and_still_hears_a_no(self):
        await self.ready()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        self.client.answer = {"coin_answer": "declines", "coin_answer_for": "unclear"}
        await self.line("bugün hava nasıl", "Paranı istemem.")
        self.assertEqual(self.client.speech_schemas[-1]["properties"]["coin_answer_for"]["enum"], ["unclear"])
        self.assertTrue(self.declined("gift"))
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.world["currency"]["player"], 100)



from api.tests.journeys.runner import JourneyCase, SCENARIO_DIR
from api.tests.journeys.schema import load_scenario


class SpokenDeclineJourney(JourneyCase):
    async def test_scenario_17_all_six_steps_pass_without_known_broken(self):
        scenario = load_scenario(SCENARIO_DIR / "17_refused_gift_not_charged.json")
        self.assertEqual(len(scenario.steps), 6)
        self.assertTrue(all(not step.known_broken for step in scenario.steps))
        results = await self.run_scenario(scenario)
        self.assertEqual([result.status for result in results], ["pass"] * 6, results)

if __name__ == "__main__":
    unittest.main()
