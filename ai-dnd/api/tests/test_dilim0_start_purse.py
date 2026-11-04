"""Dilim 0 (34): a new character's written coin becomes the purse at creation; the total never changes."""
from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

import bold_acts
import economic_actions
import game
from api.character_creation import configure_character
from api.dnd_2024_rules import CLASS_DEFINITIONS, get_character_creation_catalog
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from api.tests.test_character_creation_2024 import MockSession
from api.tests.test_roadmap_c06 import SPEC as SORCERER_SPEC
from api.tests.test_roadmap_c06_barbarian import spec as barbarian_spec
from api.tests.test_roadmap_c14_fighter import spec as fighter_spec
from api.tests.test_roadmap_c15_monk import spec as monk_spec
from api.tests.test_roadmap_c16_paladin import spec as paladin_spec
from api.tests.test_roadmap_c18_rogue import spec as rogue_spec

coin_label_gp = bold_acts.coin_label_gp
SPECS = {"Sorcerer": lambda: copy.deepcopy(SORCERER_SPEC), "Barbarian": barbarian_spec, "Fighter": fighter_spec,
         "Monk": monk_spec, "Paladin": paladin_spec, "Rogue": rogue_spec}
CLASS_COIN = {"Barbarian": {"A": 15, "B": 75}, "Bard": {"A": 18, "B": 18}, "Cleric": {"A": 15, "B": 15},
              "Druid": {"A": 9, "B": 9}, "Fighter": {"A": 10, "B": 10, "C": 10}, "Monk": {"A": 11, "B": 11},
              "Paladin": {"A": 9, "B": 9}, "Ranger": {"A": 10, "B": 10}, "Rogue": {"A": 8, "B": 8},
              "Sorcerer": {"A": 28, "B": 28}, "Warlock": {"A": 15, "B": 15}, "Wizard": {"A": 10, "B": 10}}
BACKGROUND_COIN = {"Acolyte": (8, ["8 GP"]), "Artisan": (32, ["32 GP"]), "Charlatan": (15, ["15 Altın"]),
                   "Criminal": (16, ["16 Altın"]), "Entertainer": (16, ["16 Altın"]), "Farmer": (25, ["25 Altın"]),
                   "Guard": (12, ["12 Altın"]), "Guide": (10, ["10 Altın"]), "Hermit": (15, ["15 Altın"]),
                   "Merchant": (30, ["30 Altın"]), "Noble": (25, ["25 Altın"]), "Sage": (10, ["10 Altın"]),
                   "Sailor": (20, ["20 GP"]), "Scribe": (23, ["23 GP"]), "Soldier": (14, ["14 Altın"]),
                   "Wayfarer": (16, ["16 Altın"])}


def names(world):
    return [item.get("name") if isinstance(item, dict) else item for item in world.get("inventory", [])]


def expected_cp(catalog, character_class, package_id, background, option):
    package = next(p for p in catalog["classes"][character_class]["equipment_packages"] if p["id"] == package_id)
    background_gp = (catalog["equipment_rules"]["background_option_b_gp"] if option == "B"
                     else catalog["backgrounds"][background]["coin_gp"])
    return (package["coin_gp"] + background_gp) * 100


def create(character_class, package_id, option, seed=42, convert=True):
    session = game.create_session(seed=seed)
    request = dict(SPECS[character_class](), equipment_package=package_id, background_equipment_option=option)
    if convert:
        configure_character(session, mode="custom", **request)
    else:  # the world as creation leaves it just before the one conversion (decision 35)
        with patch("api.character_creation._settle_new_character_coin", lambda session: None):
            configure_character(session, mode="custom", **request)
    return session, request


def random_created(seed, convert=True):
    session = MockSession(seed=seed)
    if convert:
        configure_character(session, mode="random")
    else:
        with patch("api.character_creation._settle_new_character_coin", lambda session: None):
            configure_character(session, mode="random")
    return session


def written_cp(world):
    """Purse plus the written coin in the pack, counted without settle_coin_labels (independent of the code under test)."""
    return world.get("currency", {}).get("player", 0) + sum(
        coin_label_gp(n) * 100 for n in names(world) if coin_label_gp(n) is not None)


class CoinLabel(unittest.TestCase):
    def test_coin_label_gp_reads_only_whole_coin_labels(self):
        self.assertEqual([coin_label_gp(x) for x in ("10 Altın", "15 GP", "50 Altın")], [10, 15, 50])
        for other in ("10 Parşömen", "2 Kese", "5 Hançer", "Altın Yüzük", "10 Altın ve bir kese", "", None, 7):
            self.assertIsNone(coin_label_gp(other), other)


class StartPurse(unittest.TestCase):
    def test_display_text_has_no_known_typo(self):
        text = json.dumps(get_character_creation_catalog(), ensure_ascii=False)
        self.assertNotIn("Zırsız", text)
        self.assertIn("Zırhsız", text)

    def assert_conserved(self, before, after, expected, label):
        """Decision 35: the total moves into the purse unchanged; non-coin items stay as they were; settling again is a no-op."""
        b, a = before.world_state, after.world_state
        self.assertEqual(written_cp(b), expected, label)                         # before = catalog (independent count)
        self.assertEqual(economic_actions.wallet_total_cp(b), expected, label)   # the screen's purse before = the same
        self.assertEqual(a.get("currency", {}).get("player"), expected, label)  # after: all of it in the purse
        self.assertEqual(economic_actions.wallet_total_cp(a), expected, label)
        self.assertEqual([n for n in names(a) if coin_label_gp(n) is not None], [], label)
        self.assertEqual(names(a), [n for n in names(b) if coin_label_gp(n) is None], label)  # order and count kept
        again = copy.deepcopy({"currency": a.get("currency"), "inventory": a.get("inventory")})
        bold_acts.settle_coin_labels(again)
        self.assertEqual(again, {"currency": a.get("currency"), "inventory": a.get("inventory")}, label)  # idempotent
        if isinstance(getattr(after, "inventory", None), list):
            self.assertEqual(list(after.inventory), list(a["inventory"]), label)

    def test_fighter_c_with_background_b_starts_with_6000_and_no_coin_text(self):
        before, _ = create("Fighter", "C", "B", convert=False)
        after, _ = create("Fighter", "C", "B")
        self.assert_conserved(before, after, 6000, "Fighter C + B")
        for item in ("Greatsword", "Ağır Tatar Yayı & 20 Ok", "Macera Çantası"):
            self.assertIn(item, names(after.world_state))

    def test_every_class_package_and_background_option_conserves_the_purse(self):
        catalog = get_character_creation_catalog()
        for character_class in SPECS:
            for package in CLASS_DEFINITIONS[character_class]["equipment_packages"]:
                for option in ("A", "B"):
                    with self.subTest(character_class=character_class, package=package["id"], option=option):
                        before, request = create(character_class, package["id"], option, convert=False)
                        after, _ = create(character_class, package["id"], option)
                        self.assert_conserved(
                            before, after, expected_cp(catalog, character_class, package["id"], request["background"], option),
                            f"{character_class} {package['id']} {option}")

    def test_every_class_in_random_creation_conserves_the_purse(self):
        catalog = get_character_creation_catalog()
        seen = set()
        for seed in range(500):
            after = random_created(seed)
            character_class = after.character["class"]
            if character_class in seen:
                continue
            seen.add(character_class)
            before = random_created(seed, convert=False)
            self.assertEqual((before.character["class"], before.character["background"]),
                             (character_class, after.character["background"]))  # same seed, same character
            package_id = CLASS_DEFINITIONS[character_class]["equipment_packages"][0]["id"]
            self.assert_conserved(
                before, after, expected_cp(catalog, character_class, package_id, after.character["background"], "A"),
                f"random {character_class}")
            if seen == set(game.CLASSES):
                break
        self.assertEqual(seen, set(game.CLASSES))

    def test_creation_is_deterministic(self):
        for character_class, package_id, option in (("Fighter", "C", "B"), ("Barbarian", "A", "A"), ("Rogue", "A", "A")):
            with self.subTest(character_class=character_class, package=package_id, option=option):
                first, _ = create(character_class, package_id, option, seed=11)
                second, _ = create(character_class, package_id, option, seed=11)
                self.assertEqual((first.world_state.get("currency"), first.world_state.get("inventory")),
                                 (second.world_state.get("currency"), second.world_state.get("inventory")))
        first, second = random_created(3), random_created(3)
        self.assertEqual((first.character["class"], first.world_state.get("currency"), first.world_state.get("inventory")),
                         (second.character["class"], second.world_state.get("currency"), second.world_state.get("inventory")))

    def test_a_resumed_old_save_keeps_its_label_until_money_moves(self):
        session, _ = create("Fighter", "C", "B")
        # An old save: the pack still holds the written coin and the purse lacks it (today's state before this slice).
        session.world_state["inventory"] = [*session.world_state["inventory"], "10 Altın"]
        session.world_state["currency"]["player"] = 5000
        payload = serialize_campaign_payload(session)
        restored = game.create_session(seed=7)
        restore_campaign_session(restored, payload)
        self.assertIn("10 Altın", names(restored.world_state))
        self.assertEqual(restored.world_state["currency"]["player"], 5000)
        self.assertEqual(economic_actions.wallet_total_cp(restored.world_state), 6000)
        bold_acts.settle_coin_labels(restored.world_state)  # what the first money action does (scenario 14 steps 2-3)
        self.assertNotIn("10 Altın", names(restored.world_state))
        self.assertEqual(restored.world_state["currency"]["player"], 6000)

    def test_catalog_names_the_coin_of_each_package_and_background(self):
        catalog = get_character_creation_catalog()
        self.assertEqual({c: {p["id"]: p["coin_gp"] for p in catalog["classes"][c]["equipment_packages"]}
                          for c in CLASS_COIN}, CLASS_COIN)
        self.assertEqual({b: catalog["backgrounds"][b]["coin_gp"] for b in BACKGROUND_COIN},
                         {b: gp for b, (gp, _) in BACKGROUND_COIN.items()})
        self.assertEqual(catalog["equipment_rules"]["background_option_b_gp"], 50)

    def test_catalog_lists_the_coin_items_apart(self):
        catalog = get_character_creation_catalog()
        fighter_c = next(p for p in catalog["classes"]["Fighter"]["equipment_packages"] if p["id"] == "C")
        self.assertEqual(fighter_c["coin_items"], ["10 Altın"])
        self.assertEqual({b: catalog["backgrounds"][b]["coin_items"] for b in BACKGROUND_COIN},
                         {b: items for b, (_, items) in BACKGROUND_COIN.items()})  # Acolyte's "10 Parşömen" stays a good
