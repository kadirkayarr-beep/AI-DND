"""DEX in the selected ordinary ASI family, all six classes: exact recomputation, 20 cap, honest refusal.

Numeric oracles are literal values from the page image: Armor table PDF ordinal 218 (printed 219): Leather 11 + Dex,
Chain Mail 16, Shield +2, medium armor Dex modifier max 2, heavy armor no Dex. ASI pattern PDF 201. Unarmored Defense
Barbarian PDF 51, Monk PDF 100.
"""
import copy
import unittest
from unittest.mock import patch

import character_progression as cp
import game
from api.dnd_2024_rules import SPELLS_CATALOG
from api.persistence.campaign_models import CampaignCorruptError
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from api.schemas import LevelUpAsiChoice
from api.tests import (
    test_roadmap_c14_fighter as fighter,
    test_roadmap_c15_monk as monk,
    test_roadmap_c16_paladin as paladin,
    test_roadmap_c18_rogue as rogue,
)
from api.tests.test_roadmap_c06 import SPEC
from api.tests.test_roadmap_c06_barbarian import spec as barbarian_spec
from api.tests.test_roadmap_c06_level4_con import PICK
from api.tests.test_roadmap_c06_starting_xp import create as sorcerer_session
from pydantic import ValidationError


FAMILY = [
    {"strength": 2}, {"dexterity": 2}, {"constitution": 2}, {"intelligence": 2}, {"wisdom": 2}, {"charisma": 2},
    {"strength": 1, "dexterity": 1}, {"strength": 1, "constitution": 1}, {"strength": 1, "intelligence": 1},
    {"strength": 1, "wisdom": 1}, {"strength": 1, "charisma": 1},
    {"dexterity": 1, "constitution": 1}, {"dexterity": 1, "intelligence": 1}, {"dexterity": 1, "wisdom": 1},
    {"dexterity": 1, "charisma": 1},
    {"constitution": 1, "intelligence": 1}, {"constitution": 1, "wisdom": 1}, {"constitution": 1, "charisma": 1},
    {"intelligence": 1, "wisdom": 1}, {"intelligence": 1, "charisma": 1}, {"wisdom": 1, "charisma": 1},
]
BARBARIAN_THREE = {"2": {}, "3": {"subclass_id": "berserker", "primal_knowledge_skill": "Nature"}}
FIFTEEN_DEX_LEVEL = {"Sorcerer": 16, "Barbarian": 16, "Fighter": 16, "Paladin": 16, "Rogue": 16, "Monk": 17}
# class: (armor class at level 3, after +2 DEX, armor reading)
ARMOR_CLASS = {
    "Sorcerer": (13, 14, "10 + Dex"),
    "Barbarian": (15, 16, "10 + Dex + Con"),
    "Fighter": (19, 19, "Chain Mail 16, Shield 2, Defense 1: no Dex term"),
    "Paladin": (19, 19, "Chain Mail 16, Shield 2, Defense 1: no Dex term"),
    "Rogue": (14, 15, "Leather 11 + Dex"),
    "Monk": (15, 16, "10 + Dex + Wis"),
}
CLASSES = tuple(ARMOR_CLASS)


def level_three(class_name, **kwargs):
    if class_name == "Sorcerer":
        return sorcerer_session(3)
    if class_name == "Barbarian":
        session = game.create_session(seed=52)
        cp.create_at_level(session, barbarian_spec(), 3, copy.deepcopy(BARBARIAN_THREE))
        session.commit_location_change("tavern")
        session.ensure_campaign_clock()
        return session
    return {"Fighter": fighter, "Paladin": paladin, "Rogue": rogue, "Monk": monk}[class_name].created(3, **kwargs)


def asi(increase):
    return {"feat": "Ability Score Improvement", "increase": copy.deepcopy(increase)}


def choices(class_name, increase):
    if class_name == "Sorcerer":
        return {**copy.deepcopy(PICK), "asi": asi(increase)}
    if class_name == "Paladin":
        return {"prepared_spells": ["Divine Favor"], "asi": asi(increase)}
    return {"asi": asi(increase)}


def apply_four(test, session, increase):
    preview = cp.preview_level_up(session, 4)
    test.assertEqual(preview["status"], "ready", preview)
    result = cp.apply_level_choices(session, preview, choices(session.character["class"], increase))
    test.assertEqual(result["status"], "applied", result)
    return result


def offered(session):
    preview = cp.preview_level_up(session, 4)
    if preview["status"] != "ready":
        raise AssertionError(preview)
    return [option["increase"] for option in preview["supported_asi_choices"]]


def roundtrip(session):
    payload = serialize_campaign_payload(session)
    fresh = game.create_session(seed=9)
    restore_campaign_session(fresh, payload)
    return fresh


class Family(unittest.TestCase):
    def test_the_family_has_all_twenty_one_patterns(self):
        self.assertEqual([option["increase"] for option in cp.supported_asi_choices()], FAMILY)

    def test_every_class_catalog_offers_the_family(self):
        for options in (cp.sorcerer_starting_creation_options(), cp.barbarian_starting_creation_options(),
                        cp.fighter_starting_creation_options(), cp.paladin_starting_creation_options(),
                        cp.rogue_starting_creation_options(), cp.monk_starting_creation_options()):
            self.assertEqual([option["increase"] for option in options["level_4"]["supported_asi_choices"]], FAMILY)

    def test_the_request_contract_takes_dex_and_refuses_a_wrong_shape(self):
        for increase in FAMILY:
            self.assertEqual(LevelUpAsiChoice.model_validate(asi(increase)).model_dump()["increase"], increase)
        for bad in ({"dexterity": 1}, {"dexterity": 3}, {"dexterity": 2, "strength": 1}, {"dexterity": "2"},
                    {"dexterity": 1, "dex": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                LevelUpAsiChoice.model_validate(asi(bad))

    def test_no_class_disclosure_says_dex_is_unsupported(self):
        for class_name in CLASSES:
            for level in (4, 5):
                disclosure = cp.progression_disclosure(class_name, level)
                text = " ".join(disclosure["supported"] + disclosure["pending"])
                self.assertNotIn("non-DEX", text, class_name)
                self.assertNotIn("DEX Ability Score Improvement", text, class_name)


class EachClass(unittest.TestCase):
    def test_plus_two_recomputes_every_dex_reader(self):
        for class_name in CLASSES:
            with self.subTest(class_name=class_name):
                session = level_three(class_name)
                character = session.character
                before = copy.deepcopy(character)
                self.assertEqual(character["armor_class"], ARMOR_CLASS[class_name][0], ARMOR_CLASS[class_name][2])
                apply_four(self, session, {"dexterity": 2})
                self.assertEqual(character["dexterity"], before["dexterity"] + 2)
                self.assertEqual(character["dexterity_mod"], before["dexterity_mod"] + 1)
                self.assertEqual(character["modifiers"]["dexterity"], before["dexterity_mod"] + 1)
                self.assertEqual(character["final_ability_scores"]["dexterity"], before["dexterity"] + 2)
                self.assertEqual(character["saving_throw_mods"]["dexterity"], before["saving_throw_mods"]["dexterity"] + 1)
                self.assertEqual(character["initiative"], before["initiative"] + 1)
                self.assertEqual(character["armor_class"], ARMOR_CLASS[class_name][1], ARMOR_CLASS[class_name][2])
                self.assertEqual(character["asi_choices"], [{"class_level": 4, **asi({"dexterity": 2})}])
                for ability in ("strength", "constitution", "intelligence", "wisdom", "charisma"):
                    self.assertEqual(character[ability], before[ability])

    def test_plus_one_with_another_ability(self):
        for class_name in CLASSES:
            with self.subTest(class_name=class_name):
                session = level_three(class_name)
                before = copy.deepcopy(session.character)
                apply_four(self, session, {"dexterity": 1, "charisma": 1})
                character = session.character
                self.assertEqual((character["dexterity"], character["charisma"]), (before["dexterity"] + 1, before["charisma"] + 1))
                gained = character["dexterity_mod"] - before["dexterity_mod"]
                self.assertEqual(gained, 1 if class_name == "Monk" else 0, "16 to 17 keeps +3, 17 to 18 reaches +4")
                moved = ARMOR_CLASS[class_name][1] - ARMOR_CLASS[class_name][0]
                self.assertEqual(character["armor_class"], before["armor_class"] + (moved if gained else 0))
                self.assertEqual(character["saving_throw_mods"]["dexterity"], before["saving_throw_mods"]["dexterity"] + gained)

    def test_both_con_and_dex_move_the_barbarian_total_once_each(self):
        session = level_three("Barbarian")
        session.character["constitution"] = 15
        session.character["constitution_mod"] = 2
        session.character["final_ability_scores"]["constitution"] = 15
        session.character["base_ability_scores"]["constitution"] = 14
        session.character["background_ability_bonuses"] = {"dexterity": 2, "constitution": 1}
        session.character["dexterity"] = 17
        session.character["final_ability_scores"]["dexterity"] = 17
        session.character["base_ability_scores"]["dexterity"] = 15
        session.character["ability_score_method"] = "manual"
        before = session.character["armor_class"]
        apply_four(self, session, {"dexterity": 1, "constitution": 1})
        self.assertEqual(session.character["armor_class"], before + 2)

    def test_save_round_trip_twice_keeps_everything(self):
        for class_name in CLASSES:
            with self.subTest(class_name=class_name):
                session = level_three(class_name)
                apply_four(self, session, {"dexterity": 2})
                expected = {key: copy.deepcopy(session.character[key])
                            for key in ("dexterity", "dexterity_mod", "armor_class", "saving_throw_mods", "asi_choices", "armor_origin")}
                for _ in range(2):
                    session = roundtrip(session)
                    self.assertEqual({key: session.character[key] for key in expected}, expected)
                    cp.validate_saved(session.character, session.world_state)

    def test_the_level_after_it_still_applies_and_changes_no_armor_class(self):
        for class_name in CLASSES:
            with self.subTest(class_name=class_name):
                session = level_three(class_name)
                apply_four(self, session, {"dexterity": 2})
                session = roundtrip(session)
                armor_class = session.character["armor_class"]
                import xp
                gained = dict(xp.LEVEL_THRESHOLDS)[5] - session.character["xp"]
                session._receive_xp_award(xp.apply_xp, session.character, session.world_state, gained, "quest:dex-five")
                preview = cp.preview_level_up(session, 5)
                self.assertEqual(preview["status"], "ready", preview)
                level_five = {"Paladin": {"prepared_spells": ["Lesser Restoration"]}}.get(class_name, {})
                if class_name == "Sorcerer":
                    prepared = session.world_state["spellcasting_v1"]["prepared"]
                    level_five = {"prepared_spells": [spell["id"] for spell in SPELLS_CATALOG["Sorcerer"]["spells_level_1"]
                                                      if spell["id"] not in prepared][:2]}
                result = cp.apply_level_choices(session, preview, level_five)
                self.assertEqual(result["status"], "applied", result)
                self.assertEqual(session.character["armor_class"], armor_class)

    def test_starting_levels_four_and_five(self):
        bundles = {
            "Fighter": (fighter.spec(), fighter.bundle), "Monk": (monk.spec(), monk.bundle),
            "Paladin": (paladin.spec(), paladin.bundle), "Rogue": (rogue.spec(), rogue.bundle),
        }
        for class_name, (request, bundle) in bundles.items():
            for level in (4, 5):
                with self.subTest(class_name=class_name, level=level):
                    steps = bundle(level)
                    steps["4"]["asi"] = asi({"dexterity": 2})
                    session = game.create_session(seed=52)
                    cp.create_at_level(session, copy.deepcopy(request), level, steps)
                    self.assertEqual(session.character["armor_class"], ARMOR_CLASS[class_name][1])
                    self.assertEqual(session.character["dexterity"], FIFTEEN_DEX_LEVEL[class_name] + 2)
                    roundtrip(session)

    def test_starting_level_four_sorcerer_and_barbarian(self):
        session = game.create_session(seed=42)
        steps = {"2": sorcerer_two(), "3": sorcerer_three(), "4": {**copy.deepcopy(PICK), "asi": asi({"dexterity": 2})}}
        cp.create_at_level(session, copy.deepcopy(SPEC), 4, steps)
        self.assertEqual(session.character["armor_class"], 14)
        roundtrip(session)
        session = game.create_session(seed=52)
        cp.create_at_level(session, barbarian_spec(), 4, {**copy.deepcopy(BARBARIAN_THREE), "4": {"asi": asi({"dexterity": 2})}})
        self.assertEqual(session.character["armor_class"], 16)
        roundtrip(session)


def sorcerer_two():
    from api.tests.test_roadmap_c06_starting_xp import TWO
    return copy.deepcopy(TWO)


def sorcerer_three():
    from api.tests.test_roadmap_c06_starting_xp import choices as three
    return three()


class ArmorRules(unittest.TestCase):
    def _worn(self, armor, *, dexterity=16, shield=False):
        session = fighter.created(3, style="Archery", request={**fighter.spec("Archery"), "equipment_package": "C"})
        character = session.character
        total = cp.armor_class_total("Fighter", {"dexterity": (dexterity - 10) // 2, "constitution": 0, "wisdom": 0},
                                     armor, shield, "Archery")
        character.update(armor_origin={"armor": armor, "shield": shield}, armor_class=total)
        return session

    def test_light_armor_takes_the_full_modifier(self):
        session = self._worn("Studded Leather Armor")
        self.assertEqual(session.character["armor_class"], 15)
        apply_four(self, session, {"dexterity": 2})
        self.assertEqual(session.character["armor_class"], 16)

    def test_medium_armor_stops_at_two(self):
        session = self._worn("Breastplate")
        self.assertEqual(session.character["armor_class"], 16, "14 + Dex modifier (max 2)")
        apply_four(self, session, {"dexterity": 2})
        self.assertEqual(session.character["dexterity_mod"], 4)
        self.assertEqual(session.character["armor_class"], 16)

    def test_medium_armor_below_the_cap_still_rises(self):
        session = level_three("Fighter", style="Archery", request={**fighter.spec("Archery"), "equipment_package": "C",
                                                                  "ability_score_method": "manual",
                                                                  "ability_scores": {**fighter.spec()["ability_scores"], "dexterity": 8},
                                                                  "background_ability_bonuses": {"dexterity": 1, "constitution": 2}})
        character = session.character
        self.assertEqual(character["dexterity_mod"], -1)
        total = cp.armor_class_total("Fighter", character["modifiers"], "Hide Armor", False, "Archery")
        self.assertEqual(total, 11, "12 + Dex modifier")
        character.update(armor_origin={"armor": "Hide Armor", "shield": False}, armor_class=total)
        apply_four(self, session, {"dexterity": 2})
        self.assertEqual(session.character["armor_class"], 12)

    def test_heavy_armor_takes_nothing(self):
        session = self._worn("Plate Armor")
        self.assertEqual(session.character["armor_class"], 18)
        apply_four(self, session, {"dexterity": 2})
        self.assertEqual(session.character["armor_class"], 18)

    def test_a_shield_stays_flat(self):
        session = self._worn("Leather Armor", shield=True)
        self.assertEqual(session.character["armor_class"], 16)
        apply_four(self, session, {"dexterity": 2})
        self.assertEqual(session.character["armor_class"], 17)

    def test_every_armor_row_matches_the_page(self):
        rows = {"Padded Armor": 14, "Leather Armor": 14, "Studded Leather Armor": 15, "Hide Armor": 14, "Chain Shirt": 15,
                "Scale Mail": 16, "Breastplate": 16, "Half Plate Armor": 17, "Ring Mail": 14, "Chain Mail": 16,
                "Splint Armor": 17, "Plate Armor": 18}
        for armor, expected in rows.items():
            self.assertEqual(cp.armor_class_total("Fighter", {"dexterity": 3, "constitution": 0, "wisdom": 0}, armor, False, None), expected, armor)
        self.assertEqual(cp.armor_class_total("Fighter", {"dexterity": 3, "constitution": 0, "wisdom": 0}, "Leather Armor", True, "Defense"), 17)
        self.assertEqual(cp.armor_class_total("Sorcerer", {"dexterity": 3, "constitution": 0, "wisdom": 0}, None, True, None), 13, "no Shield training")

    def test_the_creation_calculator_is_the_same_owner(self):
        from api.dnd_2024_rules import calculate_derived_stats
        scores = {"strength": 10, "dexterity": 16, "constitution": 14, "intelligence": 10, "wisdom": 14, "charisma": 10}
        for class_name, armor, shield in (("Fighter", "Breastplate", True), ("Monk", None, True), ("Monk", None, False), ("Barbarian", None, True)):
            stats = calculate_derived_stats(class_name, "Human", scores, equipped_armor=armor, has_shield=shield)
            self.assertEqual(stats["armor_class"], cp.armor_class_total(class_name, stats["modifiers"], armor, shield, None))


class Honesty(unittest.TestCase):
    def test_cap_at_twenty(self):
        session = level_three("Monk", request={**monk.spec(), "ability_score_method": "manual",
                                               "ability_scores": {**monk.SCORES, "dexterity": 17}})
        self.assertEqual(session.character["dexterity"], 19)
        options = offered(session)
        self.assertNotIn({"dexterity": 2}, options)
        self.assertIn({"dexterity": 1, "strength": 1}, options)
        preview = cp.preview_level_up(session, 4)
        refused = cp.apply_level_choices(session, preview, choices("Monk", {"dexterity": 2}))
        self.assertEqual(refused["reason"], "asi_choice_not_eligible")
        apply_four(self, session, {"dexterity": 1, "strength": 1})
        self.assertEqual(session.character["dexterity"], 20)

    def test_an_unknown_ac_origin_refuses_only_a_dex_modifier_change(self):
        for class_name in ("Sorcerer", "Fighter", "Rogue", "Paladin"):
            with self.subTest(class_name=class_name):
                session = level_three(class_name)
                del session.character["armor_origin"]
                before = copy.deepcopy(session.character)
                options = offered(session)
                self.assertNotIn({"dexterity": 2}, options)
                self.assertIn({"dexterity": 1, "strength": 1}, options, "16 to 17 keeps the modifier, so AC cannot move")
                self.assertEqual(len(options), len(FAMILY) - 1)
                preview = cp.preview_level_up(session, 4)
                refused = cp.apply_level_choices(session, preview, choices(class_name, {"dexterity": 2}))
                self.assertEqual(refused["reason"], "asi_choice_not_eligible")
                self.assertEqual(session.character, before)

    def test_a_total_the_origin_does_not_explain_refuses_the_same_pattern(self):
        for class_name in CLASSES:
            with self.subTest(class_name=class_name):
                session = level_three(class_name)
                session.character["armor_class"] += 1
                self.assertNotIn({"dexterity": 2}, offered(session))

    def test_a_parity_neutral_increase_leaves_an_unverified_total_alone(self):
        session = level_three("Rogue")
        del session.character["armor_origin"]
        before = session.character["armor_class"]
        apply_four(self, session, {"dexterity": 1, "strength": 1})
        self.assertEqual(session.character["armor_class"], before)
        roundtrip(session)

    def test_a_barbarian_or_monk_save_without_the_origin_is_repaired_from_the_unarmored_proof(self):
        for class_name in ("Barbarian", "Monk"):
            with self.subTest(class_name=class_name):
                session = level_three(class_name)
                payload = serialize_campaign_payload(session)
                del payload["engine_save"]["player"]["armor_origin"]
                fresh = game.create_session(seed=9)
                restore_campaign_session(fresh, payload)
                self.assertEqual(fresh.character["armor_origin"], {"armor": None, "shield": False})
                self.assertIn({"dexterity": 2}, offered(fresh))

    def test_a_save_without_origin_or_proof_stays_unverified(self):
        session = level_three("Fighter")
        payload = serialize_campaign_payload(session)
        del payload["engine_save"]["player"]["armor_origin"]
        fresh = game.create_session(seed=9)
        restore_campaign_session(fresh, payload)
        self.assertNotIn("armor_origin", fresh.character)
        self.assertNotIn({"dexterity": 2}, offered(fresh))

    def test_a_forged_armor_class_behind_a_dex_record_is_refused_on_load(self):
        session = level_three("Rogue")
        apply_four(self, session, {"dexterity": 2})
        payload = serialize_campaign_payload(session)
        payload["engine_save"]["player"]["armor_class"] += 3
        with self.assertRaises(CampaignCorruptError):
            restore_campaign_session(game.create_session(seed=9), payload)

    def test_a_forged_armor_origin_is_refused_on_load(self):
        for forged in ({"armor": "Mithral Suit", "shield": False}, {"armor": None}, {"armor": None, "shield": 1},
                       {"armor": None, "shield": False, "extra": 1}, "Chain Mail", {"armor": 7, "shield": False}):
            with self.subTest(forged=forged):
                session = level_three("Rogue")
                payload = serialize_campaign_payload(session)
                payload["engine_save"]["player"]["armor_origin"] = forged
                with self.assertRaises(CampaignCorruptError):
                    restore_campaign_session(game.create_session(seed=9), payload)

    def test_a_loaded_character_never_inherits_the_previous_armor_origin(self):
        chain = level_three("Fighter")
        payload = serialize_campaign_payload(level_three("Fighter"))
        del payload["engine_save"]["player"]["armor_origin"]
        restore_campaign_session(chain, payload)
        self.assertNotIn("armor_origin", chain.character)

    def test_rollback_restores_everything(self):
        for class_name in CLASSES:
            with self.subTest(class_name=class_name):
                session = level_three(class_name)
                before = copy.deepcopy(session.character)
                world = copy.deepcopy(session.world_state)
                preview = cp.preview_level_up(session, 4)
                with patch.object(cp, "validate_saved", side_effect=ValueError("synthetic")):
                    result = cp.apply_level_choices(session, preview, choices(class_name, {"dexterity": 2}))
                self.assertEqual(result["status"], "rejected", result)
                self.assertEqual(session.character, before)
                self.assertEqual(session.world_state, world)

    def test_the_score_owner_itself_refuses_an_unverified_modifier_change(self):
        session = level_three("Rogue")
        del session.character["armor_origin"]
        before = copy.deepcopy(session.character)
        delta = {"changes": [{"ability": "dexterity", "from": 16, "to": 18}]}
        with self.assertRaises(ValueError):
            cp._apply_asi_score_delta(copy.deepcopy(before), delta)

    def test_the_proof_alone_does_not_repair_a_total_it_does_not_explain(self):
        session = level_three("Barbarian")
        session.character["armor_class"] += 2  # a carried Shield: the proof records only that no suit is worn
        self.assertIsNone(cp.repaired_armor_origin(session.character, session.world_state))
        session.character["armor_class"] -= 2
        self.assertEqual(cp.repaired_armor_origin(session.character, session.world_state), {"armor": None, "shield": False})
        self.assertIsNone(cp.repaired_armor_origin(session.character, {}))

    def test_a_paladin_who_reloaded_before_level_two_gets_defense_from_the_kept_origin(self):
        session = paladin.created(1)
        self.assertEqual(session.character["armor_class"], 18)
        session = roundtrip(session)
        self.assertNotIn("equipment_choices", session.character)
        paladin.earn(session, 2)
        result = cp.apply_level_choices(session, cp.preview_level_up(session, 2),
                                        {"prepared_spells": ["Bless"], "fighting_style": "Defense"})
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual(session.character["armor_class"], 19)

    def test_a_live_combat_record_carries_the_new_total(self):
        from api.tests.test_death_system import start_test_combat
        for class_name in ("Monk", "Sorcerer"):
            with self.subTest(class_name=class_name):
                session = level_three(class_name)
                start_test_combat(session)
                apply_four(self, session, {"dexterity": 2})
                record = next(r for r in session.world_state["combat"]["participant_records"] if r["id"] == "player")
                self.assertEqual(record["armor_class"], ARMOR_CLASS[class_name][1])

    def test_combat_records_follow_the_new_total(self):
        session = level_three("Rogue")
        combat = session.world_state.setdefault("combat", {})
        with patch.object(session, "_sync_combat_participant_records") as sync:
            combat["active"] = True
            with patch.object(cp, "validate_saved"), patch.object(session, "_validate_save_payload"):
                apply_four(self, session, {"dexterity": 2})
        sync.assert_called_once()
        session = level_three("Sorcerer")
        combat = session.world_state.setdefault("combat", {})
        with patch.object(session, "_sync_combat_participant_records") as sync:
            combat["active"] = True
            with patch.object(cp, "validate_saved"), patch.object(session, "_player_state_for_save"):
                apply_four(self, session, {"dexterity": 2})
        sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
