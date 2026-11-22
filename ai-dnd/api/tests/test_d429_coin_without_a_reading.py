"""D-429: coin held out on a line whose model reading failed answers as it does with the flag off (owner rule G11).

`_coin_without_a_reading` gives that coin the money owner's structural decision. The row's four cases: a beer ordered
from the barman with coin below its price opens the counter as with the flag off (1); coin and a bed promised to a
named person who is not the innkeeper opens the room card, or keeps the `unclear` note when no card can open (2); a
bed promised in a fight stays `unclear` (R11) and opens nothing (3); the HTTP room path really runs on a failed
reading (4). In every case no coin moves: the purse, pack, ledger, room and clock are byte-equal before and after.
No real model is called.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

import campaign_time
import game
import money_owner
from api.tests.test_economic_action_http import EconomicHttpFixture
from api.tests.town_seed import fixed_town

BEER_BELOW_PRICE = "barmene 2 bakır verip bi bira istiyorum"
BED_TO_A_NAMED_SMITH = "Aldric'e 1 gümüş verip oda tutuyorum"
BED_TO_THE_INNKEEPER = "hancıya 1 gümüş verip oda tutuyorum"


def _money(world):
    """Purse, pack, ledger, room and clock as bytes: a line that moves no coin leaves them exactly as they were."""
    flags = world.get("flags", {})
    return json.dumps({"currency": world["currency"], "inventory": world.get("inventory"),
                       "ledger": flags.get("economic_ledger"), "inn_room": flags.get("inn_room"),
                       "clock": world.get("campaign_time")}, ensure_ascii=False, sort_keys=True)


def _played(test, seed, flag, line, *, fight=False):
    """One coin line at the counter (test_economic_room's table plus a named smith), the flag set, no model answer."""
    original = game._coin_without_a_reading
    with fixed_town(test, seed), patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": flag}), \
            patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
        s = game.create_session(seed=7)
        w = s.world_state
        here = w["location"]
        w["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": here, "current_hp": 10},
            {"id": "guest", "name": "Oren", "role": "Yolcu", "location": here, "current_hp": 10},
            {"id": "t7_aldric", "name": "Aldric", "role": "Demirci", "location": here, "current_hp": 10},
        ]
        w["currency"] = {"player": 500, "barman": 100, "guest": 100, "t7_aldric": 100}
        w.setdefault("flags", {})["turn_index"] = 3
        campaign_time.initialize(w)
        if fight:  # Oren turns on the player (test_combat_lifecycle.ready's way); the player acts first
            oren = w["npcs"][1]
            oren.update(current_hp=40, max_hp=40, armor_class=20, hostile=True, distance_ft=5,
                        attack_damage_type="bludgeoning")
            w.setdefault("monster_perception", {})[oren["id"]] = {"player": {"visible": True}}
            with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
                s.start_combat(oren)
            test.assertTrue(w["combat"]["active"])
        seen = []

        def watch(*args):
            original(*args)
            decided = money_owner.current(s)
            seen.append(None if decided is None else (decided.kind, decided.npc_id, decided.amount_cp))

        before = _money(w)
        with patch("game._coin_without_a_reading", side_effect=watch):
            result = s.run_player_turn(line)
        action = result.get("action_result") or {}
        counter = w["flags"].get("counter_offer_v1")
        return {"route": getattr(s, "_front_route", None), "seen": seen,
                "action": (action.get("action"), action.get("status")),
                "cards": sorted((data["status"], data["proposal"]["purpose"], data["proposal"]["recipient_id"])
                                for data in w.get("flags", {}).get("economic_offers", {}).values()),
                "counter": None if counter is None else (counter.get("npc_id"), counter.get("key")),
                "notes": list(getattr(s, "_turn_notes", None) or []),
                "money_before": before, "money_after": _money(w), "narration": result.get("narration")}


class ACoinWithoutAReading(unittest.TestCase):
    def test_a_beer_paid_below_price_opens_the_counter_with_the_reading_down(self):
        # Case 1 (the beer twin): two coppers fit neither the beer (4) nor a room, and the words ask for no bed. With
        # the flag off the counter opens and asks how many; a failed reading must not leave Marek saying only "Peki."
        off = _played(self, 20261480, "", BEER_BELOW_PRICE)
        on = _played(self, 20261480, "1", BEER_BELOW_PRICE)
        self.assertEqual(on["route"], "fallback:failed")
        self.assertEqual(len(on["seen"]), 1)  # the coin was decided once, by the structural rule
        self.assertEqual((on["action"], on["cards"], on["counter"]), (off["action"], off["cards"], off["counter"]),
                         on["narration"])
        self.assertEqual((off["action"], off["counter"]), (("shop_offer", "offer_open"), ("barman", "bira")))
        self.assertIn(off["narration"], on["narration"])
        for played in (off, on):
            self.assertEqual(played["money_after"], played["money_before"])

    def test_a_coin_and_bed_promise_to_a_named_person_keeps_its_note(self):
        # Case 2: coin and a bed promised to Aldric, a smith who gives no rooms. The room card opens (with whoever
        # serves here), or, when none can open, the `unclear` note for Aldric is kept: the coin never vanishes silently.
        on = _played(self, 20261482, "1", BED_TO_A_NAMED_SMITH)
        self.assertEqual(on["route"], "fallback:failed")
        room_opened = [card for card in on["cards"] if card[:2] == ("prepared", "room")]
        noted = ("t7_aldric", money_owner.unclear_note(10)) in on["notes"]
        self.assertTrue(room_opened or noted, on)
        self.assertEqual(on["money_after"], on["money_before"])

    def test_a_bed_promise_in_combat_stays_unclear(self):
        # Case 3 (R11): in a fight nothing is bought, given or rented. Coin and a bed promised to the innkeeper stay an
        # `unclear` decision with its note; no room card opens and nothing is paid.
        on = _played(self, 20261484, "1", BED_TO_THE_INNKEEPER, fight=True)
        self.assertEqual(on["route"], "fallback:failed")
        self.assertEqual(on["seen"], [("unclear", "barman", 10)], on["narration"])
        self.assertIn(("barman", money_owner.unclear_note(10)), on["notes"], on["narration"])
        self.assertEqual(on["cards"], [], on["narration"])
        self.assertEqual(on["money_after"], on["money_before"])

    def test_coin_for_whoever_serves_that_names_no_ware_keeps_its_note(self):
        # Review fix 1 (G11): only words naming a thing the counter sells are the counter's to read. A tip, plain coin
        # or coin for talk held out to whoever serves keeps its `unclear` decision and note; nothing moves.
        for line, amount in (("barmene 1 gümüş bahşiş veriyorum", 10), ("barmene 5 bakır veriyorum", 5),
                             ("Marek'e 3 bakır verip ne haber diyorum", 3)):
            with self.subTest(line=line):
                on = _played(self, 20261488, "1", line)
                self.assertEqual(on["route"], "fallback:failed")
                self.assertEqual(on["seen"], [("unclear", "barman", amount)], on["narration"])
                self.assertIn(("barman", money_owner.unclear_note(amount)), on["notes"], on["narration"])
                self.assertEqual(on["money_after"], on["money_before"])


class TheRoomReadingReallyFailedOverHttp(EconomicHttpFixture):
    """Case 4: the HTTP room path for "hancıya 1 gümüş verip oda tutuyorum" (test_economic_room's D-402 test) runs on
    a reading that really failed, and its card is the one the flag-off line opens; the line moves no coin."""

    async def asyncSetUp(self):
        with fixed_town(self, 20261486):
            await super().asyncSetUp()

    async def test_the_room_reading_really_failed_in_the_http_test(self):
        session = self.record.game_session
        before = self.money()
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}), \
                patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            session.run_player_turn(BED_TO_THE_INNKEEPER)
        self.assertEqual(session._front_route, "fallback:failed")
        self.assertIsNone(money_owner.current(session))
        self.save()
        [card] = self.offers().values()
        self.assertEqual((card["status"], card["proposal"]["purpose"], card["proposal"]["recipient_id"],
                          card["proposal"]["tender_cp"]), ("prepared", "room", "barman", None))
        after = json.loads(self.money())
        after.pop("turn_index")  # the line is a turn: only the money it holds must not move
        self.assertEqual(json.dumps(after, ensure_ascii=False, sort_keys=True),
                         json.dumps({k: v for k, v in json.loads(before).items() if k != "turn_index"},
                                    ensure_ascii=False, sort_keys=True))
        answer, body = await self.confirm(card)
        self.assertEqual((answer["economic_resolution"]["status"], answer["economic_resolution"]["net_debit_cp"],
                          self.purse()), ("applied", 50, 50))
        undone = await self.undo(body["action_id"])
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.purse(), 100)


if __name__ == "__main__":
    unittest.main()
