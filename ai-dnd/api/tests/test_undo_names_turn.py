"""Görev 26: the undo sentence says which turn it undid and how the purse moved back.

Text only: the undo itself (restore, card revival, one step) is untouched; the purse numbers here are read from the
world before and after the very same restore, and the purse after the undo is the purse before the turn.
"""
from __future__ import annotations

import unittest

from api.history_view import undo_narration
from api.tests.test_economic_action_http import TIP, EconomicHttpFixture

OLD_PLAIN = ("Son tur geri alındı: “barmene selam veriyorum” ve sonuçları yaşanmamış sayılıyor. "
             "Dünya o turdan önceki hâline döndü; sıradaki hamle senin.")


class UndoSentenceNamesTheTurn(unittest.TestCase):
    def test_no_purse_change_keeps_todays_sentence(self):
        self.assertEqual(undo_narration("barmene selam veriyorum"), OLD_PLAIN)
        self.assertEqual(undo_narration("barmene selam veriyorum", purse_delta_cp=0), OLD_PLAIN)
        self.assertEqual(undo_narration("barmene selam veriyorum", purse_delta_cp=None), OLD_PLAIN)

    def test_coins_coming_back_are_counted(self):
        text = undo_narration("bira istiyorum", purse_delta_cp=4)
        self.assertEqual(text, "Son tur geri alındı: “bira istiyorum” ve sonuçları yaşanmamış sayılıyor. "
                               "Kesene 4 bakır geri döndü. Dünya o turdan önceki hâline döndü; sıradaki hamle senin.")

    def test_coins_going_back_are_counted(self):
        self.assertIn("Kesenden 7 bakır geri alındı.", undo_narration("kılıcı satıyorum", purse_delta_cp=-7))

    def test_a_turn_label_names_the_turn_instead_of_the_fixed_card_words(self):
        text = undo_narration("Teklifi onayla", purse_delta_cp=4, turn_label="Marek'e bahşiş: 4 bakır ödendi.")
        self.assertIn("“Marek'e bahşiş: 4 bakır ödendi” ve sonuçları", text)
        self.assertNotIn("Teklifi onayla", text)

    def test_a_slash_command_is_still_never_quoted(self):
        text = undo_narration("/item shop_buy barman bira 1 0 4", purse_delta_cp=4)
        self.assertNotIn("/", text)
        self.assertNotIn("“", text)
        self.assertIn("Kesene 4 bakır geri döndü.", text)


class UndoSentenceOverHttp(EconomicHttpFixture):
    async def test_undoing_a_paid_card_names_it_and_the_coins(self):
        card = await self.card(**TIP)
        answered, body = await self.confirm(card)
        self.assertEqual(self.purse(), 96)
        summary = answered["economic_resolution"]["public_summary"].rstrip(".")
        undone = await self.undo(body["action_id"])
        self.assertEqual(undone.status_code, 200, undone.text)
        narration = undone.json()["narration"]
        self.assertIn(f"“{summary}”", narration)
        self.assertIn("Kesene 4 bakır geri döndü.", narration)
        self.assertNotIn("Teklifi onayla", narration)
        self.assertEqual((self.purse(), self.world["currency"]["barman"]), (100, 0))  # the undo itself is unchanged
        self.assertEqual(undone.json()["state"]["wallet"]["total_cp"], 100)

    async def test_undoing_a_moneyless_turn_says_nothing_about_the_purse(self):
        turn_id, _ = await self.real_turn("Tezgâha yaslanıp salonu dinliyorum.")
        undone = await self.undo(turn_id)
        self.assertEqual(undone.status_code, 200, undone.text)
        narration = undone.json()["narration"]
        self.assertIn("“Tezgâha yaslanıp salonu dinliyorum.”", narration)
        self.assertNotIn("Kese", narration)
        self.assertEqual(self.purse(), 100)


if __name__ == "__main__":
    unittest.main()
