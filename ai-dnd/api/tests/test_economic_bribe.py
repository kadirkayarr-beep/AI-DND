"""A4: coin held out to the guard making an arrest opens a bribe card; only its confirmation rolls the word (C8, O1).

The first bribe card of a hold pauses that turn's escalation; a second bribe in the same hold does not, and when
the guard's patience is spent the fight starts and no card is prepared at all. A card left open is cancelled at
the next ordinary turn. Coin handed to someone else during an arrest is no bribe. No real model is called.
"""

from __future__ import annotations

import copy
import unittest
import uuid
from unittest.mock import patch

import bold_acts
import campaign_time
import economic_actions as ea
import game
import world_reactions
from api.serializers import serialize_session_state
from api.tests.test_economic_action_http import EconomicHttpFixture


def bribe_cards(world):
    return [data for data in world.get("flags", {}).get("economic_offers", {}).values()
            if any(effect["kind"] == "bribe_accepted" for effect in data["on_accept"])]


class Arrest(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.w = self.s.world_state
        self.here = self.w["location"]
        self.w["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": self.here, "current_hp": 10},
            {"id": "guard", "name": "Çavuş Hale", "role": "Muhafız", "location": self.here, "current_hp": 10},
        ]
        self.w["currency"] = {"player": 500, "barman": 0, "guard": 0}
        self.w.setdefault("flags", {})["turn_index"] = 10
        campaign_time.initialize(self.w)
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)

    def held(self, *, since=0):
        deed = {"kind": "theft", "at": 120, "location": self.here, "text": "Tezgâhtan kese çalındı",
                "described": ["guard"], "witnesses": [], "told": [], "heard": [], "seen_near": [],
                "challenged": ["guard"],
                "hold": {"guard": "guard", "place": self.here, "turn": self.w["flags"]["turn_index"] - since,
                         "arrest": True}}
        self.w["flags"].setdefault("deeds", []).append(deed)
        return deed

    def deed(self):
        """The arrest as the world holds it now: a turn may swap the world's dicts for committed copies."""
        return self.w["flags"]["deeds"][-1]

    def offers(self):
        return self.w.get("flags", {}).get("economic_offers", {})

    def prepared(self):
        return [data for data in self.offers().values() if data["status"] == "prepared"]

    def held_out(self, amount, line="/item list"):
        self.s._bribe_held_out = amount
        return self.s.run_player_turn(line)

    def fighting(self):
        return bool(self.w.get("combat", {}).get("active"))

    def counting(self, name):
        calls = []
        real = getattr(world_reactions, name)
        return calls, patch.object(world_reactions, name, side_effect=lambda *a, **k: (calls.append(1), real(*a, **k))[1])


class TheBribeCard(Arrest):
    def test_guard_bribe_opens_card_no_debit(self):
        deed = self.held()
        self.assertTrue(world_reactions.refuses(self.w, self.w["npcs"][1]))
        before = copy.deepcopy(self.w["currency"])
        result = self.held_out(100)
        self.assertEqual(self.w["currency"], before)
        [card] = bribe_cards(self.w)
        self.assertEqual((card["status"], card["proposal"]["recipient_id"], card["proposal"]["amount_cp"]),
                         ("prepared", "guard", 100))
        self.assertIn("hold", self.deed())
        self.assertIn("100 bakır", result["narration"])
        del deed

    def test_bribe_card_turn_does_not_escalate(self):
        deed = self.held(since=world_reactions.ARREST_PATIENCE + 3)
        forced, spy = self.counting("_force")
        with spy:
            self.held_out(100)
        self.assertEqual(forced, [])
        self.assertFalse(self.fighting())
        self.assertIs(self.deed()["hold"]["bribe_card_opened"], True)
        self.assertEqual(len(bribe_cards(self.w)), 1)
        del deed

    def test_second_bribe_in_same_hold_does_not_pause_escalation(self):
        deed = self.held(since=world_reactions.ARREST_PATIENCE + 3)
        self.held_out(100)
        [first] = bribe_cards(self.w)
        purse = self.w["currency"]["player"]
        prepares = []
        real = ea.prepare_from_turn
        with patch.object(ea, "prepare_from_turn", side_effect=lambda *a, **k: (prepares.append(1), real(*a, **k))[1]):
            result = self.held_out(100)
        self.assertTrue(self.fighting(), result["narration"])
        self.assertEqual(prepares, [])
        self.assertEqual(self.offers()[first["offer_id"]]["status"], "cancelled")
        self.assertEqual(len(self.offers()), 1)
        self.assertEqual(self.w["currency"]["player"], purse)
        self.assertNotIn("teklif hazır", result["narration"])
        self.assertIsNone(serialize_session_state(self.s)["economic_offer"])
        self.assertNotIn("hold", self.deed())
        del deed

    def test_second_bribe_without_force_opens_card_and_still_presses(self):
        deed = self.held(since=0)
        deed["hold"]["bribe_card_opened"] = True
        pressed, spy = self.counting("_press")
        with spy:
            self.held_out(100)
        self.assertEqual(len(pressed), 1)
        self.assertFalse(self.fighting())
        self.assertEqual(len(self.prepared()), 1)
        lines, done = None, None
        self.s._bribe_held_out = 100
        token = game._ACTIVE_SESSION.set(self.s)
        try:
            lines, done = world_reactions._settle_the_law(self.s, {"action_result": {}})
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertIs(done, True)
        self.assertTrue(lines)

    def test_settle_the_law_returns_law_done_flag(self):
        result = {"action_result": {}}
        token = game._ACTIVE_SESSION.set(self.s)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)
        self.assertEqual(world_reactions._settle_the_law(self.s, result), ([], False))  # nobody is arresting
        deed = self.held()
        self.s._bribe_held_out = 0
        self.assertEqual(world_reactions._settle_the_law(self.s, result), ([], False))
        self.s._bribe_held_out = 100
        lines, done = world_reactions._settle_the_law(self.s, result)
        self.assertTrue(lines)
        self.assertIs(done, True)
        self.assertIs(deed["hold"]["bribe_card_opened"], True)
        for status, reason in (("refused", "npc_refuses"), ("clarification", "purse_below_base")):
            with self.subTest(status=status):
                deed["hold"].pop("bribe_card_opened", None)
                answer = ea.PrepareResult(status=status, offer=None, reason_code=reason, public_message="Olmaz.")
                self.s._bribe_held_out = 100
                with patch.object(ea, "prepare_from_turn", return_value=answer):
                    self.assertEqual(world_reactions._settle_the_law(self.s, result), (["Olmaz."], False))
                self.assertNotIn("bribe_card_opened", deed["hold"])
                pressed, spy = self.counting("_press")
                self.s._bribe_held_out = 100
                with spy, patch.object(ea, "prepare_from_turn", return_value=answer):
                    world_reactions.answer(self.s, {"narration": "", "action_result": {}})
                self.assertEqual(len(pressed), 1)
        self.s._bribe_held_out = 0
        self.s._front_deed = "yield"
        self.s._adventure_player_text = "tamam teslim oluyorum"
        lines, done = world_reactions._settle_the_law(self.s, result)
        self.assertTrue(lines)
        self.assertIs(done, True)

    def test_bribe_clarification_does_not_pause_escalation(self):
        deed = self.held()
        self.w["currency"]["player"] = 50
        pressed, spy = self.counting("_press")
        with spy:
            result = self.held_out(100)
        self.assertEqual(self.prepared(), [])
        self.assertIn(ea._CLARIFY["purse_below_base"], result["narration"])
        self.assertEqual(len(pressed), 1)
        self.assertNotIn("bribe_card_opened", self.deed().get("hold", {}))
        del deed

    def test_next_turn_escalates_and_cancels_open_bribe_card(self):
        self.held(since=world_reactions.ARREST_PATIENCE + 3)
        self.held_out(100)
        [card] = bribe_cards(self.w)
        self.assertFalse(self.fighting())
        result = self.held_out(0)
        self.assertEqual(self.offers()[card["offer_id"]]["status"], "cancelled")
        self.assertTrue(self.fighting(), result["narration"])

    def test_coin_to_innkeeper_under_arrest_is_not_bribe(self):
        deed = self.held()
        self.s._front_coin = 5
        listed = {"speaking_with": None, "people": [{"id": "barman"}, {"id": "guard"}]}
        token = game._ACTIVE_SESSION.set(self.s)
        try:
            game._hand_over_coin({"kind": "speak_to", "id": "barman"}, listed)
            self.assertEqual(getattr(self.s, "_bribe_held_out", 0), 0)
            amount, person, place = self.s._coin_paid
            self.assertEqual((amount, person["id"], place), (5, "barman", self.here))
        finally:
            game._ACTIVE_SESSION.reset(token)
        pressed, spy = self.counting("_press")
        with spy:
            result = self.s.run_player_turn("hancıya 5 bakır verip oda tutuyorum")
        self.assertEqual(len(pressed), 1)
        self.assertEqual(bribe_cards(self.w), [])
        self.assertNotIn("bribe_card_opened", self.deed()["hold"])
        del deed
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["tender_cp"]), ("room", None))
        self.assertIn(bold_acts.COIN_NOT_TENDERED, result["narration"])
        # Coin held out with nobody named goes to the guard's word.
        self.s._coin_paid = None
        self.s._front_coin = 5
        token = game._ACTIVE_SESSION.set(self.s)
        try:
            game._hand_over_coin({"kind": "attempt"}, listed)
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertEqual(self.s._bribe_held_out, 5)
        self.assertIsNone(self.s._coin_paid)


class BribeConfirmations(EconomicHttpFixture):
    async def open_bribe(self, amount=100):
        self.hold_by_guard()
        session = self.record.game_session
        session._bribe_held_out = amount
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            session.run_player_turn("/item list")
        self.save()
        [card] = bribe_cards(self.world)
        return {"offer_id": card["offer_id"], "confirmation_digest": card["confirmation_digest"]}

    def checks(self, result):
        calls = []
        return calls, patch.object(bold_acts, "_check",
                                   side_effect=lambda *a, **k: (calls.append(a[1:]), {"result": result})[1])

    async def test_bribe_failed_check_zero_delta(self):
        card = await self.open_bribe()
        before = copy.deepcopy((self.world["currency"], self.world.get("inventory")))
        calls, rolled = self.checks("BAŞARISIZ")
        with rolled:
            answer, _ = await self.confirm(card)
        self.assertEqual((answer["economic_resolution"]["status"], answer["economic_resolution"]["reason_code"]),
                         ("refused", "check_failed"))
        self.assertEqual((self.world["currency"], self.world.get("inventory")), before)
        self.assertEqual(answer["economic_resolution"]["net_debit_cp"], 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("hold", self.world["flags"]["deeds"][-1])

    async def test_bribe_success_releases_hold_once(self):
        card = await self.open_bribe()
        calls, rolled = self.checks("BAŞARILI")
        with rolled:
            answer, body = await self.confirm(card)
            self.assertEqual(answer["economic_resolution"]["status"], "applied")
            self.assertEqual((self.purse(), self.world["currency"]["guard"]), (0, 100))
            self.assertNotIn("hold", self.world["flags"]["deeds"][-1])
            paid = self.money()
            replay = await self.post(body)
            self.assertEqual(replay.json(), answer)
            again, _ = await self.confirm(card)
        self.assertEqual(again["economic_resolution"]["reason_code"], "offer_not_prepared")
        self.assertEqual(self.money(), paid)
        self.assertEqual(len(calls), 1)

    async def test_failed_bribe_cannot_be_reconfirmed(self):
        card = await self.open_bribe()
        calls, rolled = self.checks("BAŞARISIZ")
        with rolled:
            await self.confirm(card)
            stored = self.offers()[card["offer_id"]]
            self.assertEqual(stored["status"], "consumed")
            self.assertTrue(stored["operation_id"])
            purse, hold = self.purse(), copy.deepcopy(self.world["flags"]["deeds"][-1].get("hold"))
            again, _ = await self.confirm(card, action_id=str(uuid.uuid4()))
        self.assertEqual(again["economic_resolution"]["reason_code"], "offer_not_prepared")
        self.assertEqual(len(calls), 1)
        self.assertEqual((self.purse(), self.world["flags"]["deeds"][-1].get("hold")), (purse, hold))

    async def test_consuming_confirm_counts_toward_arrest_patience(self):
        deed = self.hold_by_guard()
        turn = self.world["flags"].get("turn_index", 0)
        # Patience is two turns: the free turn alone would make it one; the consuming confirm is the other.
        deed["hold"]["turn"] = turn
        self.save()
        pressed = []
        real_press = world_reactions._press
        with patch.object(world_reactions, "_press", side_effect=lambda *a, **k: (pressed.append(1), real_press(*a, **k))[1]):
            card = await self.card(purpose="tip", recipient_id="barman", amount_cp=4)
            refused, _ = await self.confirm({"offer_id": "0" * 32, "confirmation_digest": "0" * 64})
            self.assertEqual(refused["economic_resolution"]["reason_code"], "offer_not_prepared")
            self.assertEqual(self.world["flags"].get("turn_index", 0), turn)
            answer, _ = await self.confirm(card)
            self.assertEqual(answer["economic_resolution"]["status"], "applied")
            self.assertEqual(self.world["flags"]["turn_index"], turn + 1)
            self.assertEqual(pressed, [])
            self.assertFalse(self.world.get("combat", {}).get("active"))
            self.assertIn("hold", self.world["flags"]["deeds"][-1])
            await self.real_turn()
        self.assertTrue(pressed)
        self.assertTrue(self.world.get("combat", {}).get("active"))


if __name__ == "__main__":
    unittest.main()
