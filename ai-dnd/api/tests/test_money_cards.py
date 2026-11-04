"""The money owner opens the card its decision names, after the person answered; coin never becomes a silent gift.

`game._tell_the_coin` is a thin wrapper over `money_owner.open_card_after_reply` (design §3a, §12 D29, plan Task 7).
A gift decision opens a Hediye card and a tip decision a Bahşiş card, both for the coin held out and neither paying
anything before its confirmation. Goods, room, a past payment and a bribe open nothing here: the counter, the room
card and the guard's card are their own owners'. An unclear decision opens no card and leaves a note for this turn
only. Coin with no decision of its own opens nothing. No real model is called.
"""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import economic_actions as ea
import game
import money_owner
from api.core_resolution import resolution_action_scope
from money_owner import CoinDecision

UNCLEAR = "ne için olduğu belli değil"


class Cards(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.w = self.s.world_state
        self.here = self.w["location"]
        self.w["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": self.here, "current_hp": 10},
            {"id": "osman", "name": "Osman", "role": "Kervancı", "location": self.here, "current_hp": 10},
            {"id": "guest", "name": "Oren", "role": "Yolcu", "location": self.here, "current_hp": 10},
        ]
        self.w["currency"] = {"player": 100, "barman": 0, "osman": 0, "guest": 0}
        self.s._turn_notes = []
        token = game._ACTIVE_SESSION.set(self.s)  # the engine's helpers below read this session, as a turn does
        self.addCleanup(game._ACTIVE_SESSION.reset, token)
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)

    def npc(self, npc_id):
        return next(npc for npc in self.w["npcs"] if npc["id"] == npc_id)

    def decision(self, kind, npc_id, amount, *, source="model"):
        """What `game._hand_over_coin` leaves for a line that held out coin: the decision and the coin in hand."""
        self.s._coin_decision = CoinDecision(kind, npc_id, amount, 0, None, source, self.here)
        self.s._coin_paid = (amount, self.npc(npc_id) if npc_id else None, self.here)

    def result(self, **action):
        return {"narration": "Başını kaldırıyor.",
                "action_result": {"action": "dialogue", "status": "resolved", "state_changes": [], **action}}

    def prepared(self):
        return [data for data in self.w.get("flags", {}).get("economic_offers", {}).values()
                if data["status"] == "prepared"]

    def labels(self, card):
        state = ea.EconomicState(world=self.w, character=self.s.character)
        return [line.label for line in ea.public_offer(state, ea.offer_from_record(card)).lines]

    def money(self):
        return copy.deepcopy((self.w["currency"], self.w.get("inventory"),
                              self.w.get("flags", {}).get("economic_ledger")))

    def notes(self):
        return [note for note in self.s._turn_notes if UNCLEAR in note[1]]


class TheDecisionNamesTheCard(Cards):
    def test_unclear_coin_opens_no_card_and_notes_it(self):
        self.decision("unclear", "osman", 5)
        game._tell_the_coin(self.result())
        self.assertEqual(self.prepared(), [])
        [(npc_id, text)] = [note for note in self.s._turn_notes if "ne için olduğu belli değil" in note[1]]
        self.assertEqual(npc_id, "osman")  # notes are (npc_id | None, text) pairs (D28)
        self.assertEqual(text, "oyuncu 5 bakır gösterdi, ne için olduğu belli değil; para el değiştirmedi")

    def test_an_unclear_decision_from_the_model_or_from_structure_says_nothing_aloud(self):
        for source in ("model", "structural"):
            with self.subTest(source=source):
                self.s._turn_notes = []
                self.decision("unclear", "osman", 5, source=source)
                result = self.result()
                before = self.money()
                game._tell_the_coin(result)
                self.assertEqual(self.prepared(), [])
                self.assertEqual(result["narration"], "Başını kaldırıyor.")  # no stock "what for?" line (decision 5)
                self.assertEqual(self.money(), before)
                self.assertEqual(len(self.notes()), 1)

    def test_gift_decision_opens_a_hediye_card(self):
        self.decision("gift", "osman", 5)
        result = self.result()
        before = self.money()
        game._tell_the_coin(result)
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["recipient_id"], card["proposal"]["amount_cp"]),
                         ("gift", "osman", 5))
        self.assertEqual(self.labels(card), ["Hediye"])
        self.assertIsNone(card["proposal"]["tender_cp"])
        self.assertEqual(self.money(), before)  # the card only waits; its confirmation alone pays
        self.assertIn("teklif hazır", result["narration"])
        self.assertEqual(self.notes(), [])

    def test_tip_decision_without_an_open_offer_opens_a_bahsis_card(self):
        self.decision("tip", "barman", 3)
        result = self.result()
        before = self.money()
        game._tell_the_coin(result)
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["recipient_id"], card["proposal"]["amount_cp"]),
                         ("tip", "barman", 3))
        self.assertEqual(self.labels(card), ["Bahşiş"])
        self.assertEqual(self.money(), before)
        self.assertIn("teklif hazır", result["narration"])

    def test_the_card_pays_only_on_its_confirmation_and_only_once(self):
        self.decision("tip", "barman", 3)
        game._tell_the_coin(self.result())
        [card] = self.prepared()

        def confirm(action):
            with resolution_action_scope(action, "session"):
                return ea.confirm_offer(ea.EconomicState(world=self.w, character=self.s.character),
                                        offer_id=card["offer_id"], confirmation_digest=card["confirmation_digest"],
                                        operation_id=f"offer:{action}", check=lambda skill, dc: "BAŞARILI")

        paid = confirm("tip-1")
        self.assertEqual((paid.status, paid.net_debit_cp), ("applied", 3))
        again = confirm("tip-2")
        self.assertEqual((again.status, again.reason_code, again.net_debit_cp), ("refused", "offer_not_prepared", 0))
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["barman"]), (97, 3))

    def test_a_coin_with_no_decision_never_becomes_a_gift(self):
        self.s._coin_paid = (5, self.npc("guest"), self.here)
        self.s.run_player_turn("/item list")
        self.assertEqual(self.prepared(), [])

    def test_coin_with_no_decision_opens_nothing_and_says_nothing(self):
        self.s._coin_decision = None
        self.s._coin_paid = (5, self.npc("osman"), self.here)
        result = self.result()
        before = self.money()
        game._tell_the_coin(result)
        self.assertEqual(self.prepared(), [])
        self.assertEqual(result["narration"], "Başını kaldırıyor.")
        self.assertEqual(self.money(), before)
        self.assertEqual(self.notes(), [])

    def test_goods_room_a_past_payment_and_a_bribe_open_no_card_here(self):
        # The counter, the room card and the guard's card are opened by their own owners, never as a gift.
        for kind in ("goods", "room", "paid_before", "bribe"):
            with self.subTest(kind=kind):
                self.decision(kind, "barman", 50)
                result = self.result()
                before = self.money()
                game._tell_the_coin(result)
                self.assertEqual(self.prepared(), [])
                self.assertEqual(result["narration"], "Başını kaldırıyor.")
                self.assertEqual(self.money(), before)
                self.assertEqual(self.notes(), [])

    def test_a_decision_about_other_coin_opens_nothing(self):
        # A decision left from an earlier line never names a card for coin this line held out to someone else.
        for paid in ((7, "osman"), (5, "guest")):
            with self.subTest(paid=paid):
                self.s._coin_decision = CoinDecision("gift", "osman", 5, 0, None, "model", self.here)
                self.s._coin_paid = (paid[0], self.npc(paid[1]), self.here)
                game._tell_the_coin(self.result())
                self.assertEqual(self.prepared(), [])

    def test_a_decision_with_no_coin_in_hand_opens_nothing(self):
        # Coin a room or the counter already took off the hand (or a turn already over) opens no second card.
        self.s._coin_decision = CoinDecision("gift", "osman", 5, 0, None, "model", self.here)
        self.s._coin_paid = None
        game._tell_the_coin(self.result())
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.notes(), [])

    def test_coin_the_room_or_the_counter_read_is_theirs(self):
        for action in ({"coin_seen_by": "room"}, {"coin_seen_by": "purchase"}, {"action": "shop_offer"}):
            with self.subTest(action=action):
                self.decision("gift", "barman", 5)
                game._tell_the_coin(self.result(**action))
                self.assertEqual(self.prepared(), [])

    def test_coin_whose_taker_stayed_behind_goes_back_with_a_note(self):
        self.decision("gift", "osman", 5)
        self.w["location"] = next(place for place in self.w["locations"] if place != self.here)
        result = self.result()
        game._tell_the_coin(result)
        self.assertEqual(self.prepared(), [])
        self.assertIn(game.COIN_LEFT_BEHIND, result["narration"])
        self.assertEqual(game.COIN_LEFT_BEHIND, money_owner.COIN_LEFT_BEHIND)

    def test_coin_held_out_to_nobody_named_asks_who_and_opens_nothing(self):
        self.decision("unclear", None, 5)
        result = self.result()
        game._tell_the_coin(result)
        self.assertEqual(self.prepared(), [])
        self.assertIn(ea._CLARIFY["npc_unknown"], result["narration"])
        self.assertEqual([note[0] for note in self.notes()], [None])

    def test_the_wrapper_takes_the_coin_off_the_hand(self):
        self.decision("gift", "osman", 5)
        self.s._counter_held = self.npc("barman")
        game._tell_the_coin(self.result())
        self.assertIsNone(self.s._coin_paid)
        self.assertIsNone(self.s._counter_held)
        game._tell_the_coin(self.result())  # the same decision again: no coin in hand, no second card
        self.assertEqual(len(self.prepared()), 1)

    def test_a_failed_prepare_still_takes_the_coin_off_the_hand(self):
        self.decision("gift", "osman", 5)
        with patch.object(ea, "prepare_from_turn", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                game._tell_the_coin(self.result())
        self.assertIsNone(self.s._coin_paid)
        self.assertIsNone(self.s._counter_held)


class TheReadingWritesWhatTheCardReads(Cards):
    """`_hand_over_coin` writes the decision from the reading's deal; the card after the reply reads that decision."""

    def hand_over(self, front, amount=5, who="osman"):
        listed = {"speaking_with": None, "people": [{"id": who}], "goods": []}
        self.s._front_coin = amount
        game._hand_over_coin({"kind": "speak_to", "id": who}, listed, front)
        game._tell_the_coin(self.result())

    def test_no_deal_to_someone_who_does_not_serve_opens_nothing(self):
        self.hand_over({"kind": "speak_to", "person_id": "osman", "coin_cp": 5})
        self.assertEqual(money_owner.current(self.s).kind, "unclear")
        self.assertEqual(self.prepared(), [])
        self.assertEqual([note[0] for note in self.notes()], ["osman"])

    def test_a_gift_deal_opens_the_hediye_card(self):
        self.hand_over({"kind": "speak_to", "person_id": "osman", "coin_cp": 5, "deal": "gift"})
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["amount_cp"]), ("gift", 5))
        self.assertEqual(self.labels(card), ["Hediye"])

    def test_a_tip_deal_opens_the_bahsis_card(self):
        self.hand_over({"kind": "speak_to", "person_id": "barman", "coin_cp": 3, "deal": "tip"}, 3, "barman")
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["amount_cp"]), ("tip", 3))
        self.assertEqual(self.labels(card), ["Bahşiş"])

    def test_a_past_payment_opens_nothing(self):
        self.hand_over({"kind": "speak_to", "person_id": "barman", "coin_cp": 5, "deal": "paid_before"}, 5, "barman")
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.notes(), [])
        self.assertEqual(self.w["currency"]["player"], 100)


class TheSpeechNoteReadsTheDecision(Cards):
    def note(self, npc_id):
        return game._experimental_speech_note(self.w, self.npc(npc_id), None, "al şunu")

    def test_coin_waiting_for_a_card_is_told_to_its_person_as_not_yet_theirs(self):
        for kind in ("gift", "tip", "room", "goods"):
            with self.subTest(kind=kind):
                self.decision(kind, "osman", 5)
                note = self.note("osman")
                self.assertIn("Oyuncu sana 5 bakır uzatıyor; para henüz sende değil", note)
                self.assertNotIn("artık sende", note)
                self.assertNotIn("bakır uzatıyor", self.note("guest"))  # nobody else hears of it

    def test_coin_in_hand_with_no_decision_is_not_told(self):
        self.s._coin_decision = None
        self.s._coin_paid = (5, self.npc("osman"), self.here)
        self.assertNotIn("bakır uzatıyor", self.note("osman"))

    def test_unclear_coin_is_told_as_shown_for_no_known_reason(self):
        self.decision("unclear", "osman", 5)
        note = self.note("osman")
        self.assertIn("Oyuncu sana 5 bakır gösterdi, ne için olduğu belli değil; para el değiştirmedi.", note)
        self.assertNotIn("bakır uzatıyor", note)
        self.assertNotIn("kartı onaylarsa", note)  # no card opens for it

    def test_a_past_payment_and_a_bribe_are_no_coin_held_out_now(self):
        for kind in ("paid_before", "bribe"):
            with self.subTest(kind=kind):
                self.decision(kind, "osman", 5)
                note = self.note("osman")
                self.assertNotIn("bakır uzatıyor", note)
                self.assertNotIn("bakır gösterdi", note)


if __name__ == "__main__":
    unittest.main()
