"""The owner's tavern turns T13 and T43, as typed: a beer or a plate is bought at the counter, once.

Real app, real adapter, real engine; only the model client is scripted, and the speech reply may carry
the commitment a small model really sends. Talk with the barman never moves coin or goods; the one
counter trade does, exactly once.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import bold_acts
import equipment_economy
from api.tests.test_front_proposal import FrontClient
from api.tests.test_world_keeps_its_word import FrontScene


class SpeechWithCommitment(FrontClient):
    """The speech reply may carry the commitment a small model sends with it."""

    commitment = None

    def chat(self, *args, **kwargs):
        schema = kwargs.get("format") or {}
        props = schema.get("properties") or {}
        if "front" in props or "intent" in props:
            return super().chat(*args, **kwargs)
        self.chat_calls += 1
        self.schemas.append(schema)
        self.message_batches.append(kwargs.get("messages", []))
        body = {"spoken_text": self.narration, "stage_direction": self.stage_direction, "threat": ""}
        if self.commitment is not None:
            body["commitment"] = self.commitment
        return {"message": {"content": json.dumps(body, ensure_ascii=False)}}


class AtTheCounter(FrontScene):
    PURSE = 2435

    async def at_the_bar(self, *, barman_holds=0):
        await self.begin()
        self.client = SpeechWithCommitment()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.npc["role"] = "Barmen"
        wallets = self.world.setdefault("currency", {})
        wallets["player"] = self.PURSE
        if barman_holds:
            wallets[self.npc["id"]] = barman_holds

    async def say(self, line, front, reply="Buyur.", *, commitment=None, stage=""):
        self.client.front = front
        self.client.stage_direction = stage
        self.client.commitment = commitment
        return await self.line(line, reply)

    def purse(self):
        return self.world["currency"]["player"]

    def barman(self):
        return self.world["currency"].get(self.npc["id"], 0)

    def bag(self):
        return [item.get("name") if isinstance(item, dict) else item for item in self.world.get("inventory", [])]

    def seq(self):
        return self.world.get("shop_trades_v1", {}).get("seq", 0)

    def speak(self):
        return {"kind": "speak_to", "person_id": self.npc["id"]}


class T13ABeerIsPaidForOnce(AtTheCounter):
    async def test_asking_what_a_beer_costs_puts_no_beer_in_the_bag(self):
        await self.at_the_bar()
        out = await self.say("tezgaha dayanıyorum. bi bira ver usta, kaç para?", self.speak(),
                             "Bira dört bakır paradır usta, buyur.", commitment={"kind": "give", "item": "Bira"})
        self.assertNotIn("Bira", self.bag(), out["narration"])
        self.assertEqual(self.purse(), self.PURSE)
        self.assertEqual(self.seq(), 0)
        self.assertIn("dört bakır", out["narration"])  # the price asked for is still said

    async def test_a_gold_thrown_for_a_beer_opens_the_counter_and_moves_no_coin(self):
        await self.at_the_bar()
        # The reading says what the coin is for (plan Task 8: with coin held out, the decision opens the counter)
        out = await self.say("bi altın atıyorum tezgaha usta, bi bira ver bana",
                             {**self.speak(), "coin_cp": 100, "deal": "goods", "deal_goods": "bira"}, "Sağ ol.")
        self.assertEqual(out["turn_outcome"]["action"], "shop_offer", out["narration"])
        self.assertEqual(self.purse(), self.PURSE, out["narration"])
        self.assertEqual(self.barman(), 0)
        self.assertNotIn("Bira", self.bag())
        self.assertNotIn("kesenden çıkıyor", out["narration"])
        self.assertNotIn("artık sende", str(self.client.message_batches))
        self.assertIsNone(getattr(self.session, "_handed_note", None))

    async def test_the_barman_handing_back_change_in_words_moves_nothing(self):
        await self.at_the_bar(barman_holds=100)
        out = await self.say("ee üstümü vermedin ama, bira dört bakırdı değil mi?", self.speak(),
                             "Haklısın, işte biran. Al üstünü, doksan altı bakır.",
                             commitment={"kind": "give", "item": "Bira", "amount_cp": 96})
        self.assertEqual(self.purse(), self.PURSE, out["narration"])
        self.assertEqual(self.barman(), 100)
        self.assertNotIn("Bira", self.bag())
        self.assertNotIn("avucuna", out["narration"])

    async def test_the_beer_bought_at_the_counter_comes_once_for_its_price(self):
        await self.at_the_bar()
        out = await self.line(f"/item shop_buy {self.npc['id']} bira 1 0 4")
        self.assertEqual(self.purse(), self.PURSE - 4, out["narration"])
        self.assertEqual(self.barman(), 4)
        beers = [item for item in self.world["inventory"] if isinstance(item, dict) and item.get("name") == "Bira"]
        self.assertEqual(len(beers), 1, self.bag())
        self.assertIn("4 bakır", out["narration"])
        again = await self.line(f"/item shop_buy {self.npc['id']} bira 1 0 4")
        self.assertIn("offer_stale", again["narration"])
        self.assertEqual(self.purse(), self.PURSE - 4)
        self.assertEqual(self.bag().count("Bira"), 1)


class T43APlateIsPaidForOnce(AtTheCounter):
    PURSE = 2276

    async def test_a_plate_with_coin_counted_out_opens_the_counter_and_moves_nothing(self):
        await self.at_the_bar(barman_holds=100)
        out = await self.say("ver bi tabak o zaman, otuz bakırı sayıp tezgaha koyuyorum",
                             {"kind": "attempt", "coin_cp": 30, "deal": "goods", "deal_goods": "yemek"},
                             "Parayı aldım, peynirle ekmeği hemen getiriyorum.",
                             commitment={"kind": "give", "item": "Ekmek peynir", "amount_cp": 30},
                             stage="Barmen tezgaha bırakılan bakırları alıp bir tabak hazırlar")
        self.assertEqual(out["turn_outcome"]["action"], "shop_offer", out["narration"])
        self.assertEqual(self.purse(), self.PURSE, out["narration"])
        self.assertEqual(self.barman(), 100)
        self.assertNotIn("avucuna", out["narration"])
        self.assertNotIn("kesenden çıkıyor", out["narration"])
        self.assertFalse([name for name in self.bag() if "peynir" in name.casefold() or "tabak" in name.casefold()])

    async def test_a_plate_promised_in_words_is_not_handed_over(self):
        await self.at_the_bar(barman_holds=100)
        out = await self.say("tabak yemek otuzdu dimi, ver hadi bi tane?", self.speak(),
                             "Otuz bakır, al bakalım peynirle ekmeğini.",
                             commitment={"kind": "give", "item": "Ekmek peynir", "amount_cp": 30})
        self.assertEqual(self.purse(), self.PURSE, out["narration"])
        self.assertEqual(self.barman(), 100)
        self.assertNotIn("Ekmek peynir", self.bag())
        self.assertNotIn("avucuna", out["narration"])

    async def test_the_plate_bought_at_the_counter_takes_thirty_once(self):
        await self.at_the_bar(barman_holds=100)
        self.assertFalse(hasattr(bold_acts, "give_coin"))  # the old hand-over writer is gone (A4)
        out = await self.line(f"/item shop_buy {self.npc['id']} yemek 1 0 30")
        self.assertEqual(self.purse(), self.PURSE - 30, out["narration"])
        self.assertEqual(self.barman(), 130)
        # Counted from the ledger, not from pay calls: the owner pays on its copy and then on the live world (A2).
        flags = self.world.get("flags", {})
        purchases = [entry for entry in flags.get("economic_ledger", {}).get("operations", {}).values()
                     if entry["purpose"] == "purchase"]
        self.assertEqual([entry["net_debit_cp"] for entry in purchases], [30])
        self.assertFalse([data for data in flags.get("economic_offers", {}).values()
                          if data["proposal"]["purpose"] == "gift"])
        self.assertEqual(self.bag().count("Tabak yemek"), 1, self.bag())


if __name__ == "__main__":
    unittest.main()
