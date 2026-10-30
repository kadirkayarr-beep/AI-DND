"""Monk (C15) earned 1->5 and starting levels 1-5: literal source oracles, state, persistence, rollback.

Values only, read from the page renders (no book text): core traits and Martial Arts PDF ordinal 100, Monk Features table PDF 101
(level 1-5: PB 2/2/2/2/3, Martial Arts 1d6 x4 then 1d8, Focus Points none/2/3/4/5, Unarmored Movement none then +10 ft), level 3-5
features PDF 102, Warrior of the Open Hand PDF 106. Effects are in test_roadmap_c15_monk_features. Synthetic faults are unit
boundaries, not native campaign evidence.
"""
import copy
import unittest
from unittest.mock import patch

import character_progression as cp
import class_tables
import game
import hit_dice
import monk_features
import xp
from api.persistence.campaign_models import CampaignCorruptError, CampaignValidationError
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from api.tests.test_roadmap_c06 import SPEC

STRENGTH_ASI = {"feat": "Ability Score Improvement", "increase": {"strength": 2}}
WISDOM_ASI = {"feat": "Ability Score Improvement", "increase": {"wisdom": 2}}
CHOICES = {"2": {}, "3": {"subclass_id": "open_hand"}, "4": {"asi": STRENGTH_ASI}, "5": {}}
THRESHOLDS = dict(xp.LEVEL_THRESHOLDS)
RESULTS = {2: ("Monk's Focus", "Unarmored Movement", "Uncanny Metabolism"), 3: ("Deflect Attacks", "Monk Subclass"),
           4: ("Ability Score Improvement", "Slow Fall"), 5: ("Extra Attack", "Stunning Strike")}
SCORES = {"strength": 12, "dexterity": 15, "constitution": 13, "intelligence": 8, "wisdom": 14, "charisma": 10}


def spec():
    request = copy.deepcopy(SPEC)
    request.update(character_class="Monk", cantrips=[], spells=[], ability_scores=dict(SCORES),
                   background_ability_bonuses={"dexterity": 2, "constitution": 1},
                   proficient_skills=["Acrobatics", "Insight", "Persuasion", "Sleight of Hand", "Stealth"])
    return request


def bundle(level):
    return {str(n): copy.deepcopy(CHOICES[str(n)]) for n in range(2, level + 1)}


def created(level=1, *, request=None, choices=None):
    session = game.create_session(seed=52)
    cp.create_at_level(session, request or spec(), level, choices or (bundle(level) if level > 1 else None))
    session.commit_location_change("tavern")
    session.ensure_campaign_clock()
    return session


def earn(session, level):
    gained = THRESHOLDS[level] - session.character["xp"]
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state, gained, f"quest:monk-{level}")


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
        table = cp.table("Monk")
        rows = [table["levels"][str(n)] for n in range(1, 6)]
        self.assertEqual([row["proficiency_bonus"] for row in rows], [2, 2, 2, 2, 3])
        self.assertEqual([row["martial_arts_die"] for row in rows], [6, 6, 6, 6, 8])
        self.assertEqual([row["focus_points"] for row in rows], [None, 2, 3, 4, 5])
        self.assertEqual([row["unarmored_movement_ft"] for row in rows], [None, 10, 10, 10, 10])
        self.assertEqual(rows[4]["features"], ["Extra Attack", "Stunning Strike"])
        self.assertEqual(class_tables.table("Monk"), table, "the data oracle keeps reading the one moved file")
        self.assertEqual(table["source"]["class_rules"]["open_hand"]["pdf_page"], 106)

    def test_supported_level_and_asi_path(self):
        self.assertEqual(cp._supported_level("Monk"), 5)
        self.assertTrue(cp.for_class("Monk").selected_asi)
        self.assertEqual(game.CLASS_HIT_DICE["Monk"], 8)
        self.assertEqual(xp.FIXED_HP_BY_CLASS["Monk"], 5)


class EarnedProgression(unittest.TestCase):
    def test_level_one_is_created_applied_with_no_focus(self):
        session = created()
        self.assertEqual((session.character["level"], session.character["progression_level"], session.character["xp"]), (1, 1, 0))
        view = monk_features.projection(session)
        self.assertEqual((view["martial_arts_die"], view["focus"]), (6, None))

    def test_each_step_is_previewed_pure_and_lists_the_features(self):
        session = created()
        for target in range(2, 6):
            earn(session, target)
            before = session._capture_runtime_snapshot()
            preview = cp.preview_level_up(session, target)
            self.assertEqual((preview["status"], preview["class_name"], preview["from_level"], preview["to_level"]),
                             ("ready", "Monk", target - 1, target))
            self.assertEqual(tuple(preview["features"]), RESULTS[target])
            self.assertIsNone(preview["capacity"])
            self.assertTrue(preview["hit_points"]["already_applied"])
            self.assertEqual(session._capture_runtime_snapshot(), before)
            step(self, session, target)
        self.assertEqual((session.character["level"], session.character["progression_level"]), (5, 5))

    def test_choices_required_per_step(self):
        session = created()
        wanted = {2: {}, 3: {"subclass_id": 1}, 4: {"asi": 1}, 5: {}}
        for target in range(2, 6):
            earn(session, target)
            self.assertEqual(cp.preview_level_up(session, target)["choices_required"], wanted[target])
            step(self, session, target)

    def test_xp_level_is_not_applied_progression(self):
        session = created()
        earn(session, 5)
        self.assertEqual((session.character["level"], session.character["progression_level"]), (5, 1))
        self.assertEqual(cp.attacks_per_attack_action(session.character), 1)
        self.assertEqual(cp.preview_level_up(session, 3)["status"], "blocked")
        view = monk_features.projection(session)
        self.assertEqual((view["martial_arts_die"], view["focus"], view["movement_bonus_ft"]), (6, None, 0),
                         "die, Focus and movement follow the applied level")
        self.assertEqual(hit_dice.total(session.character), 1)

    def test_hit_points_are_paid_once_by_xp_and_by_the_step_when_it_runs_ahead(self):
        session = created()
        earn(session, 2)
        hp = session.character["max_hp"]
        step(self, session, 2)
        self.assertEqual(session.character["max_hp"], hp)
        ahead = created()
        hp, gain = ahead.character["max_hp"], xp.hit_point_gain(ahead.character)
        step(self, ahead, 2)
        self.assertEqual(ahead.character["max_hp"], hp + gain)

    def test_a_step_applies_once_and_cannot_be_skipped(self):
        session = created()
        earn(session, 4)
        for target in (3, 4, 5):
            self.assertEqual(cp.preview_level_up(session, target)["status"], "blocked", target)
        preview = cp.preview_level_up(session, 2)
        self.assertEqual(cp.apply_level_choices(session, preview, {})["status"], "applied")
        self.assertEqual(cp.apply_level_choices(session, preview, {})["reason"], "already_applied")

    def test_level_three_takes_exactly_one_supported_subclass(self):
        session = earned(self, 2)
        earn(session, 3)
        preview = cp.preview_level_up(session, 3)
        self.assertEqual(preview["subclass_options"], [{"id": "open_hand", "name": "Warrior of the Open Hand"}])
        for wrong in ({}, {"subclass_id": "warrior-of-mercy"}, {"subclass_id": "champion"}, {"subclass_id": 1},
                      {"subclass_id": "open_hand", "primal_knowledge_skill": "Nature"}):
            self.assertEqual(cp.apply_level_choices(session, preview, wrong)["status"], "rejected", wrong)
        self.assertNotIn("subclass_id", session.character)
        step(self, session, 3)
        self.assertEqual(session.character["subclass_id"], "open_hand")

    def test_level_four_reuses_the_shared_asi_family(self):
        session = earned(self, 3)
        earn(session, 4)
        preview = cp.preview_level_up(session, 4)
        self.assertIn(STRENGTH_ASI, preview["supported_asi_choices"])
        self.assertIn({"feat": "Ability Score Improvement", "increase": {"dexterity": 2}}, preview["supported_asi_choices"])
        for wrong in ({}, {"asi": {"feat": "Tough", "increase": {"strength": 2}}}, {"asi": {**STRENGTH_ASI, "increase": {"dexterity": 3}}}):
            self.assertEqual(cp.apply_level_choices(session, preview, wrong)["status"], "rejected", wrong)
        strength, ac = session.character["strength"], session.character["armor_class"]
        step(self, session, 4)
        self.assertEqual((session.character["strength"], session.character["armor_class"]), (strength + 2, ac))
        self.assertEqual(session.character["asi_choices"], [{"class_level": 4, **STRENGTH_ASI}])

    def test_unarmored_defense_follows_a_wisdom_modifier_rise_through_the_shared_step(self):
        """PDF 100: base AC 10 + DEX + WIS. WIS 14 to 16 raises the modifier and AC by 1; 14 to 15 changes neither."""
        for increase, gain in (({"wisdom": 2}, 1), ({"wisdom": 1, "strength": 1}, 0), ({"constitution": 2}, 0)):
            session = earned(self, 3)
            earn(session, 4)
            ac = session.character["armor_class"]
            self.assertEqual(ac, 10 + 3 + 2)
            step(self, session, 4, {"asi": {"feat": "Ability Score Improvement", "increase": increase}})
            self.assertEqual(session.character["armor_class"], ac + gain, increase)

    def test_a_wisdom_rise_is_not_offered_over_an_armor_class_the_formula_does_not_explain(self):
        session = earned(self, 3)
        earn(session, 4)
        session.character["armor_class"] = 19
        offered = cp.preview_level_up(session, 4)["supported_asi_choices"]
        self.assertNotIn(WISDOM_ASI, offered)
        self.assertIn(STRENGTH_ASI, offered)

    def test_level_five_has_no_choice_and_raises_nothing_but_the_applied_level(self):
        session = earned(self, 4)
        earn(session, 5)
        before = copy.deepcopy(session.character)
        step(self, session, 5)
        changed = {key for key in set(before) | set(session.character) if before.get(key) != session.character.get(key)}
        self.assertEqual(changed, {"progression_level"})
        self.assertEqual(cp.attacks_per_attack_action(session.character), 2)

    def test_focus_growth_adds_points_without_a_refill(self):
        session = earned(self, 3)
        session.character["monk_state"] = {"focus_spent": 3, "metabolism_spent": True, "deflect": "reduce"}
        earn(session, 4)
        step(self, session, 4)
        view = monk_features.projection(session)
        self.assertEqual((view["focus"]["points_remaining"], view["focus"]["max_points"]), (1, 4))

    def test_level_six_stays_closed(self):
        session = earned(self, 5)
        self.assertEqual(cp.preview_level_up(session, 6)["reason"], "progression_level_not_supported")


class Rollback(unittest.TestCase):
    def test_a_failed_step_leaves_nothing(self):
        for level in (3, 4, 5):
            session = earned(self, level - 1)
            earn(session, level)
            preview = cp.preview_level_up(session, level)
            choices = copy.deepcopy(CHOICES[str(level)])
            before = session._capture_runtime_snapshot()
            real = cp.validate_saved

            def fail_after_mutation(player, world, **kwargs):
                if player.get("progression_level") == level:
                    raise ValueError("synthetic")
                return real(player, world, **kwargs)
            with patch.object(cp, "validate_saved", side_effect=fail_after_mutation):
                result = cp.apply_level_choices(session, preview, choices)
            self.assertEqual((level, result["status"], result["reason"]), (level, "rejected", "resulting_state_invalid"))
            self.assertEqual(session._capture_runtime_snapshot(), before)


class SavedState(unittest.TestCase):
    def test_round_trip_keeps_state_subclass_and_choices(self):
        for level in range(1, 6):
            session = created(level)
            if level >= 2:
                session.character["monk_state"] = {"focus_spent": 2, "metabolism_spent": True, "deflect": "off"}
            fresh, _ = roundtrip(session)
            for key in ("progression_level", "monk_state", "subclass_id", "asi_choices", "level", "xp"):
                self.assertEqual(fresh.character.get(key), session.character.get(key), (level, key))
            self.assertEqual(fresh.world_state.get("worn_armor_v1"), {"version": 1, "armor_id": None})

    def test_a_legacy_monk_without_the_new_fields_loads_and_plays_with_nothing_spent(self):
        session = created()
        session.character.pop("monk_state", None)
        session.character.pop("progression_level", None)
        session.world_state.pop("worn_armor_v1", None)
        fresh, _ = roundtrip(session)
        self.assertNotIn("monk_state", fresh.character)
        self.assertNotIn("worn_armor_v1", fresh.world_state, "reading never writes the proof back")
        self.assertEqual(monk_features.projection(fresh)["martial_arts_die"], 6)
        self.assertTrue(monk_features.projection(fresh)["martial_arts_ready"])

    def test_a_legacy_monk_still_holding_the_default_sword_it_never_owned_fights_unarmed(self):
        session = created()
        session.world_state["equipment"].update(main_hand="longsword")
        session.world_state.pop("worn_armor_v1")
        fresh, _ = roundtrip(session)
        self.assertTrue(monk_features.projection(fresh)["martial_arts_ready"])

    def test_a_forged_armor_proof_is_refused(self):
        session = created()
        payload = serialize_campaign_payload(session)
        payload["engine_save"]["world_state"]["worn_armor_v1"] = {"version": 1, "armor_id": "chain_mail"}
        with self.assertRaises((CampaignCorruptError, CampaignValidationError, ValueError)):
            restore_campaign_session(game.create_session(seed=19), payload)

    def forged(self, level, change):
        session = created(level)
        payload = serialize_campaign_payload(session)
        change(payload["engine_save"]["player"])
        fresh = game.create_session(seed=19)
        before = fresh._capture_runtime_snapshot()
        with self.assertRaises((CampaignCorruptError, CampaignValidationError, ValueError)):
            restore_campaign_session(fresh, payload)
        self.assertEqual(fresh._capture_runtime_snapshot(), before)

    def test_forged_saves_fail_closed(self):
        key = "monk_state"
        good = {"focus_spent": 0, "metabolism_spent": False, "deflect": "reduce"}
        cases = [
            (1, lambda p: p.update({"subclass_id": "open_hand"})),
            (2, lambda p: p.update({"subclass_id": "open_hand"})),
            (3, lambda p: p.pop("subclass_id")),
            (3, lambda p: p.update({"subclass_id": "warrior-of-mercy"})),
            (3, lambda p: p.update({"subclass_id": "champion"})),
            (2, lambda p: p.update({"metamagic": ["quickened_spell"]})),
            (1, lambda p: p.update({key: {**good, "focus_spent": 1}})),
            (2, lambda p: p.update({key: {**good, "focus_spent": 3}})),
            (5, lambda p: p.update({key: {**good, "focus_spent": 6}})),
            (2, lambda p: p.update({key: {**good, "focus_spent": True}})),
            (2, lambda p: p.update({key: {**good, "focus_spent": -1}})),
            (2, lambda p: p.update({key: {**good, "metabolism_spent": 1}})),
            (2, lambda p: p.update({key: {**good, "deflect": "always"}})),
            (2, lambda p: p.update({key: {"focus_spent": 0}})),
            (2, lambda p: p.update({key: {**good, "extra": 0}})),
            (2, lambda p: p.update({key: []})),
            (4, lambda p: p.pop("asi_choices")),
            (5, lambda p: p.update({"progression_level": 6})),
        ]
        for index, (level, change) in enumerate(cases):
            with self.subTest(index=index, level=level):
                self.forged(level, change)

    def test_a_forged_armor_class_after_a_wisdom_rise_is_refused(self):
        session = earned(self, 3)
        earn(session, 4)
        step(self, session, 4, {"asi": WISDOM_ASI})
        session.character["armor_class"] += 1
        with self.assertRaises(ValueError):
            cp.validate_saved(session.character, session.world_state)

    def test_monk_fields_are_refused_on_other_classes(self):
        with self.assertRaises(ValueError):
            cp.validate_saved({"class": "Barbarian", "level": 1, "monk_state": {"focus_spent": 0, "metabolism_spent": False, "deflect": "reduce"}}, {})

    def test_applied_rules_refuse_caster_and_rage_state(self):
        session = created(2)
        for key in ("spellcasting_v1", "sorcery_points_v1", "rage_v1"):
            with self.subTest(key), self.assertRaises(ValueError):
                cp.validate_saved(session.character, {**session.world_state, key: {}})

    def test_the_unarmored_proof_stays_closed_to_other_classes(self):
        import equipment_economy
        proof = {"worn_armor_v1": {"version": 1, "armor_id": None}}
        equipment_economy.validate_worn_armor(proof, {"class": "Monk"}, 4)
        with self.assertRaises(Exception):
            equipment_economy.validate_worn_armor(proof, {"class": "Fighter"}, 4)


class StartingLevels(unittest.TestCase):
    def test_every_start_reaches_the_applied_level_through_the_same_steps(self):
        expected_hp = None
        for level in range(1, 6):
            session = created(level)
            self.assertEqual((session.character["level"], session.character["progression_level"], session.character["xp"]),
                             (level, level, THRESHOLDS[level]))
            self.assertEqual(session.character["current_hp"], session.character["max_hp"])
            self.assertEqual(session.character.get("subclass_id"), "open_hand" if level >= 3 else None)
            self.assertEqual(session.character["armor_class"], 15)
            if expected_hp is not None:
                self.assertGreater(session.character["max_hp"], expected_hp)
            expected_hp = session.character["max_hp"]

    def test_the_starting_hands_hold_no_foreign_weapon(self):
        session = created()
        held = session.world_state["equipment"]
        self.assertEqual(held["off_hand"], None)
        self.assertTrue(monk_features.projection(session)["martial_arts_ready"], held)

    def test_start_bundles_are_exact_and_leave_nothing_on_refusal(self):
        bad = [(2, {}), (2, {"2": {"x": 1}}), (3, {"2": {}}), (3, {"2": {}, "3": {}}), (3, {"2": {}, "3": {"subclass_id": "champion"}}),
               (4, {"2": {}, "3": {"subclass_id": "open_hand"}}), (5, bundle(4)), (5, {**bundle(5), "5": {"x": 1}}),
               (4, {**bundle(4), "4": {"asi": {"feat": "Ability Score Improvement", "increase": {"dexterity": 3}}}}), (6, bundle(5))]
        for level, choices in bad:
            with self.subTest(level=level, choices=choices):
                session = game.create_session(seed=52)
                before = session._capture_runtime_snapshot()
                with self.assertRaises(ValueError):
                    cp.create_at_level(session, spec(), level, choices)
                self.assertEqual(session._capture_runtime_snapshot(), before)


if __name__ == "__main__":
    unittest.main()
