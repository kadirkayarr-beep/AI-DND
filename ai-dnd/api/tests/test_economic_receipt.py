"""A2: the money receipt is checked against the confirmed offer, not against what the narration or the purse says.

A wrong narration and a wrong purse can agree on the same wrong number; the receipt still refuses it, because the
price, the recipient, the change, the goods and the stock are recomputed from the offer the server stored.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import unittest

import economic_actions as ea
import equipment_economy
from api.schemas import PublicEconomicResolution as PublicEconomicResolutionSchema
from api.tests.test_economic_offer import proposal, room
from api.tests.test_economic_resolution import ResolutionFixture


def validation_rejected(before: ea.EconomicFacts, after: ea.EconomicFacts, resolution: ea.EconomicResolution,
                        offer: ea.EconomicOffer | None) -> bool:
    try:
        ea.validate_economic_resolution(before, after, resolution, confirmed_offer=offer)
    except ea.EconomicReceiptError:
        return True
    return False


class TheReceiptIsIndependent(ResolutionFixture):
    def facts_after(self, change) -> ea.EconomicFacts:
        """The facts of a copy of the world after `change` wrote to it; the live world is never touched."""
        world = copy.deepcopy(self.w)
        change(world)
        return ea.economic_facts(ea.EconomicState(world=world, character=None))

    def test_receipt_rejects_matching_wrong_narration_and_wallet(self):
        offer = self.offer(proposal(purpose="tip", recipient_id="barman", amount_cp=4))
        before = ea.economic_facts(self.state())
        honest = self.resolve(offer)
        tampered = dataclasses.replace(
            honest, net_debit_cp=5, public_summary="Barmene 5 bakır verdin.",
            asset_deltas=[ea.AssetDelta("player", "currency", "cp", 100, 95),
                          ea.AssetDelta("barman", "currency", "cp", 0, 5)])
        five_gone = self.facts_after(lambda world: equipment_economy.pay(world, "player", "barman", 5))
        self.assertTrue(validation_rejected(before, five_gone, tampered, offer))
        four_gone = self.facts_after(lambda world: equipment_economy.pay(world, "player", "barman", 4))
        self.assertFalse(validation_rejected(before, four_gone, honest, offer))
        # The purse moving the right amount does not save a receipt that claims otherwise, nor the other way round.
        self.assertTrue(validation_rejected(before, four_gone, tampered, offer))
        self.assertTrue(validation_rejected(before, five_gone, honest, offer))

    def test_receipt_rejects_recipient_stock_or_change_mismatch(self):
        before = ea.economic_facts(self.state())

        def room_and_tip(world, tip_to="barman"):
            world["currency"]["player"] -= 55
            world["currency"][tip_to] += 5
            world["flags"]["economic_ledger"] = {"sink_totals": {self.sink_id: 50}}
            world["flags"]["inn_room"] = {"place": self.here,
                                          "until": world["campaign_time"]["elapsed_seconds"] + 24 * 3600}

        offer = self.offer(room(recipient_id="barman", tip_cp=5, tender_cp=100))
        honest = self.resolve(offer)
        self.assertEqual((honest.status, honest.change_cp), ("applied", 45))
        right = self.facts_after(room_and_tip)
        self.assertFalse(validation_rejected(before, right, honest, offer))

        with self.subTest("recipient"):
            wrong_recipient = dataclasses.replace(honest, asset_deltas=[
                delta if delta.owner_id != "barman" else ea.AssetDelta("farmer", "currency", "cp", 0, 5)
                for delta in honest.asset_deltas])
            paid_farmer = self.facts_after(lambda world: room_and_tip(world, tip_to="farmer"))
            self.assertTrue(validation_rejected(before, paid_farmer, wrong_recipient, offer))
            self.assertTrue(validation_rejected(before, paid_farmer, honest, offer))

        with self.subTest("change"):
            self.assertTrue(validation_rejected(before, right, dataclasses.replace(honest, change_cp=40), offer))
            self.assertTrue(validation_rejected(before, right, dataclasses.replace(honest, tender_cp=60), offer))

        purchase = self.offer(proposal(purpose="purchase", recipient_id="barman", item_id="bira", count=1))
        sold = self.resolve(purchase, "op-buy")
        self.assertEqual(sorted((d.asset_kind, d.owner_id, d.asset_id, d.after - d.before) for d in sold.asset_deltas),
                         [("currency", "barman", "cp", 4), ("currency", "player", "cp", -4),
                          ("item", "player", "Bira", 1), ("stock", "barman", "bira", -1)])

        def bought(world, *, beers=1, stock_drops=True):
            equipment_economy.pay(world, "player", "barman", 4)
            for _ in range(beers):
                equipment_economy.grant_named_item(world, "Bira")
            if stock_drops:
                npc = next(npc for npc in world["npcs"] if npc["id"] == "barman")
                npc.setdefault("wares_v1", {})["bira"] = {"stock": 11}

        self.assertFalse(validation_rejected(before, self.facts_after(bought), sold, purchase))
        with self.subTest("stock not dropped"):
            self.assertTrue(validation_rejected(
                before, self.facts_after(lambda world: bought(world, stock_drops=False)), sold, purchase))
        with self.subTest("two beers handed"):
            self.assertTrue(validation_rejected(
                before, self.facts_after(lambda world: bought(world, beers=2)), sold, purchase))

    def test_public_receipt_hides_other_npc_wallet(self):
        self.w["currency"]["barman"] = 137
        self.w["npcs"][0].update(name="Gizli Marek", name_known_to_player=False)
        offer = self.offer(room(recipient_id="barman", tip_cp=5, tender_cp=100))
        result = self.settle(offer)
        self.assertEqual(result.status, "applied")
        public = ea.public_resolution(self.state(), result)
        payload = dataclasses.asdict(public)
        PublicEconomicResolutionSchema.model_validate(payload)
        text = json.dumps(payload, ensure_ascii=False)
        for hidden in ("137", "142", "asset_deltas", "balances", "base_fingerprint", "world_effects", "Gizli",
                       "barman", "acceptance"):
            self.assertNotIn(hidden, text)
        self.assertEqual((public.net_debit_cp, public.change_cp, public.tender_cp), (55, 45, 100))
        self.assertEqual([(line.line_id, line.total_cp) for line in public.lines], [("room:0", 50), ("tip:1", 5)])


if __name__ == "__main__":
    unittest.main()
