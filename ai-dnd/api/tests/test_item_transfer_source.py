"""A5: an item changes hands only from where it really is, and a valued or held one only with a card.

No real model is called. Session-level tests patch the model boundary to fail; the chat tests run the real app
with the scripted front reading of the errand fixtures, so a false yes from the model is only a reading.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import unittest
from unittest.mock import patch

import economic_actions as ea
import equipment_economy
import game
import pocket
import world_reactions
from api.core_resolution import resolution_action_scope
from api.tests import test_said_is_real as said


def holdings(world):
    """Who holds which item, the hands, the purses, the cards and the ledger: what a transfer could change."""
    owners = {str(owner): sorted(str(item.get("item_id") if isinstance(item, dict) else item) for item in items)
              for owner, items in equipment_economy.containers(world) if items}
    flags = world.get("flags") or {}
    return json.dumps({"owners": owners, "hands": world.get("equipment"), "currency": world.get("currency"),
                       "offers": flags.get("economic_offers"), "ledger": flags.get("economic_ledger"),
                       "consents": {npc.get("id"): npc.get("item_consents") for npc in world.get("npcs", [])}},
                      ensure_ascii=False, sort_keys=True)


def owners_of(world, item_id):
    return [owner for owner, items in equipment_economy.containers(world)
            for item in items if isinstance(item, dict) and item.get("item_id") == item_id]


def total_instances(world):
    return sum(len(items) for _, items in equipment_economy.containers(world))


class Bag(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.w = self.s.world_state
        self.here = self.w["location"]
        self.w["npcs"] = [
            {"id": "hanci", "name": "Marek", "role": "Hancı", "location": self.here, "current_hp": 10, "inventory": []},
            {"id": "guest", "name": "Oren", "role": "Yolcu", "location": self.here, "current_hp": 10, "inventory": []},
        ]
        self.w["currency"] = {"player": 500, "hanci": 100, "guest": 100}
        self.w["inventory"] = [
            {"item_id": "item_ring", "name": "Kırık halka"},
            {"item_id": "item_sword", "name": "Longsword", "weapon_id": "longsword"},
            {"item_id": "item_stick", "name": "Sopa"},
            {"item_id": "item_wand", "name": "Asa", "magical": True},
            {"item_id": "item_beer", "name": "Bira"},
            {"item_id": "item_shield", "name": "Shield"},
        ]
        self.w["equipment"] = {"main_hand": None, "off_hand": None}
        equipment_economy.materialize(self.w)
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)

    def npc(self, npc_id):
        return next(npc for npc in self.w["npcs"] if npc["id"] == npc_id)

    def item(self, item_id):
        return next(item for item in self.w["inventory"] if item.get("item_id") == item_id)

    def allow(self, item_id, npc_id="guest"):
        self.npc(npc_id).setdefault("item_consents", {})[item_id] = {"operation": "give", "recipient": npc_id}

    def give(self, item_id, npc_id="guest"):
        return equipment_economy.execute(self.s, f"/item give {item_id} {npc_id}")

    def offers(self):
        return (self.w.get("flags") or {}).get("economic_offers") or {}

    def prepared(self):
        return [data for data in self.offers().values() if data["status"] == "prepared"]

    def turn(self):
        return self.w["flags"].get("turn_index", 0)

    def confirm(self, data, action="confirm-1"):
        with resolution_action_scope(action, "session"):
            return ea.confirm_offer(ea.EconomicState(world=self.w, character=self.s.character),
                                    offer_id=data["offer_id"], confirmation_digest=data["confirmation_digest"],
                                    operation_id=f"offer:{action}", check=lambda skill, dc: "BAŞARILI")

    def shown(self, text):
        self.s.messages.append({"role": "assistant", "content": text})


class Source(Bag):
    def test_narrated_item_without_source_is_not_created(self):
        self.shown("Masanın üstünde mühürlü bir mektup duruyor.")
        before, total = holdings(self.w), total_instances(self.w)
        pocket.resolve(self.s, "mektubu çantama koyuyorum")
        pocket.take_named(self.s, "mektubu alıyorum", "mektup")
        self.assertEqual(total_instances(self.w), total)
        self.assertEqual(holdings(self.w), before)
        self.assertNotIn("Mektup", [equipment_economy.label(item) for item in self.w["inventory"]])

    def test_real_item_moves_once(self):
        ground = self.w.setdefault("ground_items_by_location", {}).setdefault(self.here, [])
        ground.append({"item_id": "item_letter", "name": "Defter"})
        self.shown("Masanın dibinde eski bir defter duruyor.")
        total = total_instances(self.w)
        source_before = len(ground)
        recipient_before = len(self.w["inventory"])
        taken = pocket.resolve(self.s, "defteri çantama koyuyorum")
        self.assertIsNotNone(taken)
        self.assertEqual(owners_of(self.w, "item_letter"), ["player"])
        self.assertEqual(total_instances(self.w), total)
        self.assertEqual(len(self.w["ground_items_by_location"][self.here]), source_before - 1)
        self.assertEqual(len(self.w["inventory"]), recipient_before + 1)
        again = holdings(self.w)
        pocket.resolve(self.s, "defteri çantama koyuyorum")
        pocket.take_named(self.s, "defteri alıyorum", "defter")
        self.assertEqual(owners_of(self.w, "item_letter"), ["player"])
        self.assertEqual(total_instances(self.w), total)
        self.assertEqual([equipment_economy.label(item) for item in self.w["inventory"]].count("Defter"), 1)
        self.assertEqual(json.loads(holdings(self.w))["owners"], json.loads(again)["owners"])

    def test_wrong_location_cannot_pick_up(self):
        self.w.setdefault("ground_items_by_location", {})["somewhere_else"] = [{"item_id": "item_letter",
                                                                                "name": "Defter"}]
        self.shown("Masanın dibinde eski bir defter duruyor.")
        before, total = holdings(self.w), total_instances(self.w)
        pocket.resolve(self.s, "defteri çantama koyuyorum")
        pocket.take_named(self.s, "defteri alıyorum", "defter")
        self.assertEqual(owners_of(self.w, "item_letter"), ["ground:somewhere_else"])
        self.assertEqual(total_instances(self.w), total)
        self.assertEqual(holdings(self.w), before)

    def test_real_gift_needs_no_card(self):
        self.allow("item_ring")
        total = total_instances(self.w)
        result = self.give("item_ring")
        self.assertTrue(result["action_result"]["success"], result["narration"])
        self.assertEqual(owners_of(self.w, "item_ring"), ["guest"])
        self.assertEqual(self.offers(), {})
        self.assertEqual(total_instances(self.w), total)
        self.assertNotIn("item_ring", self.npc("guest").get("item_consents", {}))


class NeedsCard(Bag):
    def test_priced_item_needs_card(self):
        import item_transfers
        self.assertTrue(item_transfers.item_needs_card(self.w, self.item("item_sword")))

    def test_magic_item_needs_card(self):
        import item_transfers
        self.assertTrue(item_transfers.item_needs_card(self.w, self.item("item_wand")))

    def test_shop_label_item_needs_card(self):
        import item_transfers
        import shop_trade
        self.assertEqual(shop_trade.priced_in("Bira")[2], 4)
        self.assertTrue(item_transfers.item_needs_card(self.w, self.item("item_beer")))

    def test_held_weapon_needs_card(self):
        import item_transfers
        self.assertFalse(item_transfers.item_needs_card(self.w, self.item("item_stick")))
        self.w["equipment"]["main_hand"] = "item_stick"
        self.assertTrue(item_transfers.item_needs_card(self.w, self.item("item_stick")))

    def test_string_item_uses_catalog_lookup(self):
        import item_transfers
        before = holdings(self.w)
        self.assertTrue(item_transfers.item_needs_card(self.w, "Greataxe"))
        self.assertEqual(holdings(self.w), before)

    def test_plain_unpriced_item_needs_no_card(self):
        import item_transfers
        before = holdings(self.w)
        self.assertFalse(item_transfers.item_needs_card(self.w, self.item("item_ring")))
        self.assertFalse(item_transfers.item_needs_card(self.w, "Kırık halka"))
        self.assertEqual(holdings(self.w), before)

    def test_coin_label_is_money_not_item_gift(self):
        self.w["inventory"].append("8 Altın")
        equipment_economy.materialize(self.w)
        label = next(item for item in self.w["inventory"] if item["name"] == "8 Altın")
        self.allow(label["item_id"])
        before = holdings(self.w)
        refused = self.give(label["item_id"])
        self.assertFalse(refused["action_result"]["success"])
        self.assertEqual(holdings(self.w), before)
        state = ea.EconomicState(world=self.w, character=self.s.character)
        as_item = ea.prepare_offer(state, dataclasses.replace(
            ea.turn_proposal("item_gift", "guest"), item_id=label["item_id"], source_id="player",
            source_action_id="turn:t"), offer_id="o1", campaign_id="c", actor_id="player", turn_index=0)
        self.assertNotEqual(as_item.status, "prepared")
        as_money = ea.prepare_offer(state, dataclasses.replace(
            ea.turn_proposal("gift", "guest", amount_cp=1200), source_action_id="turn:t"),
            offer_id="o2", campaign_id="c", actor_id="player", turn_index=0)
        self.assertEqual(as_money.status, "prepared", as_money.public_message)
        self.assertEqual(holdings(self.w), before)


class ArmorAndHands(Bag):
    def test_item_give_prepare_refusal_does_not_advance_turn(self):
        self.allow("item_sword")
        before, turn = holdings(self.w), self.turn()
        with patch.object(world_reactions, "refuses", side_effect=lambda world, npc: npc.get("id") == "guest"):
            result = self.give("item_sword")
        self.assertFalse(result["action_result"]["success"])
        self.assertEqual(result["action_result"]["status"], "rejected")
        self.assertEqual(result["action_result"]["reason"], "npc_refuses")
        self.assertEqual(self.turn(), turn)
        self.assertEqual(holdings(self.w), before)

    def test_plain_item_give_records_item_transfer_operation(self):
        self.allow("item_ring")
        seq = self.w["flags"].get("economic_ledger", {}).get("operation_seq", 0)
        result = self.give("item_ring")
        self.assertTrue(result["action_result"]["success"], result["narration"])
        ledger = self.w["flags"]["economic_ledger"]
        self.assertEqual(ledger["operation_seq"], seq + 1)
        self.assertIn(f"unscoped:economic:item_transfer:{seq + 1}", ledger["operations"])

    def test_direct_execute_item_card_has_source_action_id(self):
        self.allow("item_sword")
        result = self.give("item_sword")
        self.assertTrue(result["action_result"]["success"], result["narration"])
        [card] = self.prepared()
        source = card["proposal"]["source_action_id"]
        self.assertIsInstance(source, str)
        self.assertTrue(source.startswith("turn:"), source)

    def test_catalog_armor_item_gift_refused(self):
        import item_transfers
        self.allow("item_shield")
        before, turn = holdings(self.w), self.turn()
        result = self.give("item_shield")
        self.assertFalse(result["action_result"]["success"])
        self.assertEqual(result["action_result"]["reason"], "armor_owner_required")
        self.assertIn("Dünya durumu değişmedi", result["narration"])
        self.assertEqual((holdings(self.w), self.turn()), (before, turn))
        state = ea.EconomicState(world=self.w, character=self.s.character)
        prepared = ea.prepare_offer(state, dataclasses.replace(
            ea.turn_proposal("item_gift", "guest"), item_id="item_shield", source_id="player",
            source_action_id="turn:t"), offer_id="o1", campaign_id="c", actor_id="player", turn_index=0)
        self.assertEqual((prepared.status, prepared.reason_code), ("refused", "armor_owner_required"))
        moved = item_transfers.transfer_existing_item(state, item_id="item_shield", source_id="player",
                                                      recipient_id="guest", count=1, operation_id="op:shield")
        self.assertEqual((moved.status, moved.reason_code), ("refused", "armor_owner_required"))
        self.assertEqual(holdings(self.w), before)

    def test_given_held_sword_clears_main_hand(self):
        self.w["equipment"]["main_hand"] = "item_sword"
        self.allow("item_sword")
        total = total_instances(self.w)
        self.give("item_sword")
        self.assertEqual(self.w["equipment"]["main_hand"], "item_sword")
        [card] = self.prepared()
        resolution = self.confirm(card)
        self.assertEqual(resolution.status, "applied", resolution.public_summary)
        self.assertIsNone(self.w["equipment"]["main_hand"])
        self.assertEqual(owners_of(self.w, "item_sword"), ["guest"])
        self.assertEqual(total_instances(self.w), total)

    def test_item_give_command_opens_card_for_valuable_item(self):
        from api.serializers import serialize_session_state
        self.allow("item_sword")
        candidate = copy.deepcopy(self.w)
        request = equipment_economy._apply(candidate, "give", ["item_sword", "guest"])
        self.assertIsInstance(request, equipment_economy.ItemCardRequest)
        self.assertEqual(request.proposal.purpose, "item_gift")
        self.assertEqual(owners_of(candidate, "item_sword"), ["player"])
        self.assertNotIn("economic_offers", candidate.get("flags") or {})
        turn = self.turn()
        with patch.object(ea, "prepare_from_turn", wraps=ea.prepare_from_turn) as prepare:
            result = self.give("item_sword")
        prepare.assert_called_once()
        self.assertIs(prepare.call_args.args[0], self.s)
        self.assertEqual(result["action_result"]["status"], "offered")
        self.assertEqual(result["action_result"]["npc_id"], "guest")
        self.assertEqual(self.turn(), turn + 1)
        self.assertEqual(owners_of(self.w, "item_sword"), ["player"])
        [card] = self.prepared()
        self.assertEqual(card["proposal"]["purpose"], "item_gift")
        self.assertEqual(card["lines"][0]["kind"], "item")
        projected = serialize_session_state(self.s)["economic_offer"]
        self.assertIsNotNone(projected)
        self.assertEqual(projected["offer_id"], card["offer_id"])

    def test_valuable_item_give_without_consent_opens_no_card(self):
        before = holdings(self.w)
        refused = self.give("item_sword")
        self.assertFalse(refused["action_result"]["success"])
        self.assertEqual(refused["action_result"]["reason"], "npc_consent_required")
        self.assertEqual(holdings(self.w), before)
        self.allow("item_sword")
        self.give("item_sword")
        self.assertEqual(self.npc("guest")["item_consents"], {"item_sword": {"operation": "give",
                                                                             "recipient": "guest"}})
        [card] = self.prepared()
        self.assertEqual(self.confirm(card).status, "applied")
        self.assertEqual(self.npc("guest")["item_consents"], {})
        self.npc("guest")["inventory"].remove(next(i for i in self.npc("guest")["inventory"]
                                                   if i["item_id"] == "item_sword"))
        self.w["inventory"].append({"item_id": "item_sword", "name": "Longsword", "weapon_id": "longsword"})
        again = holdings(self.w)
        second = self.give("item_sword")
        self.assertEqual(second["action_result"]["reason"], "npc_consent_required")
        self.assertEqual(holdings(self.w), again)

    def test_item_gift_live_write_updates_inventories_and_hands(self):
        self.w["equipment"]["main_hand"] = "item_sword"
        self.allow("item_sword")
        self.give("item_sword")
        world, guest = self.w, self.npc("guest")  # the live references the confirm must keep writing into
        [card] = self.prepared()
        self.assertEqual(self.confirm(card).status, "applied")
        self.assertIs(self.s.world_state, world)
        self.assertIs(self.npc("guest"), guest)
        self.assertIn("item_sword", [item["item_id"] for item in guest["inventory"]])
        self.assertNotIn("item_sword", [item["item_id"] for item in world["inventory"]])
        self.assertIsNone(world["equipment"]["main_hand"])


class ValuedCard(Bag):
    def test_valuable_item_gift_needs_card(self):
        self.allow("item_sword")
        self.give("item_sword")
        self.assertEqual(owners_of(self.w, "item_sword"), ["player"])
        [card] = self.prepared()
        first = self.confirm(card)
        self.assertEqual(first.status, "applied")
        self.assertEqual(owners_of(self.w, "item_sword"), ["guest"])
        settled = holdings(self.w)
        second = self.confirm(card, action="confirm-2")
        self.assertEqual(second.reason_code, "offer_not_prepared")
        self.assertEqual(owners_of(self.w, "item_sword"), ["guest"])
        self.assertEqual(json.loads(holdings(self.w))["owners"], json.loads(settled)["owners"])

    def test_item_gift_resolution_carries_item_deltas(self):
        self.allow("item_sword")
        self.give("item_sword")
        [data] = self.prepared()
        offer = ea.offer_from_record(data)
        state = ea.EconomicState(world=self.w, character=self.s.character)
        resolution = ea.resolve_offer(state, offer, operation_id="offer:probe")
        items = sorted((delta.owner_id, delta.before, delta.after)
                       for delta in resolution.asset_deltas if delta.asset_kind == "item")
        self.assertEqual(items, [("guest", 0, 1), ("player", 1, 0)])
        self.assertEqual(resolution.net_debit_cp, 0)
        before = holdings(self.w)
        wrong = dataclasses.replace(resolution, asset_deltas=[
            dataclasses.replace(delta, after=delta.after + 1) if delta.owner_id == "guest" else delta
            for delta in resolution.asset_deltas])
        with self.assertRaises(ea.EconomicReceiptError):
            ea.apply_resolution(state, wrong, confirmed_offer=offer)
        self.assertEqual(holdings(self.w), before)
        applied = self.confirm(data)
        self.assertEqual(applied.status, "applied")
        self.assertEqual(sorted((d.owner_id, d.before, d.after) for d in applied.asset_deltas
                                if d.asset_kind == "item"), items)


class ChatGive(said.ErrandBase):
    """The model's reading may say a hand-over; only a plain thing the line really gives moves."""

    async def bag_with(self, *items, hand=None):
        await self.errand()
        self.world["inventory"].extend(copy.deepcopy(list(items)))
        if hand is not None:
            self.world["equipment"] = {"main_hand": hand, "off_hand": None}
        equipment_economy.materialize(self.world)

    async def test_negated_handover_moves_nothing(self):
        await self.bag_with({"item_id": "item_ring", "name": "Kırık halka"})
        self.client.front = {"kind": "hand_over", "person_id": self.owner["id"], "item_id": "item_ring"}
        state_before_negated_transfer = holdings(self.world)
        total = total_instances(self.world)
        await self.line("halkayi sana vermiyorum usta, bende kalsin", "Peki.")
        state_after_negated_transfer = holdings(self.world)
        self.assertEqual(state_after_negated_transfer, state_before_negated_transfer)
        self.assertEqual(total_instances(self.world), total)

    async def test_chat_give_moves_nothing_as_today(self):
        await self.bag_with({"item_id": "item_sword", "name": "Longsword", "weapon_id": "longsword"},
                            hand="item_sword")
        self.client.front = {"kind": "hand_over", "person_id": self.owner["id"], "item_id": "item_sword"}
        before = holdings(self.world)
        await self.line("kilici ona veriyorum", "Sağ ol.")
        self.assertEqual(holdings(self.world), before)
        self.assertEqual(self.world["equipment"]["main_hand"], "item_sword")
        text, stem = pocket.settle_claim(self.session, {"item": "Longsword", "to": "person"},
                                         "Longsword artık onda.", self.owner)
        self.assertTrue(stem)
        self.assertNotIn("Longsword", text)
        self.assertEqual(holdings(self.world), before)

    async def test_creation_armor_gift_refused_ac_unchanged(self):
        await self.bag_with({"item_id": "item_mail", "name": "Zincir Zırh"})
        ac = self.session.character.get("armor_class")
        self.client.front = {"kind": "hand_over", "person_id": self.owner["id"], "item_id": "item_mail"}
        before = holdings(self.world)
        await self.line("zincir zirhimi hanciya veriyorum", "Sağ ol.")
        self.assertEqual(holdings(self.world), before)
        self.assertEqual(self.session.character.get("armor_class"), ac)
        self.owner.setdefault("item_consents", {})["item_mail"] = {"operation": "give",
                                                                   "recipient": self.owner["id"]}
        before = holdings(self.world)
        turn = self.world["flags"].get("turn_index", 0)
        fingerprint = json.dumps(self.session.serialize_game_state(), sort_keys=True, ensure_ascii=False)
        result = equipment_economy.execute(self.session, f"/item give item_mail {self.owner['id']}")
        self.assertIs(result["action_result"]["success"], False)
        self.assertEqual(result["action_result"]["status"], "rejected")
        self.assertEqual(result["action_result"]["reason"], "armor_owner_required")
        self.assertIn("Dünya durumu değişmedi", result["narration"])
        self.assertEqual(holdings(self.world), before)
        self.assertEqual(self.world["flags"].get("turn_index", 0), turn)
        self.assertEqual(self.session.character.get("armor_class"), ac)
        self.assertEqual(json.dumps(self.session.serialize_game_state(), sort_keys=True, ensure_ascii=False),
                         fingerprint)


if __name__ == "__main__":
    unittest.main()
