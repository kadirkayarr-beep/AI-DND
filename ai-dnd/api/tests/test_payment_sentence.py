"""Görev 32: the payment sentence names the item and the person ("Jemvik'e hediye: 5900 bakır ödendi.").

Text only. The card is still the one writer of money: every test here also checks the purse, the recipient's purse
and the pack against the same confirm with the old sentence, so the new words move nothing.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import economic_actions as ea
from api.tests.test_economic_action_http import ROOM, TIP, EconomicHttpFixture


class NamedPlace(unittest.TestCase):
    def test_turkish_suffixes_follow_the_last_vowel(self):
        cases = {("Jemvik", "dative"): "Jemvik'e", ("Ilgın", "dative"): "Ilgın'a", ("Çavuş Hale", "dative"): "Çavuş Hale'ye",
                 ("Marek", "ablative"): "Marek'ten", ("Ilgın", "ablative"): "Ilgın'dan", ("Hale", "ablative"): "Hale'den",
                 ("Tuna", "dative"): "Tuna'ya", ("Bir barmen", "dative"): "Bir barmene",
                 ("Kızıl saçlı biri", "dative"): "Kızıl saçlı birine", ("Bir barmen", "ablative"): "Bir barmenden"}
        for (name, case), expected in cases.items():
            with self.subTest(name=name, case=case):
                proper = not name.startswith(("Bir ", "Kızıl"))
                self.assertEqual(ea._with_case(name, case, proper=proper), expected)

    def test_a_name_without_a_vowel_gets_no_suffix(self):
        self.assertIsNone(ea._with_case("X7", "dative", proper=True))


class PaymentSentence(EconomicHttpFixture):
    def reset(self):
        self.world["flags"].pop("inn_room", None)
        self.world["flags"].pop("economic_ledger", None)
        self.world["currency"] = {"player": 100, "barman": 0, "farmer": 0, "guard": 0}

    def moved(self):
        flags = self.world.get("flags", {})
        return json.dumps({"currency": self.world["currency"], "inventory": self.world.get("inventory"),
                           "inn_room": bool(flags.get("inn_room")),
                           "sinks": (flags.get("economic_ledger") or {}).get("sink_totals")},
                          ensure_ascii=False, sort_keys=True)

    async def paid(self, fields, legacy=False):
        """One confirm from a fresh purse; `legacy` writes the old sentence. Returns (resolution, money after)."""
        self.reset()
        card = await self.card(**fields)
        if legacy:
            with patch.object(ea, "_payment_words", lambda *args, **kwargs: None):
                answered, _ = await self.confirm(card)
        else:
            answered, _ = await self.confirm(card)
        return answered["economic_resolution"], self.moved()

    async def assert_only_words_differ(self, fields, sentence):
        old, old_money = await self.paid(fields, legacy=True)
        new, new_money = await self.paid(fields)
        self.assertEqual(new["public_summary"], sentence)
        self.assertEqual(new_money, old_money)  # purse, recipient purse, pack, room right, sinks: the same
        keep = ("status", "reason_code", "lines", "refusals", "tender_cp", "change_cp", "net_debit_cp")
        self.assertEqual({key: new[key] for key in keep}, {key: old[key] for key in keep})
        self.assertNotEqual(old["public_summary"], new["public_summary"])
        return new

    async def test_a_tip_names_the_person(self):
        await self.assert_only_words_differ(TIP, "Marek'e bahşiş: 4 bakır ödendi.")
        self.assertEqual((self.purse(), self.world["currency"]["barman"]), (96, 4))

    async def test_a_gift_names_the_person_with_the_right_suffix(self):
        await self.assert_only_words_differ({"purpose": "gift", "recipient_id": "farmer", "amount_cp": 59},
                                            "Ilgın'a hediye: 59 bakır ödendi.")
        await self.assert_only_words_differ({"purpose": "gift", "recipient_id": "guard", "amount_cp": 7},
                                            "Çavuş Hale'ye hediye: 7 bakır ödendi.")

    async def test_a_room_names_the_house_and_the_tip(self):
        await self.assert_only_words_differ({**ROOM, "tip_cp": 5}, "Marek'ten oda (bir gece) ve bahşiş: 55 bakır ödendi.")

    async def test_an_unknown_name_is_never_said(self):
        self.world["npcs"][0]["name_known_to_player"] = False
        new = await self.assert_only_words_differ(TIP, "Bir barmene bahşiş: 4 bakır ödendi.")
        self.assertNotIn("Marek", new["public_summary"])

    async def test_a_declined_tip_still_says_so(self):
        self.reset()
        card = await self.card(**ROOM, tip_cp=5)
        self.world["currency"]["player"] = 52                   # the tip no longer fits: only the room is paid
        answered, _ = await self.confirm(card)
        self.assertEqual(answered["economic_resolution"]["public_summary"],
                         "Marek'ten oda (bir gece): 50 bakır ödendi. Bahşiş geçmedi; kesende kaldı.")
        self.assertEqual(self.purse(), 2)


if __name__ == "__main__":
    unittest.main()
