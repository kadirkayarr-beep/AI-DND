"""Rogue (C18) earned 1->5 and starting levels 1-5: literal source oracles, state, persistence, rollback.

Values only, read from the page renders (no book text): Rogue Features table PDF ordinal 129 (level 1-5: PB 2/2/2/2/3, Sneak Attack
1/1/2/2/3 d6), core traits and level 1 features PDF 128, Assassin PDF 133. Effects are in test_roadmap_c18_rogue_features.
Synthetic faults are unit boundaries, not native campaign evidence.
"""
import copy
import unittest
from unittest.mock import patch

import character_progression as cp
import class_tables
import game
import rogue_features as features
import xp
from api.dnd_2024_rules import get_character_creation_catalog, get_expertise_choice_count
from api.persistence.campaign_models import CampaignCorruptError, CampaignValidationError
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from api.tests.test_roadmap_c06_barbarian import spec as barbarian_spec

INTELLIGENCE_ASI = {"feat": "Ability Score Improvement", "increase": {"intelligence": 2}}
CHOICES = {"2": {}, "3": {"subclass_id": "assassin"}, "4": {"asi": INTELLIGENCE_ASI}, "5": {}}
THRESHOLDS = dict(xp.LEVEL_THRESHOLDS)
RESULTS = {2: ("Cunning Action",), 3: ("Rogue Subclass", "Steady Aim"), 4: ("Ability Score Improvement",),
           5: ("Cunning Strike", "Uncanny Dodge")}
EXPERTISE = ["Stealth", "Sleight of Hand"]
SKILLS = ["Athletics", "Perception", "Persuasion", "Sleight of Hand", "Stealth", "Acrobatics", "Deception"]


def spec():
    request = barbarian_spec()
    request.update(character_class="Rogue", equipment_package="A", proficient_skills=list(SKILLS), expertise_skills=list(EXPERTISE))
    request.pop("fighting_style", None)
    return request


def bundle(level):
    return {str(n): copy.deepcopy(CHOICES[str(n)]) for n in range(2, level + 1)}


def created(level=1, *, request=None):
    session = game.create_session(seed=52)
    cp.create_at_level(session, request or spec(), level, bundle(level) if level > 1 else None)
    session.commit_location_change("tavern")
    session.ensure_campaign_clock()
    return session


def earn(session, level):
    gained = THRESHOLDS[level] - session.character["xp"]
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state, gained, f"quest:rogue-{level}")


def step(test, session, level, choices=None):
    preview = cp.preview_level_up(session, level)
    test.assertEqual(preview["status"], "ready", preview)
    result = cp.apply_level_choices(session, preview, copy.deepcopy(CHOICES[str(level)]) if choices is None else choices)
    test.assertEqual(result["status"], "applied", result)
    return result


def earned(test, level):
    session = created()
    for target in range(2, level + 1):
        earn(session, target)
        step(test, session, target)
    return session


def roundtrip(session, seed=19):
    payload = serialize_campaign_payload(session)
    fresh = game.create_session(seed=seed)
    restore_campaign_session(fresh, payload)
    return fresh, payload


class SourceTable(unittest.TestCase):
    def test_table_moved_to_the_class_directory_with_the_literal_rows(self):
        table = cp.table("Rogue")
        self.assertEqual([table["levels"][str(n)]["proficiency_bonus"] for n in range(1, 6)], [2, 2, 2, 2, 3])
        self.assertEqual([table["levels"][str(n)]["sneak_attack_dice"] for n in range(1, 6)], [1, 1, 2, 2, 3])
        self.assertEqual({table["levels"][str(n)]["sneak_attack_die"] for n in range(1, 6)}, {6})
        self.assertEqual(table["levels"]["5"]["features"], ["Cunning Strike", "Uncanny Dodge"])
        self.assertEqual(class_tables.table("Rogue"), table, "the data oracle keeps reading the one moved file")
        self.assertEqual(table["source"]["class_rules"]["assassin"]["pdf_page"], 133)

    def test_core_traits(self):
        self.assertEqual(cp._supported_level("Rogue"), 5)
        self.assertTrue(cp.for_class("Rogue").selected_asi)
        self.assertEqual(game.CLASS_HIT_DICE["Rogue"], 8)

    def test_skill_list_is_the_ten_source_skills(self):
        ten = {"Acrobatics", "Athletics", "Deception", "Insight", "Intimidation", "Investigation", "Perception", "Persuasion",
               "Sleight of Hand", "Stealth"}
        self.assertEqual(set(get_character_creation_catalog()["classes"]["Rogue"]["skill_options"]), ten)
        self.assertEqual(set(game.CLASS_SKILL_OPTIONS["Rogue"]), ten)

    def test_weapon_grant_is_simple_and_martial_finesse_or_light(self):
        grant = created().character["weapon_proficiencies"]
        self.assertIn("simple", grant)
        self.assertNotIn("martial", grant)
        self.assertIn("rapier", grant)
        self.assertIn("scimitar", grant)
        self.assertIn("shortsword", grant)
        self.assertIn("hand_crossbow", grant)
        self.assertNotIn("longsword", grant)
        self.assertNotIn("longbow", grant)

    def test_thieves_tools_and_thieves_cant_at_creation(self):
        character = created().character
        self.assertIn("Thieves' Tools", character["proficient_tools"])
        self.assertIn("Thieves' Cant", character["languages"])
        self.assertEqual(sorted(character["expertise_skills"]), sorted(EXPERTISE))

    def test_expertise_count_stays_two_through_level_five(self):
        self.assertEqual([get_expertise_choice_count("Rogue", n) for n in range(1, 7)], [2, 2, 2, 2, 2, 4])


class EarnedProgression(unittest.TestCase):
    def test_level_one_is_created_applied(self):
        character = created().character
        self.assertEqual((character["level"], character["class"]), (1, "Rogue"))
        self.assertEqual(features.rogue_level(character), 1)

    def test_each_step_is_previewed_pure_and_lists_the_features(self):
        session = created()
        for level in range(2, 6):
            earn(session, level)
            before = copy.deepcopy((session.character, session.world_state))
            preview = cp.preview_level_up(session, level)
            self.assertEqual(preview["status"], "ready", preview)
            self.assertEqual(tuple(preview["features"]), RESULTS[level])
            self.assertEqual((session.character, session.world_state), before)
            step(self, session, level)

    def test_choices_required_per_step(self):
        session = created()
        wanted = {2: {}, 3: {"subclass_id": 1}, 4: {"asi": 1}, 5: {}}
        for level in range(2, 6):
            earn(session, level)
            self.assertEqual(cp.preview_level_up(session, level)["choices_required"], wanted[level])
            step(self, session, level)

    def test_xp_level_is_not_applied_progression(self):
        session = earned(self, 2)
        earn(session, 5)
        self.assertEqual(session.character["level"], 5)
        self.assertEqual(features.rogue_level(session.character), 2)
        self.assertEqual(features.sneak_dice(features.rogue_level(session.character)), 1)
        self.assertFalse(features.projection_of(session)["steady_aim"])
        self.assertIsNone(features.projection_of(session)["uncanny_dodge"])

    def test_hit_points_are_paid_once_by_xp_and_never_again_by_the_step(self):
        session = created()
        earn(session, 2)
        paid = session.character["max_hp"]
        step(self, session, 2)
        self.assertEqual(session.character["max_hp"], paid)

    def test_hit_points_are_paid_by_the_step_when_it_runs_ahead_of_xp(self):
        session = created()
        before = session.character["max_hp"]
        preview = cp.preview_level_up(session, 2)
        self.assertEqual(preview["status"], "ready", preview)
        self.assertEqual(preview["hit_points"]["gain"], 5 + session.character["constitution_mod"])
        step(self, session, 2)
        self.assertEqual(session.character["max_hp"], before + preview["hit_points"]["gain"])

    def test_a_step_applies_once_and_steps_cannot_be_skipped(self):
        session = earned(self, 2)
        self.assertEqual(cp.preview_level_up(session, 2)["status"], "blocked")
        earn(session, 4)
        self.assertEqual(cp.preview_level_up(session, 4)["status"], "blocked")

    def test_level_three_takes_exactly_the_assassin_and_grants_its_tools(self):
        session = earned(self, 2)
        earn(session, 3)
        preview = cp.preview_level_up(session, 3)
        self.assertEqual(preview["subclass_options"], [{"id": "assassin", "name": "Assassin"}])
        for bad in ({}, {"subclass_id": "thief"}, {"subclass_id": "champion"}, {"subclass_id": "assassin", "extra": 1}):
            self.assertEqual(cp.apply_level_choices(session, preview, bad)["status"], "rejected", bad)
        self.assertNotIn("subclass_id", session.character)
        result = step(self, session, 3)
        self.assertEqual(session.character["subclass_id"], "assassin")
        for kit in ("Disguise Kit", "Poisoner's Kit"):
            self.assertIn(kit, session.world_state["inventory"])
            self.assertIn(kit, session.character["proficient_tools"])
        self.assertIn({"kind": "subclass", "id": "assassin"}, result["changes"])

    def test_assassin_tools_are_not_duplicated_when_already_carried(self):
        session = earned(self, 2)
        session.world_state["inventory"].append("Poisoner's Kit")
        earn(session, 3)
        step(self, session, 3)
        self.assertEqual(session.world_state["inventory"].count("Poisoner's Kit"), 1)

    def test_level_four_reuses_the_shared_asi_family_without_dexterity(self):
        session = earned(self, 3)
        earn(session, 4)
        preview = cp.preview_level_up(session, 4)
        self.assertTrue(preview["supported_asi_choices"])
        self.assertFalse(any("dexterity" in option["increase"] for option in preview["supported_asi_choices"]))
        before = session.character["intelligence"]
        step(self, session, 4)
        self.assertEqual(session.character["intelligence"], before + 2)
        self.assertEqual(session.character["asi_choices"], [{"class_level": 4, **INTELLIGENCE_ASI}])

    def test_level_five_has_no_choice_and_raises_the_proficiency_bonus(self):
        session = earned(self, 4)
        earn(session, 5)
        before = session.character["max_hp"]
        step(self, session, 5)
        self.assertEqual(session.character["progression_level"], 5)
        self.assertEqual(session.character["proficiency_bonus"], 3)
        self.assertEqual(session.character["max_hp"], before)

    def test_level_six_stays_closed(self):
        session = earned(self, 5)
        self.assertEqual(cp.preview_level_up(session, 6)["reason"], "progression_level_not_supported")


class Starting(unittest.TestCase):
    def test_every_level_matches_the_earned_shape(self):
        for level in range(2, 6):
            with self.subTest(level):
                character = created(level).character
                self.assertEqual((character["level"], character["progression_level"]), (level, level))
                self.assertEqual(character.get("subclass_id"), "assassin" if level >= 3 else None)
                self.assertEqual(character["xp"], THRESHOLDS[level])

    def test_a_started_rogue_round_trips(self):
        fresh, _ = roundtrip(created(5))
        self.assertEqual(features.rogue_level(fresh.character), 5)

    def test_bundle_shape_is_exact(self):
        session = game.create_session(seed=1)
        for bad in (None, {"2": {}}, {"2": {}, "3": {}}, {"2": {"x": 1}, "3": {"subclass_id": "assassin"}}):
            with self.subTest(bad), self.assertRaises(ValueError):
                cp.create_at_level(session, spec(), 3, bad)

    def test_catalog_offers_all_levels(self):
        options = get_character_creation_catalog()["rogue_starting_creation"]
        self.assertEqual(options["supported_starting_levels"], [1, 2, 3, 4, 5])
        self.assertEqual(options["level_3"]["subclass_options"], [{"id": "assassin", "name": "Assassin"}])
        self.assertTrue(options["level_4"]["supported_asi_choices"])
        self.assertTrue(options["level_5"]["effects_supported"])

    def test_catalog_is_fail_closed_per_row(self):
        table = copy.deepcopy(cp.table("Rogue"))
        table["levels"]["4"]["sneak_attack_dice"] = 3
        with patch.object(cp, "table", return_value=table):
            options = cp.rogue_starting_creation_options()
        self.assertEqual(options["supported_starting_levels"], [1, 2, 3])
        table["levels"]["1"]["sneak_attack_dice"] = 2
        with patch.object(cp, "table", return_value=table):
            self.assertIsNone(cp.rogue_starting_creation_options())


class Rollback(unittest.TestCase):
    def test_a_failed_level_three_leaves_nothing(self):
        session = earned(self, 2)
        earn(session, 3)
        before = copy.deepcopy((session.character, session.world_state))
        preview = cp.preview_level_up(session, 3)
        original = cp.validate_saved

        def fail_after_mutation(player, world, **kwargs):
            if player.get("subclass_id"):
                raise ValueError("synthetic")
            return original(player, world, **kwargs)
        with patch.object(cp, "validate_saved", side_effect=fail_after_mutation):
            result = cp.apply_level_choices(session, preview, {"subclass_id": "assassin"})
        self.assertEqual(result["status"], "rejected")
        self.assertEqual((session.character, session.world_state), before)


class SavedState(unittest.TestCase):
    def test_round_trip_keeps_subclass_tools_and_the_uncanny_dodge_choice(self):
        session = earned(self, 5)
        session.character[features.UNCANNY_OFF] = True
        fresh, _ = roundtrip(session)
        self.assertEqual(fresh.character["subclass_id"], "assassin")
        self.assertIs(fresh.character[features.UNCANNY_OFF], True)
        self.assertIn("Poisoner's Kit", fresh.world_state["inventory"])

    def test_a_legacy_rogue_without_the_new_fields_loads_and_reads_its_weapon_grant(self):
        session = created()
        session.character.pop("weapon_proficiencies", None)
        session.character.pop("progression_level", None)
        fresh, _ = roundtrip(session)
        self.assertEqual(features.rogue_level(fresh.character), 1)
        self.assertNotIn("weapon_proficiencies", fresh.character)
        self.assertIn("rapier", cp.class_weapon_proficiencies(fresh.character))

    def forged(self, level, change):
        session = created(level)
        payload = serialize_campaign_payload(session)
        change(payload["engine_save"]["player"])
        fresh = game.create_session(seed=19)
        with self.assertRaises((CampaignCorruptError, CampaignValidationError, ValueError)):
            restore_campaign_session(fresh, payload)

    def test_forged_saves_fail_closed(self):
        cases = {
            "wrong subclass": (3, lambda p: p.update(subclass_id="thief")),
            "champion": (3, lambda p: p.update(subclass_id="champion")),
            "missing subclass": (3, lambda p: p.pop("subclass_id")),
            "subclass too early": (2, lambda p: p.update(subclass_id="assassin")),
            "uncanny dodge below five": (4, lambda p: p.update(uncanny_dodge_off=True)),
            "uncanny dodge not true": (5, lambda p: p.update(uncanny_dodge_off=False)),
            "fighter uses": (5, lambda p: p.update(fighter_uses={"second_wind_spent": 0, "action_surge_spent": 0})),
        }
        for name, (level, change) in cases.items():
            with self.subTest(name):
                self.forged(level, change)

    def test_rogue_fields_are_refused_on_other_classes(self):
        from api.tests.test_roadmap_c14_fighter import created as fighter
        session = fighter(5)
        payload = serialize_campaign_payload(session)
        payload["engine_save"]["player"]["uncanny_dodge_off"] = True
        with self.assertRaises((CampaignCorruptError, CampaignValidationError, ValueError)):
            restore_campaign_session(game.create_session(seed=19), payload)

    def test_recreation_does_not_inherit_the_uncanny_dodge_choice(self):
        session = created(5)
        session.character[features.UNCANNY_OFF] = True
        cp.create_at_level(session, spec(), 5, bundle(5))
        self.assertNotIn(features.UNCANNY_OFF, session.character)


if __name__ == "__main__":
    unittest.main()
