"""C04 (first slice): the weapon and armor tables of the PHB 2024 are the engine's source of truth.

`content/rules/phb2024/weapons_armor.json` holds values and pages read from the book (PDF 214 weapons, 218 armor; never book
text). Every weapon and armor of the book must exist in the engine with the same damage, properties, mastery, weight, cost and
armor class rule; the legacy Turkish names stay selectable. Not covered here (owners in HANDOFF): applying the Strength
requirement's speed penalty and the stealth disadvantage in play, weapon mastery effects (C04/C10+), armor training penalties
in combat, tools and adventuring gear, services, mounts.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import game
from api.dnd_2024_rules import (
    ARMOR_CLASS_RULES, ARMOR_NAME_ALIASES, CharacterCreationError, calculate_derived_stats, get_equipment_armor_and_shield,
    CLASS_DEFINITIONS,
)

ROOT = Path(__file__).resolve().parents[3]
ORACLE = json.loads((ROOT / "content" / "rules" / "phb2024" / "weapons_armor.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((ROOT / "content" / "manifest" / "phb2024.json").read_text(encoding="utf-8"))
SCORES = {"strength": 15, "dexterity": 16, "constitution": 14, "intelligence": 10, "wisdom": 12, "charisma": 8}  # Dex +3


def engine_damage(weapon):
    return f"{weapon['damage_dice']}d{weapon['damage_die']}" if weapon["damage_die"] else str(weapon["fixed_damage"])


class WeaponTableTests(unittest.TestCase):
    def test_the_oracle_has_the_38_weapons_of_the_manifest(self):
        rows = {r["name"] for r in MANIFEST["rows"] if r["category"] == "equipment" and r["subcategory"] == "weapon"}
        self.assertEqual(rows, set(ORACLE["weapons"]))
        self.assertEqual(len(ORACLE["weapons"]), 38)

    def test_every_book_weapon_exists_with_the_book_values(self):
        problems = []
        for name, book in ORACLE["weapons"].items():
            weapon = game.WEAPONS.get(name)
            if weapon is None:
                problems.append(f"{name}: missing")
                continue
            got = {
                "damage": engine_damage(weapon), "type": weapon["damage_type"], "category": weapon["category"], "kind": weapon["kind"],
                "properties": sorted(weapon["properties"]), "mastery": weapon["mastery"], "cost_cp": weapon["cost_gp"] * 100,
                "versatile": f"1d{weapon['versatile_damage_die']}" if weapon["versatile_damage_die"] else None,
                "ammo": weapon["ammunition_type"],
                "range": f"{weapon['normal_range']}/{weapon['long_range']}" if weapon["normal_range"] else None,
            }
            want = {
                "damage": book["damage"], "type": book["damage_type"], "category": book["category"], "kind": book["kind"],
                "properties": sorted(book["properties"]), "mastery": book["mastery"], "cost_cp": book["cost_cp"],
                "versatile": book["versatile_damage"], "ammo": (book["ammunition"] or {}).get("type"),
                "range": (book["ammunition"] or {}).get("range") or book["thrown_range"],
            }
            for key in want:
                if got[key] != want[key]:
                    problems.append(f"{name}.{key}: engine {got[key]!r} != book {want[key]!r}")
            if weapon.get("weight_lb") != book["weight_lb"]:  # Sling: the source table states no weight (None == None, not a verified 0)
                problems.append(f"{name}.weight: engine {weapon.get('weight_lb')!r} != book {book['weight_lb']!r}")
        self.assertEqual(problems, [])

    def test_source_gaps_are_explicit_not_defaulted(self):
        sling = ORACLE["weapons"]["Sling"]
        self.assertEqual((sling["weight_lb"], sling["weight_status"]), (None, "NOT_STATED_IN_SOURCE_TABLE"))
        self.assertIsNone(game.WEAPONS["Sling"].get("weight_lb"), "the engine does not invent a weight either")
        self.assertEqual(ORACLE["weapons"]["Lance"]["two_handed_condition"], "unless mounted")
        # engine effect: no mounted rules exist, so the Lance is always two-handed (restrictive, never lets it be one-handed on foot)
        self.assertIn("two-handed", game.WEAPONS["Lance"]["properties"])

    def test_every_mastery_is_a_book_mastery_and_legacy_names_stay(self):
        self.assertEqual({w["mastery"] for w in ORACLE["weapons"].values()}, set(ORACLE["mastery_properties"]))
        self.assertEqual(game.WEAPONS["Kılıç"]["weapon_id"], "longsword", "the legacy Turkish alias keeps resolving")
        self.assertEqual(set(game.WEAPONS) - set(ORACLE["weapons"]), {"Kılıç"})


class ArmorTableTests(unittest.TestCase):
    def test_the_oracle_has_the_12_armors_and_shield_of_the_manifest(self):
        rows = {r["name"] for r in MANIFEST["rows"] if r["category"] == "equipment" and r["subcategory"] == "armor"}
        self.assertEqual(rows, set(ORACLE["armor"]) | {"Shield"})
        self.assertEqual(len(ORACLE["armor"]), 12)
        self.assertEqual(ORACLE["shield"]["ac_bonus"], 2)

    def test_every_armor_has_its_book_rule(self):
        for name, book in ORACLE["armor"].items():
            rule = ARMOR_CLASS_RULES.get(name)
            self.assertIsNotNone(rule, f"{name}: no armor class rule")
            self.assertEqual(rule["base_ac"], book["base_ac"], name)
            mode = {"full": "full", "capped2": "capped", "none": "none"}[book["dexterity"]]
            self.assertEqual(rule["dexterity_mode"], mode, name)
            if mode == "capped":
                self.assertEqual(rule["max_dexterity_bonus"], 2, name)
            self.assertEqual(rule.get("category"), book["category"], name)
            self.assertEqual(rule.get("min_strength"), book["min_strength"], name)
            self.assertEqual(rule.get("stealth_disadvantage"), book["stealth_disadvantage"], name)

    def test_armor_class_follows_the_table_for_every_armor(self):
        # Armor weight/cost in the oracle are values-only (not compared to engine data: the engine has no armor inventory table yet)
        for dex_score, dex in ((16, 3), (12, 1), (8, -1)):
            for name, book in ORACLE["armor"].items():
                bonus = {"full": dex, "capped2": min(2, dex), "none": 0}[book["dexterity"]]
                stats = calculate_derived_stats("Fighter", "Human", {**SCORES, "dexterity": dex_score}, equipped_armor=name)
                self.assertEqual(stats["armor_class"], book["base_ac"] + bonus, f"{name} dex {dex_score}")

    def test_shield_adds_two_only_with_training(self):
        base = calculate_derived_stats("Fighter", "Human", SCORES, equipped_armor="Chain Mail")["armor_class"]
        shield = calculate_derived_stats("Fighter", "Human", SCORES, equipped_armor="Chain Mail", has_shield=True)["armor_class"]
        self.assertEqual(shield - base, ORACLE["shield"]["ac_bonus"])
        self.assertEqual(calculate_derived_stats("Wizard", "Human", SCORES, has_shield=True)["armor_class"],
                         calculate_derived_stats("Wizard", "Human", SCORES)["armor_class"], "no shield training, no benefit")

    def test_names_resolve_to_the_most_specific_armor_and_legacy_names_stay(self):
        cases = {"Studded Leather Armor": "Studded Leather Armor", "Leather Armor": "Leather Armor", "Half Plate Armor": "Half Plate Armor",
                 "Plate Armor": "Plate Armor", "Breastplate": "Breastplate", "Chain Shirt": "Chain Shirt", "Chain Mail": "Chain Mail",
                 "Zincir Zırh": "Chain Mail", "Pul Zırh": "Scale Mail", "Deri Zırh": "Leather Armor"}
        for label, expected in cases.items():
            self.assertEqual(get_equipment_armor_and_shield([f"1x {label}"])[0], expected, label)
        self.assertEqual(get_equipment_armor_and_shield(["Longsword", "Shield"]), (None, True))
        self.assertEqual(get_equipment_armor_and_shield(["Chain Mail", "Shield"]), ("Chain Mail", True))
        for pair in (["Chain Mail", "Leather Armor"], ["Plate Armor", "Padded Armor"], ["Zincir Zırh", "Deri Zırh"]):
            with self.assertRaises(CharacterCreationError, msg=pair):  # carried != worn: never silently pick one suit
                get_equipment_armor_and_shield(pair)
        self.assertEqual(get_equipment_armor_and_shield(["Zincir Zırh", "Chain Mail"])[0], "Chain Mail", "same suit under two labels")
        self.assertEqual(get_equipment_armor_and_shield(["Studded Leather Armor", "Shield"]), ("Studded Leather Armor", True))
        self.assertEqual(ARMOR_NAME_ALIASES["Zincir Zırh"], "Chain Mail")


class CreationPackagesAndKernelTests(unittest.TestCase):
    def test_every_shipped_starting_package_names_at_most_one_suit(self):
        for cls, definition in CLASS_DEFINITIONS.items():
            for package in definition.get("equipment_packages", []):
                armor, _shield = get_equipment_armor_and_shield(package["items"])  # must not raise
                self.assertTrue(armor is None or armor in ARMOR_CLASS_RULES, (cls, package["id"]))

    def test_book_weapons_and_armor_go_through_the_c08_kernel_with_the_owner_rules(self):
        import equipment_rules

        def world_with(name, weapon_id=None):
            item = {"item_id": "item_000001", "name": name}
            if weapon_id:
                item["weapon_id"] = weapon_id
            return {"location": "inn", "flags": {"turn_index": 0}, "inventory": [item], "equipment": {"main_hand": None, "off_hand": None},
                    "currency": {"player": 0}, "item_sequence": 1, "npcs": [], "ground_items_by_location": {"inn": []}}

        for name, book in ORACLE["weapons"].items():
            w = world_with(name, game.WEAPONS[name]["weapon_id"])
            delta = equipment_rules.resolve_item_use(w, "item_000001", {"use": "equip", "hand": "main_hand"})
            if "two-handed" in book["properties"]:
                # Dilim 2 Task 14: a two-handed weapon goes in the main hand and takes both hands; never the off hand alone.
                self.assertEqual((delta["status"], delta["reason"]), ("applied", None), name)
                self.assertEqual(w["equipment"], {"main_hand": "item_000001", "off_hand": None}, name)
                w = world_with(name, game.WEAPONS[name]["weapon_id"])
                off = equipment_rules.resolve_item_use(w, "item_000001", {"use": "equip", "hand": "off_hand"})
                self.assertEqual((off["status"], off["reason"]), ("rejected", "two_handed_owner_required"), name)
                self.assertEqual(w["equipment"], {"main_hand": None, "off_hand": None}, name)
            else:
                self.assertEqual(delta["status"], "applied", name)
                self.assertEqual(w["equipment"]["main_hand"], "item_000001", name)
        for name in list(ORACLE["armor"]) + ["Shield"]:
            w = world_with(name)
            moved = equipment_rules.inventory_transfer(w, "player", "ground", "item_000001")
            self.assertEqual((moved["status"], moved["reason"]), ("rejected", "armor_owner_required"), name)
            self.assertEqual(w["inventory"][0]["item_id"], "item_000001", name)
            worn = equipment_rules.resolve_item_use(w, "item_000001", {"use": "equip", "hand": "off_hand"})
            self.assertEqual(worn["status"], "rejected", name)


if __name__ == "__main__":
    unittest.main()
