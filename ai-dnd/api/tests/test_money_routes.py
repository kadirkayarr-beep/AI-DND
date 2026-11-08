"""The room and the counter read the money owner's decision, and one turn's coin goes to one card (plan Task 8).

Design §12 D29 and §3a: a `room` decision opens the room card and a `goods` decision the counter's offer for those
goods, whatever the words and whichever the source (the model's deal or the engine's structure). A `gift`, `tip`,
`paid_before`, `bribe` or `unclear` decision skips the room and the counter, and the words are not read. The old word
path runs only when there is no decision at all (no coin and no deal). The coin held out this turn is handed once,
to the one operation the decision names (`money_owner.claim`, D5).

Real app, real adapter, real engine; only the model is scripted (the journey harness's client). No real model call.
"""

from __future__ import annotations

import copy
import json
import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import bold_acts
import front_proposal
import money_owner
from api.tests.journeys import runner
from money_owner import CoinDecision

ROOM_CARD = {"max_total_cp": 50, "kalemler": ["Oda (bir gece)"]}
SETUP = {
    "npcs": [{"id": "barman", "name": "Marek", "role": "Barmen", "current_hp": 10},
             {"id": "osman", "name": "Osman", "role": "Kervancı", "current_hp": 10}],
    "currency": {"player": 100, "barman": 0, "osman": 0},
    "inventory": [],
    "seed": 7,
}


class RouteClient(runner.ScriptedClient):
    """The journey harness's scripted model, with the front reading set per line through `front`."""

    def __init__(self):
        super().__init__({})
        self.front: dict = {}

    def _front(self) -> dict:
        return {**super()._front(), **copy.deepcopy(self.front)}


class Routes(runner.JourneyCase):
    setup = SETUP

    async def asyncSetUp(self):
        await super().asyncSetUp()
        campaign = await self._journey_campaign(self.setup)
        runner.apply_setup(self, campaign, self.setup)
        self.session_id = campaign["session_id"]
        self.session = self.manager.get(self.session_id).game_session
        self.world = self.session.world_state
        self.enterContext(patch.dict(os.environ, {front_proposal.FLAG: "1"}))
        self.enterContext(patch("socket.socket.connect",
                                side_effect=AssertionError("External network is disabled in these tests.")))
        self.client = RouteClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))

    async def line(self, message, *, to=None):
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if to is not None:
            body.update(interaction_mode="say", target_id=to)
        response = await self.http.post(f"/api/game/sessions/{self.session_id}/turn", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.unexpected, [])
        return response.json()

    def cards(self):
        return [data for data in self.world.get("flags", {}).get("economic_offers", {}).values()
                if data["status"] == "prepared"]

    def card(self):
        return runner.read_observed(self, self.session_id)["kart"]

    def counter(self):
        return runner._counter_offer(self.world)

    def counter_tender(self):
        return (self.world.get("flags", {}).get("counter_offer_v1") or {}).get("tender_cp")

    def purse(self):
        return self.world["currency"]["player"]

    async def open_the_counter(self):
        """A beer asked for with no coin and no deal: the word path opens the barman's counter offer."""
        self.client.front = {"kind": "speak_to", "person_id": "barman"}
        await self.line("bir bira alayım")
        self.assertEqual(self.counter()["key"], "bira")
        self.assertIsNone(self.counter_tender())


class TheDecisionOpensTheOffer(Routes):
    async def test_a_model_room_deal_opens_the_room_card_without_room_words(self):
        self.client.front = {"kind": "speak_to", "person_id": "barman", "deal": "room"}
        await self.line("Bu gece burada kalayım")
        self.assertEqual({key: self.card()[key] for key in ROOM_CARD}, ROOM_CARD)
        [card] = self.cards()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["tender_cp"]), ("room", None))
        self.assertEqual(self.purse(), 100)

    async def test_a_model_goods_deal_opens_the_counter_without_buy_words(self):
        self.client.front = {"kind": "speak_to", "person_id": "barman", "deal": "goods", "deal_goods": "bira"}
        await self.line("bir bira alabilir miyim")
        self.assertEqual(self.counter()["key"], "bira")
        self.assertIsNone(self.counter_tender())  # opening an offer is not holding out coin (D29)
        self.assertEqual(self.cards(), [])
        self.assertEqual(self.purse(), 100)

    async def test_deal_gift_with_a_room_word_opens_one_gift_card(self):
        # The line names the coin: the reading's coin_cp counts only when the player's own words hand coin (Task 5).
        self.client.front = {"kind": "speak_to", "person_id": "barman", "coin_cp": 50, "deal": "gift"}
        await self.line("oda için değil, bu elli bakır senin, al")
        self.assertEqual([c["proposal"]["purpose"] for c in self.cards()], ["gift"])
        self.assertEqual(self.cards()[0]["proposal"]["amount_cp"], 50)
        self.assertIsNone(self.counter())
        self.assertEqual(self.purse(), 100)

    async def test_without_a_decision_the_word_path_is_unchanged(self):
        # Merged with D0 (2026-11-08): in a turn whose reading was obtained, room words are never read (the reading's
        # own `deal` or `economic_intent` decides); the old word path is what runs when there is no reading at all.
        self.enterContext(patch.dict(os.environ, {front_proposal.FLAG: "0"}))
        await self.line("bi oda tutayım usta")
        self.assertIsNone(money_owner.current(self.session))
        self.assertEqual({key: self.card()[key] for key in ROOM_CARD}, ROOM_CARD)
        self.assertEqual(self.purse(), 100)

    async def test_a_failed_model_deal_with_a_room_word_opens_no_card(self):
        self.client.front = {"kind": "speak_to", "person_id": "osman", "coin_cp": 50, "deal": "goods", "deal_goods": "bira"}
        await self.line("oda için şu elli bakırı al")
        self.assertEqual((money_owner.current(self.session).kind, money_owner.current(self.session).source),
                         ("unclear", "model"))
        self.assertEqual(self.cards(), [])
        self.assertIsNone(self.counter())
        self.assertEqual(self.purse(), 100)

    async def test_an_unclear_decision_never_reopens_the_word_path(self):
        # Five coppers to the barman with no deal: no open offer, too little for a room, so unclear (structural).
        self.client.front = {"kind": "speak_to", "person_id": "barman", "coin_cp": 5}
        await self.line("şu beş bakırı al, bir bira alayım")
        self.assertEqual((money_owner.current(self.session).kind, money_owner.current(self.session).source),
                         ("unclear", "structural"))
        self.assertIsNone(self.counter())
        self.assertEqual(self.cards(), [])
        # A goods deal for someone who sells nothing: unclear from the model, and the barman's counter stays shut.
        self.client.front = {"kind": "speak_to", "person_id": "osman", "coin_cp": 5, "deal": "goods", "deal_goods": "bira"}
        await self.line("şu beş bakırı al, bir bira alayım")
        self.assertEqual((money_owner.current(self.session).kind, money_owner.current(self.session).source),
                         ("unclear", "model"))
        self.assertIsNone(self.counter())
        self.assertEqual(self.cards(), [])
        self.assertEqual(self.purse(), 100)

    async def test_a_room_decision_said_straight_to_the_server_opens_the_room_card(self):
        # Say mode runs no bold_acts.resolve; the counter's say-mode entry obeys the same decision.
        self.client.front = {"kind": "speak_to", "person_id": "barman", "coin_cp": 50}
        await self.line("Oda için beş gümüş ödüyorum", to="barman")
        self.assertEqual(money_owner.current(self.session).kind, "room")
        [card] = self.cards()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["tender_cp"]), ("room", 50))
        self.assertEqual(self.purse(), 100)


class OneAmountOneOperation(Routes):
    async def test_one_amount_is_owned_by_one_operation(self):
        await self.open_the_counter()
        self.client.front = {"kind": "speak_to", "person_id": "barman", "coin_cp": 50, "deal": "room"}
        await self.line("şu elli bakırı al")
        [card] = self.cards()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["tender_cp"]), ("room", 50))
        self.assertEqual(self.counter()["key"], "bira")
        self.assertIsNone(self.counter_tender())  # the counter never saw the room's coin
        self.assertEqual(self.purse(), 100)

    async def test_a_gift_to_a_server_with_an_open_offer_is_the_gift_card_not_the_counters_tender(self):
        await self.open_the_counter()
        self.client.front = {"kind": "speak_to", "person_id": "barman", "coin_cp": 5, "deal": "gift"}
        await self.line("bu beş bakır senin")
        self.assertEqual([(c["proposal"]["purpose"], c["proposal"]["amount_cp"]) for c in self.cards()], [("gift", 5)])
        self.assertIsNone(self.counter_tender())
        self.assertEqual(self.purse(), 100)

    async def test_coin_for_the_open_offer_with_no_deal_is_still_its_tender(self):
        # Structure (no deal from the model): the open counter offer's tender, as before.
        await self.open_the_counter()
        self.client.front = {"kind": "speak_to", "person_id": "barman", "coin_cp": 5}
        await self.line("al şu beş bakırı")
        self.assertEqual((money_owner.current(self.session).kind, money_owner.current(self.session).source),
                         ("goods", "structural"))
        self.assertEqual((self.counter()["key"], self.counter_tender()), ("bira", 5))
        self.assertEqual(self.cards(), [])
        self.assertEqual(self.purse(), 100)


# No sleep word here: the bed half stops at the card (or its absence), and no rest is run in this bare session.
WALK_TO_ROOM = "hana gidip oda tutayım, şu elli bakırı al"


class AWalkToBedObeysTheDecision(unittest.TestCase):
    """`game._sleep_after_walk` reads a bed line through `bold_acts.take_room` once the walk has moved the player.
    Under a decision the room words are not read (D29): only a `room` decision opens the room card, with the person
    it names; a gift, tip, past payment, bribe or unclear decision opens none, and the coin stays for its own owner."""

    def setUp(self):
        import game
        self.game = game
        self.s = game.create_session()
        self.w = self.s.world_state
        self.w["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": self.w["location"], "current_hp": 10},
            {"id": "osman", "name": "Osman", "role": "Kervancı", "location": self.w["location"], "current_hp": 10},
        ]
        self.w["currency"] = {"player": 500, "barman": 0, "osman": 0}
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)

    def walk(self, kind, line=WALK_TO_ROOM, *, npc="barman"):
        self.s._economic_turn_key = f"walk-to-bed-{kind}"
        self.s._coin_decision = CoinDecision(kind, npc, 50, 0, None, "model", self.w["location"])
        self.s._coin_claimed = False
        person = next(p for p in self.w["npcs"] if p["id"] == npc)
        self.s._coin_paid = (50, person, self.w["location"])
        walked = {"narration": "Hana giriyorsun.", "action_result": {"action": "move", "status": "completed",
                                                                     "state_changes": ["location"]}}
        self.game._sleep_after_walk(walked, line, "the-street", None, session=self.s)
        return walked

    def prepared(self):
        return [data for data in self.w.get("flags", {}).get("economic_offers", {}).values()
                if data["status"] == "prepared"]

    def test_a_decision_other_than_room_opens_no_room_card(self):
        for kind in ("gift", "tip", "paid_before", "bribe", "unclear"):
            with self.subTest(kind=kind):
                self.setUp()
                walked = self.walk(kind)
                self.assertEqual(self.prepared(), [])
                self.assertNotIn("coin_seen_by", walked["action_result"])
                self.assertIsNotNone(self.s._coin_paid)  # the coin is not the room's: it stays for its own owner
                self.assertIs(self.s._coin_claimed, False)
                self.assertEqual(self.w["currency"]["player"], 500)

    def test_a_room_decision_opens_the_room_card_without_room_words(self):
        self.walk("room", "hana gidip şu elli bakırı al")
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["tender_cp"]), ("room", 50))
        self.assertEqual(self.w["currency"]["player"], 500)


class AWalkToBedThroughTheTurn(Routes):
    """The whole turn: the player walks back into the inn with coin and a goods deal for someone who sells
    nothing. The decision is unclear (model), and the bed line's room words open no card on arrival (D29)."""

    setup = {**json.loads((runner.SCENARIO_DIR / "07_leave_room.json").read_text(encoding="utf-8"))["setup"],
             "npcs": SETUP["npcs"], "currency": SETUP["currency"]}

    async def test_a_failed_model_deal_on_a_walk_to_bed_opens_no_room_card(self):
        inn = self.world["location"]
        with patch.dict(os.environ, {front_proposal.FLAG: "0"}):
            out = await self.line("dışarı çıkıyorum")
        self.assertNotEqual(self.world["location"], inn, out.get("narration"))
        self.client.front = {"kind": "go_to", "place_id": inn, "inside": True, "person_id": "osman",
                             "coin_cp": 50, "deal": "goods", "deal_goods": "bira"}
        out = await self.line("hana gidip oda tutup uyuyorum, şu elli bakırı al")
        self.assertEqual(self.world["location"], inn, out.get("narration"))  # the walk moved the player: the bed half was read
        decision = money_owner.current(self.session)
        self.assertEqual((decision.kind, decision.source), ("unclear", "model"))
        self.assertEqual(self.cards(), [])
        self.assertEqual(self.purse(), 100)


class TheClaim(unittest.TestCase):
    def session(self, kind, amount):
        here = "fr:somewhere"
        return SimpleNamespace(_coin_decision=CoinDecision(kind, "barman", amount, 0, None, "model", here),
                               _coin_claimed=False, _coin_paid=(amount, {"id": "barman"}, here), _handed_note=None)

    def test_claim_hands_the_coin_to_one_purpose_once(self):
        session = self.session("room", 50)
        self.assertEqual(money_owner.claim(session, "room"), 50)
        self.assertIs(session._coin_claimed, True)
        self.assertIsNone(money_owner.claim(session, "room"))
        self.assertIsNone(money_owner.claim(session, "goods"))

    def test_claim_gives_nothing_to_another_purpose_or_without_a_decision(self):
        session = self.session("goods", 5)
        self.assertIsNone(money_owner.claim(session, "room"))
        self.assertIs(session._coin_claimed, False)
        self.assertEqual(money_owner.claim(session, "goods"), 5)
        for kind in ("gift", "tip", "paid_before", "bribe", "unclear"):
            with self.subTest(kind=kind):
                other = self.session(kind, 5)
                self.assertIsNone(money_owner.claim(other, "room"))
                self.assertIsNone(money_owner.claim(other, "goods"))
                self.assertIs(other._coin_claimed, False)
        self.assertIsNone(money_owner.claim(SimpleNamespace(), "room"))

    def test_an_offer_asked_for_with_no_coin_claims_no_tender(self):
        self.assertIsNone(money_owner.claim(self.session("room", 0), "room"))

    def test_held_out_coin_under_a_decision_is_the_claim(self):
        session = self.session("room", 50)
        self.assertIsNone(bold_acts.held_out_coin(session, "goods"))
        self.assertIsNotNone(session._coin_paid)  # not the counter's coin: it stays for its own owner
        self.assertEqual(bold_acts.held_out_coin(session, "room"), 50)
        self.assertIsNone(session._coin_paid)
        self.assertIsNone(bold_acts.held_out_coin(session, "room"))


if __name__ == "__main__":
    unittest.main()
