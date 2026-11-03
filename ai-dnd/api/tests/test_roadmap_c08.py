"""C08: structured item use and transfer go through the existing equipment owner, never around it.

`equipment_rules.resolve_item_use` / `inventory_transfer` map onto `equipment_economy`'s atomic operations: an applied action gives
the same result as the owner's own command, a repeated action has no second effect, a rejection leaves the world unchanged, and
no PHB equipment entry is reported complete (catalog coverage is C04's, lifecycle evidence is C01's).
"""
from __future__ import annotations

import copy
import unittest

import equipment_economy as economy
import equipment_rules
from capabilities import capability_status


def world():
    return {
        "location": "inn",
        "flags": {"turn_index": 0},
        "inventory": [
            {"item_id": "item_000001", "name": "Dagger", "weapon_id": "dagger"},
            {"item_id": "item_000002", "name": "Longsword", "weapon_id": "longsword"},
            {"item_id": "item_000003", "name": "Greatsword", "weapon_id": "greatsword"},
        ],
        "equipment": {"main_hand": None, "off_hand": None},
        "currency": {"player": 500, "vendor": 100},
        "item_sequence": 3,
        "npcs": [{"id": "vendor", "name": "Vendor", "location": "inn", "inventory": [], "item_consents": {}}],
        "ground_items_by_location": {"inn": []},
    }


NOTE = "item_000004"


def with_note(w):
    """A plain thing of no worth: the only kind the kernel hands to a person without a card (step 0, K5)."""
    w["inventory"].append({"item_id": NOTE, "name": "Folded note"})
    w["item_sequence"] = 4
    return w


class TransferTests(unittest.TestCase):
    def test_item_kernel_preserves_existing_use_and_transfer(self):
        mine, owner = world(), world()
        delta = equipment_rules.inventory_transfer(mine, "player", "ground", "item_000001")
        economy._apply(owner, "drop", ["item_000001"])
        self.assertEqual(delta["status"], "applied")
        self.assertEqual(mine, owner, "the same result as the owner's own command")
        self.assertEqual([i["item_id"] for i in mine["ground_items_by_location"]["inn"]], ["item_000001"])
        back = equipment_rules.inventory_transfer(mine, "ground", "player", "item_000001")
        self.assertEqual(back["status"], "applied")
        self.assertEqual(back["changes"][0]["to"], "player")
        self.assertIn("item_000001", [i["item_id"] for i in mine["inventory"]])

    def test_repeating_an_applied_action_has_no_second_effect(self):
        w = world()
        equipment_rules.inventory_transfer(w, "player", "ground", "item_000001")
        after_first = copy.deepcopy(w)
        again = equipment_rules.inventory_transfer(w, "player", "ground", "item_000001")
        self.assertEqual((again["status"], again["reason"]), ("rejected", "item_not_owned"))
        self.assertEqual(w, after_first)
        self.assertEqual(w["currency"], {"player": 500, "vendor": 100})

    def test_npc_gift_needs_consent_and_consent_is_spent_once(self):
        w = with_note(world())
        denied = equipment_rules.inventory_transfer(w, "player", "vendor", NOTE)
        self.assertEqual((denied["status"], denied["reason"]), ("rejected", "npc_consent_required"))
        self.assertEqual(w, with_note(world()))
        w["npcs"][0]["item_consents"] = {NOTE: {"operation": "give", "recipient": "vendor"}}
        ok = equipment_rules.inventory_transfer(w, "player", "vendor", NOTE)
        self.assertEqual(ok["status"], "applied")
        self.assertEqual(w["npcs"][0]["item_consents"], {})
        self.assertEqual([i["item_id"] for i in w["npcs"][0]["inventory"]], [NOTE])
        self.assertNotIn(NOTE, [i["item_id"] for i in w["inventory"]])
        snapshot = copy.deepcopy(w)
        self.assertEqual(equipment_rules.inventory_transfer(w, "player", "vendor", NOTE)["status"], "rejected")
        self.assertEqual(w, snapshot)

    def test_a_valued_gift_needs_its_card_and_moves_or_spends_nothing_here(self):
        # Step 0 (K5): a priced dagger goes only through `/item give` and its card; the kernel neither moves it nor
        # spends the consent, and never reports a card request as applied.
        w = world()
        w["npcs"][0]["item_consents"] = {"item_000001": {"operation": "give", "recipient": "vendor"}}
        before = copy.deepcopy(w)
        refused = equipment_rules.inventory_transfer(w, "player", "vendor", "item_000001")
        self.assertEqual((refused["status"], refused["reason"], refused["changes"]),
                         ("rejected", "item_card_required", []))
        self.assertEqual(w, before)

    def test_stacks_unknown_routes_and_unknown_items_are_rejected_without_change(self):
        for args, reason in (
            (("player", "ground", "item_000001", 2), "stack_quantity_unsupported"),
            (("player", "ground", "item_000001", True), "stack_quantity_unsupported"),
            (("vendor", "ground", "item_000001", 1), "transfer_route_unsupported"),
            (("player", "ground", "item_999999", 1), "item_not_owned"),
            (("player", "nobody", "item_000001", 1), "npc_unknown"),
        ):
            w = world()
            delta = equipment_rules.inventory_transfer(w, *args)
            self.assertEqual((delta["status"], delta["reason"]), ("rejected", reason), args)
            self.assertEqual(w, world(), args)


class UseTests(unittest.TestCase):
    def test_equip_unequip_use_the_owner_rules(self):
        w = world()
        self.assertEqual(equipment_rules.resolve_item_use(w, "item_000002", {"use": "equip", "hand": "main_hand"})["status"], "applied")
        self.assertEqual(w["equipment"]["main_hand"], "item_000002")
        occupied = equipment_rules.resolve_item_use(w, "item_000001", {"use": "equip", "hand": "main_hand"})
        self.assertEqual((occupied["status"], occupied["reason"]), ("rejected", "hand_occupied"))
        two_handed = equipment_rules.resolve_item_use(w, "item_000003", {"use": "equip", "hand": "off_hand"})
        self.assertEqual(two_handed["reason"], "two_handed_owner_required")
        self.assertEqual(equipment_rules.resolve_item_use(w, "item_000002", {"use": "unequip", "hand": "main_hand"})["status"], "applied")
        self.assertIsNone(w["equipment"]["main_hand"])

    def test_dropping_an_equipped_item_clears_the_hand(self):
        w = world()
        equipment_rules.resolve_item_use(w, "item_000002", {"use": "equip", "hand": "main_hand"})
        equipment_rules.resolve_item_use(w, "item_000002", {"use": "drop"})
        self.assertIsNone(w["equipment"]["main_hand"])

    def test_unknown_use_unknown_item_and_non_weapons_are_rejected_not_faked(self):
        w = world()
        w["inventory"].append({"item_id": "item_000004", "name": "Mystery Potion"})
        for item, choice, reason in (
            ("item_000001", {"use": "drink"}, "unsupported_use"),
            ("item_000001", {}, "unsupported_use"),
            ("item_000001", None, "unsupported_use"),
            ("item_999999", {"use": "equip", "hand": "main_hand"}, "item_not_owned"),
            ("item_000004", {"use": "equip", "hand": "main_hand"}, "unsupported_equipment"),
            ("item_000001", {"use": "equip", "hand": "tail"}, "unsupported_equipment"),
        ):
            before = copy.deepcopy(w)
            delta = equipment_rules.resolve_item_use(w, item, choice)
            self.assertEqual((delta["status"], delta["reason"]), ("rejected", reason), (item, choice))
            self.assertEqual(w, before)
            self.assertEqual(delta["changes"], [])

    def test_an_invalid_world_is_not_committed(self):
        w = world()
        w["inventory"].append({"item_id": "item_000001", "name": "Dagger copy"})  # duplicate identity
        before = copy.deepcopy(w)
        self.assertEqual(equipment_rules.inventory_transfer(w, "player", "ground", "item_000002")["status"], "rejected")
        self.assertEqual(w, before)


class ReviewHardeningTests(unittest.TestCase):
    """Findings of the independent C08 review."""

    def test_every_applied_move_reports_item_transfer_with_from_and_to(self):
        w = with_note(world())
        drop = equipment_rules.inventory_transfer(w, "player", "ground", "item_000001")
        self.assertEqual(drop["changes"], [{"kind": "item_transfer", "item_id": "item_000001", "name": "Dagger",
                                            "from": "player", "to": "ground:inn"}])
        w["npcs"][0]["item_consents"] = {NOTE: {"operation": "give", "recipient": "vendor"}}
        give = equipment_rules.inventory_transfer(w, "player", "npc:vendor", NOTE)
        self.assertEqual(give["changes"], [{"kind": "item_transfer", "item_id": NOTE, "name": "Folded note",
                                            "from": "player", "to": "vendor"}])
        w["npcs"][0]["item_consents"] = {NOTE: {"operation": "receive", "recipient": "player"}}
        got = equipment_rules.inventory_transfer(w, "npc:vendor", "player", NOTE)
        self.assertEqual((got["status"], got["changes"][0]["from"], got["changes"][0]["to"]), ("applied", "vendor", "player"))
        equip = equipment_rules.resolve_item_use(w, "item_000002", {"use": "equip", "hand": "main_hand"})
        self.assertEqual(equip["changes"][0]["kind"], "equipment")

    def test_effects_pending_names_any_item_that_is_not_a_plain_catalog_weapon(self):
        w = world()
        w["inventory"].append({"item_id": "item_000004", "name": "Mystery Potion"})
        w["inventory"].append({"item_id": "item_000005", "name": "Longsword +1", "weapon_id": "longsword", "magic_attack_bonus": 1})
        self.assertEqual(equipment_rules.inventory_transfer(w, "player", "ground", "item_000004")["effects_pending"],
                         ["effect_unmodelled:Mystery Potion"])
        self.assertEqual(equipment_rules.inventory_transfer(w, "player", "ground", "item_000005")["effects_pending"],
                         ["effect_unmodelled:Longsword +1"])
        self.assertEqual(equipment_rules.inventory_transfer(w, "player", "ground", "item_000001")["effects_pending"], [])

    def test_npc_ids_work_with_or_without_the_prefix_and_dead_npcs_are_looted_by_bare_id(self):
        w = with_note(world())
        w["npcs"][0]["item_consents"] = {NOTE: {"operation": "give", "recipient": "vendor"}}
        self.assertEqual(equipment_rules.inventory_transfer(w, "player", "vendor", NOTE)["status"], "applied")
        w["npcs"][0].update(dead=True)
        loot = equipment_rules.inventory_transfer(w, "vendor", "player", NOTE)
        self.assertEqual((loot["status"], loot["changes"][0]["from"], loot["changes"][0]["to"]),
                         ("applied", "vendor", "player"))
        self.assertIn(NOTE, [i["item_id"] for i in w["inventory"]])
        self.assertEqual(w["npcs"][0]["inventory"], [])
        living = world()
        living["npcs"][0]["inventory"] = [{"item_id": "item_000009", "name": "Coin Purse"}]
        refused = equipment_rules.inventory_transfer(living, "vendor", "player", "item_000009")
        self.assertEqual(refused["reason"], "loot_actor_not_defeated")
        dead_give = world()
        dead_give["npcs"][0].update(dead=True)
        self.assertEqual(equipment_rules.inventory_transfer(dead_give, "player", "vendor", "item_000001")["reason"], "npc_unavailable")

    def test_non_string_ids_and_self_routes_are_rejected_not_raised(self):
        for args in ((None, "player", "item_000001"), ("player", None, "item_000001"), ("player", "ground", None),
                     ("player", "ground", ""), ("player", "player", "item_000001"), ("player", "surface:desk", "item_000001")):
            w = world()
            delta = equipment_rules.inventory_transfer(w, *args)
            self.assertEqual(delta["status"], "rejected", args)
            self.assertEqual(w, world(), args)
        self.assertEqual(equipment_rules.resolve_item_use(world(), None, {"use": "drop"})["reason"], "unsupported_use")

    def test_armor_and_shields_stay_with_the_armor_owner(self):
        w = world()
        w["inventory"] += [{"item_id": "item_000004", "name": "Chain Mail"}, {"item_id": "item_000005", "name": "Shield"}]
        for item in ("item_000004", "item_000005"):
            for delta in (equipment_rules.inventory_transfer(w, "player", "ground", item),
                          equipment_rules.resolve_item_use(w, item, {"use": "equip", "hand": "off_hand"})):
                self.assertEqual(delta["status"], "rejected", item)
        self.assertEqual(equipment_rules.inventory_transfer(w, "player", "ground", "item_000004")["reason"], "armor_owner_required")
        self.assertEqual({i["item_id"] for i in w["inventory"]} >= {"item_000004", "item_000005"}, True)

    def test_parity_with_the_owner_for_equip_take_and_give_and_double_equip(self):
        for build, mine_call, owner_call in (
            (world, lambda w: equipment_rules.resolve_item_use(w, "item_000002", {"use": "equip", "hand": "main_hand"}),
             lambda w: economy._apply(w, "equip", ["item_000002", "main_hand"])),
        ):
            mine, owner = build(), build()
            mine_call(mine)
            owner_call(owner)
            self.assertEqual(mine, owner)
            again = equipment_rules.resolve_item_use(mine, "item_000002", {"use": "equip", "hand": "main_hand"})
            self.assertEqual(again["reason"], "hand_occupied")
            self.assertEqual(mine, owner)
        a, b = world(), world()
        a["ground_items_by_location"]["inn"] = b["ground_items_by_location"]["inn"] = [{"item_id": "item_000009", "name": "Rope"}]
        equipment_rules.inventory_transfer(a, "ground", "player", "item_000009")
        economy._apply(b, "take", ["item_000009"])
        self.assertEqual(a, b)
        a, b = world(), world()
        for w in (a, b):
            w["npcs"][0]["item_consents"] = {"item_000001": {"operation": "give", "recipient": "vendor"}}
        equipment_rules.inventory_transfer(a, "player", "vendor", "item_000001")
        economy._apply(b, "give", ["item_000001", "vendor"])
        self.assertEqual(a, b)

    def test_legacy_string_items_are_materialised_by_the_owner_not_by_this_kernel(self):
        w = world()
        w["inventory"] = ["Dagger"]
        delta = equipment_rules.inventory_transfer(w, "player", "ground", "item_000099")
        self.assertEqual(delta["reason"], "item_not_owned")
        self.assertEqual(w["inventory"], ["Dagger"], "a rejection leaves even the legacy shape untouched")
        ok = equipment_rules.inventory_transfer(w, "player", "ground", "item_000004")  # the owner assigns the next sequence id
        self.assertEqual((ok["status"], ok["effects_pending"]), ("applied", []))
        self.assertEqual(w["inventory"], [])
        self.assertEqual(w["ground_items_by_location"]["inn"][0]["weapon_id"], "dagger")


class NoFalseCompletionTests(unittest.TestCase):
    def test_the_kernel_does_not_mark_any_equipment_entry_complete(self):
        for entry in ("phb2024:equipment:weapon:club", "phb2024:equipment:armor:plate-armor"):
            status = capability_status(entry, {})["status"]
            self.assertNotEqual(status, "COMPLETE", entry)
        self.assertEqual(capability_status("phb2024:equipment:weapon:not-a-weapon", {})["status"], "UNKNOWN_ENTRY")


if __name__ == "__main__":
    unittest.main()
