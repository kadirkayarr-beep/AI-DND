"""A2: one economic owner. A confirmed offer is resolved on a copy, checked against its receipt, then written once.

No model call, no database. `resolve_offer` only reads; `apply_resolution` settles the purse's written coin on a
copy, applies the money, the room right and the world effect there, validates the world and the receipt, and only
then repeats the same steps on the live dicts in place. A day's wage goes through `settle_entitlement` and is paid
once per event however often it is asked for.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import unittest
from unittest.mock import patch

import bold_acts
import economic_actions as ea
import equipment_economy
import equipment_native
from api.tests.test_economic_offer import OfferFixture, proposal, room


def refuse_line(offer: ea.EconomicOffer, line_id: str) -> ea.EconomicOffer:
    """A fixture-only line refusal: the step-0 engine never refuses only the tip of a full purse."""
    decisions = [dataclasses.replace(decision, status="refused", reason_code="fixture_line_refused")
                 if decision.line_id == line_id else decision for decision in offer.acceptance.line_decisions]
    return dataclasses.replace(offer, acceptance=dataclasses.replace(offer.acceptance, line_decisions=decisions))


class ResolutionFixture(OfferFixture):
    def setUp(self):
        super().setUp()
        self.w["currency"] = {"player": 100, "barman": 0, "farmer": 0}
        self.sink_id = f"sink:lodging:{self.here}"

    def offer(self, value: ea.EconomicProposal) -> ea.EconomicOffer:
        result = self.prepare(value, offer_id=ea.new_offer_id())
        self.assertEqual(result.status, "prepared", result.public_message)
        return result.offer

    def resolve(self, offer: ea.EconomicOffer, operation_id: str = "op-1", check=None) -> ea.EconomicResolution:
        return ea.resolve_offer(self.state(), offer, operation_id=operation_id, check=check)

    def apply(self, resolution: ea.EconomicResolution, offer: ea.EconomicOffer | None) -> ea.EconomicResolution:
        return ea.apply_resolution(self.state(), resolution, confirmed_offer=offer)

    def settle(self, offer: ea.EconomicOffer, operation_id: str = "op-1", check=None) -> ea.EconomicResolution:
        return self.apply(self.resolve(offer, operation_id, check), offer)

    def sink(self) -> int:
        return ((self.w["flags"].get("economic_ledger") or {}).get("sink_totals") or {}).get(self.sink_id, 0)

    def has_room(self) -> bool:
        return isinstance(self.w["flags"].get("inn_room"), dict)

    def snapshot(self) -> str:
        return json.dumps({"currency": self.w["currency"], "flags": self.w["flags"],
                           "inventory": self.w.get("inventory")}, ensure_ascii=False, sort_keys=True)


class RoomAndTip(ResolutionFixture):
    def test_room_and_tip_acceptance_matrix(self):
        # The two "tip refused" rows are unit-level: the fixture refuses the tip line itself (fixture_line_refused).
        # The step-0 engine has no reason to refuse only the tip of a full purse; that only happens by no_money.
        cases = (
            ("both accepted", "base_required", None, (45, 5, 50, True)),
            ("tip refused", "base_required", "tip:1", (50, 0, 50, True)),
            ("no room", "base_required", "room:0", (100, 0, 0, False)),
            ("all or none, tip refused", "all_or_none", "tip:1", (100, 0, 0, False)),
        )
        for name, dependency, refused, expected in cases:
            with self.subTest(name):
                self.setUp()
                offer = self.offer(room(recipient_id="barman", tip_cp=5, dependency=dependency))
                if refused:
                    offer = refuse_line(offer, refused)
                result = self.settle(offer)
                got = (self.w["currency"]["player"], self.w["currency"]["barman"], self.sink(), self.has_room())
                self.assertEqual(got, expected, result)
                self.assertEqual(result.status, "applied" if expected[3] else "refused")
                if refused == "tip:1" and dependency == "base_required":
                    self.assertEqual([(r.line_id, r.reason_code) for r in result.refusals],
                                     [("tip:1", "fixture_line_refused")])

    def test_existing_room_sink_policy_is_preserved(self):
        result = self.settle(self.offer(room(recipient_id="barman")))
        self.assertEqual(result.status, "applied")
        self.assertEqual(self.w["currency"]["player"], 50)
        self.assertEqual(self.w["currency"]["barman"], 0)
        self.assertEqual(self.sink(), 50)
        self.assertEqual(self.w["flags"]["inn_room"]["place"], self.here)
        self.assertEqual(self.w["flags"]["inn_room"]["until"],
                         self.w["campaign_time"]["elapsed_seconds"] + bold_acts._ROOM_DAY)
        sink = [delta for delta in result.asset_deltas if delta.asset_kind == "sink"]
        self.assertEqual([(d.owner_id, d.before, d.after) for d in sink], [(self.sink_id, 0, 50)])
        self.assertNotIn("barman", {delta.owner_id for delta in result.asset_deltas})

    def test_room_alone_insufficient_funds_changes_nothing(self):
        offer = self.offer(room(recipient_id="barman"))
        self.w["currency"]["player"] = 40
        before = self.snapshot()
        result = self.settle(offer)
        self.assertEqual((result.status, result.reason_code), ("refused", "no_money"))
        self.assertEqual(result.asset_deltas, [])
        self.assertEqual(self.snapshot(), before)

    def test_room_plus_tip_wallet_52_pays_room_refuses_tip(self):
        self.w["currency"]["player"] = 52
        result = self.settle(self.offer(room(recipient_id="barman", tip_cp=5)))
        self.assertEqual(result.status, "applied")
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["barman"], self.sink()), (2, 0, 50))
        self.assertEqual([(r.line_id, r.reason_code) for r in result.refusals], [("tip:1", "no_money")])
        self.assertEqual(result.net_debit_cp, 50)

    def test_all_or_none_insufficient_changes_nothing(self):
        offer = self.offer(room(recipient_id="barman", tip_cp=5, dependency="all_or_none"))
        self.w["currency"]["player"] = 52
        before = self.snapshot()
        result = self.settle(offer)
        self.assertEqual((result.status, result.reason_code), ("refused", "no_money"))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.has_room())


class WagesAreEntitlements(ResolutionFixture):
    def test_wage_and_tip_have_distinct_causes(self):
        wage = ea.settle_entitlement(self.state(), event_id="wage:job-1:3", payer_id="thread-pool:job-1:3",
                                     recipient_id="player", amount_cp=40)
        self.assertEqual((wage.status, wage.replayed, wage.operation_id), ("applied", False, "entitlement:wage:job-1:3"))
        self.settle(self.offer(proposal(purpose="tip", recipient_id="farmer", amount_cp=5)), "op-tip")
        self.assertEqual(self.w["currency"]["player"], 135)
        self.assertEqual(self.w["currency"]["farmer"], 5)
        self.assertNotIn("thread-pool:job-1:3", self.w["currency"])
        ledger = self.w["flags"]["economic_ledger"]
        self.assertEqual(ledger["entitlements"], {"wage:job-1:3": "entitlement:wage:job-1:3"})
        self.assertEqual({op: entry["purpose"] for op, entry in ledger["operations"].items()},
                         {"entitlement:wage:job-1:3": "entitlement", "op-tip": "tip"})

    def test_entitlement_event_pays_once(self):
        first = ea.settle_entitlement(self.state(), event_id="wage:job-1:1", payer_id="thread-pool:job-1:1",
                                      recipient_id="player", amount_cp=40)
        self.assertFalse(first.replayed)
        self.assertEqual(self.w["currency"]["player"], 140)
        again = ea.settle_entitlement(self.state(), event_id="wage:job-1:1", payer_id="thread-pool:job-1:1",
                                      recipient_id="player", amount_cp=40)
        self.assertEqual((again.operation_id, again.status, again.asset_deltas, again.net_debit_cp, again.replayed),
                         (first.operation_id, "applied", [], 0, True))
        self.assertEqual(self.w["currency"]["player"], 140)
        # 201 later operations prune the first one out of `operations`; the event is still known.
        operations = self.w["flags"]["economic_ledger"]["operations"]
        for index in range(201):
            operations[f"filler-{index}"] = {"offer_id": None, "purpose": "tip", "net_debit_cp": 0, "turn_index": 0}
        ea.settle_entitlement(self.state(), event_id="wage:job-1:2", payer_id="thread-pool:job-1:2",
                              recipient_id="player", amount_cp=40)
        operations = self.w["flags"]["economic_ledger"]["operations"]
        self.assertEqual(len(operations), 200)
        self.assertNotIn(first.operation_id, operations)
        self.assertEqual(self.w["currency"]["player"], 180)
        late = ea.settle_entitlement(self.state(), event_id="wage:job-1:1", payer_id="thread-pool:job-1:1",
                                     recipient_id="player", amount_cp=40)
        self.assertEqual((late.operation_id, late.asset_deltas, late.net_debit_cp, late.replayed),
                         (first.operation_id, [], 0, True))
        self.assertEqual(self.w["currency"]["player"], 180)

    def test_entitlements_are_bounded_and_keep_the_undo_window(self):
        self.w["flags"]["turn_index"] = 10
        ledger = self.w["flags"].setdefault("economic_ledger", {})
        operations = ledger.setdefault("operations", {})
        entitlements = ledger.setdefault("entitlements", {})
        recent = [f"wage:recent:{index}" for index in range(10)]
        for event_id in recent:  # the oldest entries, yet paid in the turn undo can take back
            entitlements[event_id] = f"entitlement:{event_id}"
            operations[f"entitlement:{event_id}"] = {"offer_id": None, "purpose": "entitlement",
                                                     "net_debit_cp": 0, "turn_index": 9}
        old = [f"wage:old:{index}" for index in range(ea.LEDGER_ENTITLEMENTS_CAP - 5)]
        for event_id in old:
            entitlements[event_id] = f"entitlement:{event_id}"
        purse = self.w["currency"]["player"]
        new = ea.settle_entitlement(self.state(), event_id="wage:new:1", payer_id="thread-pool:new:1",
                                    recipient_id="player", amount_cp=40)
        self.assertEqual((new.status, new.replayed), ("applied", False))
        self.assertEqual(self.w["currency"]["player"], purse + 40)
        entitlements = self.w["flags"]["economic_ledger"]["entitlements"]
        self.assertEqual(len(entitlements), ea.LEDGER_ENTITLEMENTS_CAP)
        self.assertTrue(all(event_id in entitlements for event_id in recent))
        self.assertIn("wage:new:1", entitlements)
        self.assertEqual([event_id for event_id in old if event_id not in entitlements], old[:6])
        again = ea.settle_entitlement(self.state(), event_id=recent[0], payer_id="thread-pool:recent:0",
                                      recipient_id="player", amount_cp=40)
        self.assertEqual((again.replayed, again.net_debit_cp), (True, 0))
        self.assertEqual(self.w["currency"]["player"], purse + 40)

    def test_item_moves_never_push_money_operations_out(self):
        self.settle(self.offer(proposal(purpose="tip", recipient_id="farmer", amount_cp=5)), "op-tip")
        operations = self.w["flags"]["economic_ledger"]["operations"]
        for index in range(ea.LEDGER_ITEM_OPERATIONS_CAP + 50):
            operations[f"unscoped:economic:item_transfer:{index}"] = {
                "purpose": "item_transfer", "item_id": "i", "source_id": "player", "recipient_id": "farmer",
                "net_debit_cp": 0, "turn_index": 0}
        ea.settle_entitlement(self.state(), event_id="wage:job-1:9", payer_id="thread-pool:job-1:9",
                              recipient_id="player", amount_cp=1)
        operations = self.w["flags"]["economic_ledger"]["operations"]
        items = [key for key, entry in operations.items() if entry["purpose"] == "item_transfer"]
        self.assertEqual(len(items), ea.LEDGER_ITEM_OPERATIONS_CAP)
        self.assertEqual(items[0], "unscoped:economic:item_transfer:50")
        self.assertIn("op-tip", operations)
        self.assertIn("entitlement:wage:job-1:9", operations)
        for index in range(ea.LEDGER_OPERATIONS_CAP + 1):
            operations[f"filler-{index}"] = {"offer_id": None, "purpose": "tip", "net_debit_cp": 0, "turn_index": 0}
        ea.trim_operations(operations)
        self.assertEqual(len([key for key, entry in operations.items() if entry["purpose"] == "item_transfer"]),
                         ea.LEDGER_ITEM_OPERATIONS_CAP)
        self.assertEqual(len([key for key, entry in operations.items() if entry["purpose"] != "item_transfer"]),
                         ea.LEDGER_OPERATIONS_CAP)
        self.assertNotIn("op-tip", operations)


class TenderAndChange(ResolutionFixture):
    def test_tender_change_is_accounting_not_gift(self):
        result = self.settle(self.offer(proposal(purpose="tip", recipient_id="barman", amount_cp=3, tender_cp=100)))
        self.assertEqual((result.status, result.change_cp, result.net_debit_cp, result.tender_cp),
                         ("applied", 97, 3, 100))
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["barman"]), (97, 3))

    def test_tender_exceeds_wallet_changes_nothing(self):
        self.w["currency"]["player"] = 3
        before = self.snapshot()
        result = self.settle(self.offer(proposal(purpose="tip", recipient_id="barman", amount_cp=3, tender_cp=100)))
        self.assertEqual((result.status, result.reason_code, result.asset_deltas), ("refused", "tender_invalid", []))
        self.assertEqual(self.snapshot(), before)

    def test_tender_covers_base_refuses_tip(self):
        result = self.settle(self.offer(room(recipient_id="barman", tip_cp=5, tender_cp=52)))
        self.assertEqual(result.status, "applied")
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["barman"], self.sink()), (50, 0, 50))
        self.assertEqual([(r.line_id, r.reason_code) for r in result.refusals], [("tip:1", "tender_short")])
        self.assertEqual(result.change_cp, 2)


class AppliedOnceOnACopyFirst(ResolutionFixture):
    def test_reserved_funds_refused_on_copy_before_live_write(self):
        self.w["currency"]["player"] = 60
        self.w["item_rewards"] = {"reward-1": {"currency_cp": 50, "origin": equipment_native.ORIGIN,
                                               "source_npc_id": "player"}}
        offer = self.offer(room(recipient_id="barman"))
        resolution = self.resolve(offer)
        self.assertEqual(resolution.status, "applied")  # the plain purse covers it; the copy finds the reserve
        currency, sinks = json.dumps(self.w["currency"], sort_keys=True), self.sink()
        result = self.apply(resolution, offer)
        self.assertEqual((result.status, result.reason_code, result.asset_deltas), ("refused", "no_money", []))
        self.assertEqual(json.dumps(self.w["currency"], sort_keys=True), currency)
        self.assertEqual(self.sink(), sinks)
        self.assertNotIn("economic_ledger", self.w["flags"])

    def test_reused_operation_id_is_rejected(self):
        offer = self.offer(proposal(purpose="tip", recipient_id="barman", amount_cp=5))
        resolution = self.resolve(offer, "op-same")
        self.apply(resolution, offer)
        before = copy.deepcopy(self.w)
        with self.assertRaises(ea.EconomicReceiptError) as raised:
            self.apply(resolution, offer)
        self.assertEqual(raised.exception.reason, "operation_id_reused")
        self.assertEqual(self.w, before)

    def test_no_partial_assets_after_grant_failure(self):
        offer = self.offer(room(recipient_id="barman", tip_cp=5))
        resolution = self.resolve(offer)
        before = self.snapshot()
        live = self.w

        def fails_on_the_copy(world):
            if world is not live:
                raise equipment_economy.EquipmentError("duplicate_item_identity")

        with patch.object(equipment_economy, "validate_world", side_effect=fails_on_the_copy):
            with self.assertRaises(ea.EconomicReceiptError):
                self.apply(resolution, offer)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.has_room())

    def test_legacy_coin_total_is_not_double_counted(self):
        self.w["currency"]["player"] = 30
        self.w["inventory"] = [*self.w.get("inventory", []), "1 Altın"]
        result = self.settle(self.offer(room(recipient_id="barman")))
        self.assertEqual(result.status, "applied")
        self.assertEqual(self.w["currency"]["player"], 80)
        self.assertNotIn("1 Altın", [item.get("name") if isinstance(item, dict) else item
                                     for item in self.w["inventory"]])
        facts = ea.economic_facts(self.state())
        self.assertEqual(facts.balances["player"], 80)
        self.assertEqual(facts.sink_totals, {self.sink_id: 50})

    def test_world_effect_applies_atomically_with_debit(self):
        deed = self.theft_held_by_guard()
        self.w["currency"]["guard"] = 0
        offer = self.offer(proposal(purpose="gift", recipient_id="guard", amount_cp=100))
        self.assertEqual(offer.on_accept, [ea.WorldEffect(kind="bribe_accepted", npc_id="guard")])
        resolution = self.resolve(offer, check=lambda skill, dc: "BAŞARILI")
        self.assertEqual(resolution.world_effects, offer.on_accept)
        live = self.w
        with patch.object(equipment_economy, "validate_world",
                          side_effect=lambda world: (_ for _ in ()).throw(
                              equipment_economy.EquipmentError("boom")) if world is not live else None):
            with self.assertRaises(ea.EconomicReceiptError):
                self.apply(resolution, offer)
        self.assertIn("hold", deed)
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["guard"]), (100, 0))
        result = self.apply(resolution, offer)
        self.assertEqual(result.status, "applied")
        self.assertNotIn("hold", deed)
        self.assertIs(self.w["flags"]["deeds"][-1], deed)
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["guard"]), (0, 100))

    def test_failed_bribe_check_moves_nothing(self):
        deed = self.theft_held_by_guard()
        offer = self.offer(proposal(purpose="gift", recipient_id="guard", amount_cp=100))
        before = self.snapshot()
        seen = []
        result = self.settle(offer, check=lambda skill, dc: seen.append((skill, dc)) or "BAŞARISIZ")
        self.assertEqual((result.status, result.reason_code, result.world_effects), ("refused", "check_failed", []))
        self.assertEqual(seen[0][0], "Persuasion")
        self.assertIn("hold", deed)
        self.assertEqual(self.snapshot(), before)

    def test_resolve_offer_does_not_touch_live_state(self):
        self.w["inventory"] = [*self.w.get("inventory", []), "2 Altın"]
        offer = self.offer(room(recipient_id="barman", tip_cp=5))
        before = copy.deepcopy(self.w)
        resolution = self.resolve(offer)
        self.assertEqual(resolution.status, "applied")
        self.assertEqual(self.w, before)

    def test_apply_resolution_keeps_caller_references_live(self):
        self.w["threads"] = [{"thread_id": "job-1", "paid_cp": 0}]
        thread = self.w["threads"][0]
        npc = self.w["npcs"][0]
        wallets = self.w["currency"]
        flags = self.w["flags"]
        ea.settle_entitlement(self.state(), event_id="wage:job-1:1", payer_id="thread-pool:job-1:1",
                              recipient_id="player", amount_cp=40)
        self.settle(self.offer(room(recipient_id="barman", tip_cp=5)))
        self.assertIs(thread, self.w["threads"][0])
        self.assertIs(npc, self.w["npcs"][0])
        self.assertIs(wallets, self.w["currency"])
        self.assertIs(flags, self.w["flags"])
        self.assertEqual((wallets["player"], wallets["barman"]), (85, 5))
        self.assertEqual(flags["inn_room"]["place"], self.here)

    def test_apply_resolution_runs_receipt_validation(self):
        offer = self.offer(proposal(purpose="tip", recipient_id="barman", amount_cp=4))
        honest = self.resolve(offer)
        tampered = dataclasses.replace(
            honest, net_debit_cp=5, public_summary="5 bakır ödendi.",
            asset_deltas=[ea.AssetDelta("player", "currency", "cp", 100, 95),
                          ea.AssetDelta("barman", "currency", "cp", 0, 5)])
        currency = json.dumps(self.w["currency"], sort_keys=True)
        flags = json.dumps(self.w["flags"], sort_keys=True, ensure_ascii=False)
        with self.assertRaises(ea.EconomicReceiptError):
            self.apply(tampered, offer)
        self.assertEqual(json.dumps(self.w["currency"], sort_keys=True), currency)
        self.assertEqual(json.dumps(self.w["flags"], sort_keys=True, ensure_ascii=False), flags)
        self.assertEqual(self.apply(honest, offer).status, "applied")
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["barman"]), (96, 4))

    def test_base_fingerprint_uses_normalized_purse(self):
        self.w["currency"]["player"] = 0
        self.w["inventory"] = [*self.w.get("inventory", []), "8 Altın"]
        offer = self.offer(room(recipient_id="barman"))
        resolution = self.resolve(offer)
        self.assertEqual(resolution.status, "applied")
        result = self.apply(resolution, offer)
        self.assertEqual((result.status, result.reason_code), ("applied", None))
        self.assertEqual(self.w["currency"]["player"], 750)

    def test_changed_economy_since_resolution_is_stale(self):
        offer = self.offer(room(recipient_id="barman"))
        resolution = self.resolve(offer)
        self.w["currency"]["player"] = 90
        before = self.snapshot()
        result = self.apply(resolution, offer)
        self.assertEqual((result.status, result.reason_code), ("refused", "stale"))
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
