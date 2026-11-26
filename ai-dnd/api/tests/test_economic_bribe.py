"""A4: coin held out to the guard making an arrest opens a bribe card; only its confirmation rolls the word (C8, O1).

The first bribe card of a hold pauses that turn's escalation; a second bribe in the same hold does not, and when
the guard's patience is spent the fight starts and no card is prepared at all. A card left open is cancelled at
the next ordinary turn. Coin handed to someone else during an arrest is no bribe. No real model is called.
"""

from __future__ import annotations

import copy
import os
import unittest
import uuid
from unittest.mock import patch

import bold_acts
import campaign_time
import economic_actions as ea
import game
import money_owner
import world_reactions
from api.serializers import serialize_session_state
from api.tests import test_front_proposal as front_tests
from api.tests.coin_seam import planted
from api.tests.journeys.runner import call_kind
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
        with planted(self.s, _bribe_held_out=amount):
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
        # Design §12 D29 (plan Task 8): five coppers fit neither an open offer nor the room's price, so the money
        # owner's decision is unclear; the room words are not read for it. No card opens, nothing is paid, and the
        # coin is noted for the innkeeper's turn only.
        decision = money_owner.current(self.s)
        self.assertEqual((decision.kind, decision.npc_id, decision.amount_cp, decision.source),
                         ("unclear", "barman", 5, "structural"))
        self.assertEqual(self.prepared(), [], result["narration"])
        self.assertNotIn(bold_acts.COIN_NOT_TENDERED, result["narration"])
        self.assertEqual(self.w["currency"]["player"], 500)
        self.assertIn(("barman", money_owner.unclear_note(5)), self.s._turn_notes)
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


class AFailedReadingStillDecidesTheCoin(Arrest):
    """Owner rule G11 ("Eski kural karar versin", Kadir 2026-11-19): with the flag on, a reading that failed leaves the
    coin the line's own words hold out to the money owner's structural rule (no deal), which decides it and writes its
    note; coin never vanishes silently. A reading that came back decides the coin once, from the model, and the
    structural rule never adds a second decision. The setUp's model raises AssertionError: a failed reading, not an
    outage (G6), so the line plays on through the old chain."""

    def setUp(self):
        super().setUp()
        flag = patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"})
        flag.start()
        self.addCleanup(flag.stop)

    def deciding(self):
        """Every decision the money owner makes this turn, by its source."""
        made = []
        real = money_owner.decide
        return made, patch.object(money_owner, "decide",
                                  side_effect=lambda *a, **k: (made.append(real(*a, **k)), made[-1])[1])

    def test_a_failed_reading_still_gives_coin_to_the_innkeeper_the_structural_decision_and_its_note(self):
        self.held()
        made, spy = self.deciding()
        pressed, pressing = self.counting("_press")
        with spy, pressing:
            result = self.s.run_player_turn("hancıya 5 bakır verip oda tutuyorum")
        self.assertEqual(self.s._front_route, "fallback:failed")
        self.assertEqual([(d.kind, d.npc_id, d.amount_cp, d.source) for d in made],
                         [("unclear", "barman", 5, "structural")])
        self.assertIs(money_owner.current(self.s), made[0])
        self.assertIn(("barman", money_owner.unclear_note(5)), self.s._turn_notes)
        self.assertEqual(bribe_cards(self.w), [])
        self.assertEqual(self.prepared(), [], result["narration"])
        self.assertEqual(self.w["currency"]["player"], 500)
        self.assertEqual(len(pressed), 1)
        self.assertNotIn("bribe_card_opened", self.deed()["hold"])

    def test_an_unusable_reading_is_a_failed_reading_for_the_coin(self):
        self.held()
        client = front_tests.FrontClient()
        client.unusable = ("{\"intent\": ", "length")
        made, spy = self.deciding()
        with spy, patch("game.ollama.chat", side_effect=client.chat):
            result = self.s.run_player_turn("hancıya 5 bakır verip oda tutuyorum")
        self.assertEqual(self.s._front_route, "fallback:unusable")
        self.assertEqual([(d.kind, d.npc_id, d.amount_cp, d.source) for d in made],
                         [("unclear", "barman", 5, "structural")])
        self.assertIn(("barman", money_owner.unclear_note(5)), self.s._turn_notes)
        self.assertEqual(self.prepared(), [], result["narration"])
        self.assertEqual(self.w["currency"]["player"], 500)

    def test_a_failed_reading_puts_coin_held_out_to_nobody_to_the_arresting_guard(self):
        self.held(since=world_reactions.ARREST_PATIENCE + 3)
        made, spy = self.deciding()
        forced, forcing = self.counting("_force")
        with spy, forcing:
            result = self.s.run_player_turn("100 bakır uzatıyorum")
        self.assertEqual(self.s._front_route, "fallback:failed")
        self.assertEqual([(d.kind, d.npc_id, d.amount_cp, d.source) for d in made],
                         [("bribe", "guard", 100, "structural")])
        [card] = bribe_cards(self.w)
        self.assertEqual((card["status"], card["proposal"]["recipient_id"], card["proposal"]["amount_cp"]),
                         ("prepared", "guard", 100), result["narration"])
        self.assertEqual(self.w["currency"]["player"], 500)  # the card moves nothing until it is confirmed
        # D-411: the first card of a hold pauses that turn's escalation, as when the coin was planted (TheBribeCard)
        self.assertEqual(forced, [])
        self.assertFalse(self.fighting())
        self.assertIs(self.deed()["hold"]["bribe_card_opened"], True)

    def test_a_failed_reading_with_coin_for_nobody_found_keeps_it_in_hand_and_asks_who(self):
        # No arrest: the structural decision names nobody, so it is not kept; the coin waits in hand with no decision
        # (read as with no reading: a room or an order the words ask for would take it) and who it is for is asked.
        made, spy = self.deciding()
        seen = []
        real = money_owner.open_card_after_reply
        with spy, patch.object(money_owner, "open_card_after_reply", side_effect=lambda s, r, *a, **k: (
                seen.append((money_owner.current(s), s._coin_paid)), real(s, r, *a, **k))[1]):
            result = self.s.run_player_turn("100 bakır uzatıyorum")
        self.assertEqual(self.s._front_route, "fallback:failed")
        self.assertEqual([(d.kind, d.npc_id, d.amount_cp, d.source) for d in made],
                         [("unclear", None, 100, "structural")])
        self.assertEqual(seen, [(None, (100, None, self.here))])
        self.assertIn(ea._CLARIFY["npc_unknown"], result["narration"])
        self.assertEqual((self.offers(), self.w["currency"]["player"]), ({}, 500))

    def read_back(self, front):
        """One coin line under arrest whose reading came back with this front; the decisions the turn made."""
        self.held()
        client = front_tests.FrontClient()
        client.front = front
        kinds = []
        made, spy = self.deciding()
        with spy, patch("game.ollama.chat", side_effect=lambda *a, **k: (
                kinds.append(call_kind(k.get("format")) or "other"), client.chat(*a, **k))[1]):
            self.s.run_player_turn("hancıya 5 bakır verip oda tutuyorum")
        self.assertEqual(kinds, ["front", "speech"])  # one reading, then the innkeeper's answer
        self.assertTrue(self.s._front_route.startswith("front:"), self.s._front_route)
        self.assertEqual(self.w["currency"]["player"], 500)
        return [(d.kind, d.npc_id, d.amount_cp, d.source) for d in made]

    # Review Focus 3: the structural rule runs only when the reading failed.
    def test_a_reading_that_came_back_makes_the_only_coin_decision(self):
        self.assertEqual(self.read_back({"kind": "speak_to", "person_id": "barman", "coin_cp": 5, "deal": "room"}),
                         [("unclear", "barman", 5, "model")])

    def test_a_reading_that_came_back_seeing_no_coin_gets_no_structural_decision(self):
        self.assertEqual(self.read_back({"kind": "speak_to", "person_id": "barman", "coin_cp": 0, "deal": "none"}),
                         [])


class BribeConfirmations(EconomicHttpFixture):
    async def open_bribe(self, amount=100):
        self.hold_by_guard()
        session = self.record.game_session
        with planted(session, _bribe_held_out=amount), \
                patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
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
