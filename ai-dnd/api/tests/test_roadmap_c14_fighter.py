"""Fighter (C14) earned 1->5 and starting levels 1-5: literal source oracles, state, persistence, rollback.

Values only, read from the page renders (no book text): Fighter Features table PDF ordinal 91 (level 1-5: PB 2/2/2/2/3, Second Wind
2/2/2/3/3, Weapon Mastery 3/3/3/4/4), core traits and level 1-2 features PDF 90, Champion PDF 95. Effects are in
test_roadmap_c14_fighter_features. Synthetic faults are unit boundaries, not native campaign evidence.
"""
import copy
import unittest
from unittest.mock import patch

import character_progression as cp
import class_tables
import fighter_features
import game
import hit_dice
import xp
from api.persistence.campaign_models import CampaignCorruptError, CampaignValidationError
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from api.tests.test_roadmap_c06_barbarian import spec as barbarian_spec

STRENGTH_ASI = {"feat": "Ability Score Improvement", "increase": {"strength": 2}}
CHOICES = {"2": {}, "3": {"subclass_id": "champion"}, "4": {"asi": STRENGTH_ASI}, "5": {}}
THRESHOLDS = dict(xp.LEVEL_THRESHOLDS)
RESULTS = {2: ("Action Surge (one use)", "Tactical Mind"), 3: ("Fighter Subclass",), 4: ("Ability Score Improvement",),
           5: ("Extra Attack", "Tactical Shift")}


def spec(style="Defense"):
    request = barbarian_spec()
    request.update(character_class="Fighter", fighting_style=style, equipment_package="A")
    return request


def bundle(level):
    return {str(n): copy.deepcopy(CHOICES[str(n)]) for n in range(2, level + 1)}


def created(level=1, *, style="Defense", request=None):
    session = game.create_session(seed=52)
    cp.create_at_level(session, request or spec(style), level, bundle(level) if level > 1 else None)
    session.commit_location_change("tavern")
    session.ensure_campaign_clock()
    return session


def earn(session, level):
    """XP-earned numeric level; the class choices of that level stay unapplied."""
    gained = THRESHOLDS[level] - session.character["xp"]
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state, gained, f"quest:fighter-{level}")


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
        table = cp.table("Fighter")
        self.assertEqual([table["levels"][str(n)]["proficiency_bonus"] for n in range(1, 6)], [2, 2, 2, 2, 3])
        self.assertEqual([table["levels"][str(n)]["second_wind"] for n in range(1, 6)], [2, 2, 2, 3, 3])
        self.assertEqual([table["levels"][str(n)]["weapon_mastery"] for n in range(1, 6)], [3, 3, 3, 4, 4])
        self.assertEqual(table["levels"]["5"]["features"], ["Extra Attack", "Tactical Shift"])
        self.assertEqual(class_tables.table("Fighter"), table, "the data oracle keeps reading the one moved file")
        self.assertEqual(table["source"]["class_rules"]["core_traits"]["pdf_page"], 90)
        self.assertEqual(table["source"]["class_rules"]["champion"]["pdf_page"], 95)

    def test_supported_level_and_asi_path(self):
        self.assertEqual(cp._supported_level("Fighter"), 5)
        self.assertTrue(cp.for_class("Fighter").selected_asi)
        self.assertEqual(game.CLASS_HIT_DICE["Fighter"], 10)
        self.assertEqual(xp.FIXED_HP_BY_CLASS["Fighter"], 6)

    def test_persuasion_is_a_fighter_skill_option(self):
        from api.dnd_2024_rules import CLASS_DEFINITIONS
        self.assertEqual(sorted(CLASS_DEFINITIONS["Fighter"]["skill_options"]), sorted(
            ["Acrobatics", "Animal Handling", "Athletics", "History", "Insight", "Intimidation", "Persuasion", "Perception", "Survival"]))


class EarnedProgression(unittest.TestCase):
    def test_level_one_is_created_applied_and_with_the_full_pool(self):
        session = created()
        self.assertEqual((session.character["level"], session.character["progression_level"], session.character["xp"]), (1, 1, 0))
        self.assertEqual(session.character["fighting_style"], "Defense")
        self.assertEqual(fighter_features.projection(session)["second_wind"]["max_uses"], 2)

    def test_each_step_is_previewed_pure_and_lists_the_features(self):
        session = created()
        for target in range(2, 6):
            earn(session, target)
            before = session._capture_runtime_snapshot()
            preview = cp.preview_level_up(session, target)
            self.assertEqual((preview["status"], preview["class_name"], preview["from_level"], preview["to_level"]),
                             ("ready", "Fighter", target - 1, target))
            self.assertEqual(tuple(preview["features"]), RESULTS[target])
            self.assertIsNone(preview["capacity"])
            self.assertTrue(preview["hit_points"]["already_applied"])
            self.assertIn("Weapon Mastery", " ".join(preview["effects_pending"]))
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
        self.assertEqual(fighter_features.projection(session)["second_wind"]["max_uses"], 2, "the pool follows the applied level")
        self.assertEqual(hit_dice.total(session.character), 1)

    def test_hit_points_are_paid_once_by_xp_and_never_again_by_the_step(self):
        session = created()
        earn(session, 2)
        hp = session.character["max_hp"]
        step(self, session, 2)
        self.assertEqual(session.character["max_hp"], hp)

    def test_hit_points_are_paid_by_the_step_when_it_runs_ahead_of_xp(self):
        session = created()
        hp, gain = session.character["max_hp"], xp.hit_point_gain(session.character)
        step(self, session, 2)
        self.assertEqual(session.character["max_hp"], hp + gain)
        self.assertEqual(session.character["level"], 2)

    def test_a_step_applies_once(self):
        session = created()
        earn(session, 2)
        preview = cp.preview_level_up(session, 2)
        self.assertEqual(cp.apply_level_choices(session, preview, {})["status"], "applied")
        self.assertEqual(cp.apply_level_choices(session, preview, {})["reason"], "already_applied")
        self.assertEqual(session.character["progression_level"], 2)

    def test_steps_cannot_be_skipped(self):
        session = created()
        earn(session, 4)
        for target in (3, 4, 5):
            self.assertEqual(cp.preview_level_up(session, target)["status"], "blocked", target)

    def test_level_three_takes_exactly_one_supported_subclass(self):
        session = earned(self, 2)
        earn(session, 3)
        preview = cp.preview_level_up(session, 3)
        self.assertEqual(preview["subclass_options"], [{"id": "champion", "name": "Champion"}])
        for wrong in ({}, {"subclass_id": "battle-master"}, {"subclass_id": "berserker"}, {"subclass_id": 1},
                      {"subclass_id": "champion", "primal_knowledge_skill": "Nature"}):
            self.assertEqual(cp.apply_level_choices(session, preview, wrong)["status"], "rejected", wrong)
        self.assertNotIn("subclass_id", session.character)
        step(self, session, 3)
        self.assertEqual(session.character["subclass_id"], "champion")

    def test_level_four_reuses_the_shared_asi_family(self):
        session = earned(self, 3)
        earn(session, 4)
        preview = cp.preview_level_up(session, 4)
        self.assertIn(STRENGTH_ASI, preview["supported_asi_choices"])
        self.assertIn({"feat": "Ability Score Improvement", "increase": {"dexterity": 2}}, preview["supported_asi_choices"])
        strength = session.character["strength"]
        for wrong in ({}, {"asi": {"feat": "Tough", "increase": {"strength": 2}}}, {"asi": {**STRENGTH_ASI, "increase": {"dexterity": 3}}},
                      {"asi": {**STRENGTH_ASI, "increase": {"strength": 3}}}):
            self.assertEqual(cp.apply_level_choices(session, preview, wrong)["status"], "rejected", wrong)
        step(self, session, 4)
        self.assertEqual(session.character["strength"], strength + 2)
        self.assertEqual(session.character["asi_choices"], [{"class_level": 4, **STRENGTH_ASI}])

    def test_constitution_asi_pays_retroactive_hit_points_and_leaves_armor_class(self):
        """PDF 41: a Constitution modifier rise adds 1 Hit Point per level. Level 4 from CON 14: 16 pays 4, 15 keeps the modifier and pays 0."""
        for increase, gain in (({"constitution": 2}, 4), ({"constitution": 1, "strength": 1}, 0)):
            session = earned(self, 3)
            earn(session, 4)
            hp, ac = session.character["max_hp"], session.character["armor_class"]
            self.assertEqual(session.character["constitution"], 14)
            step(self, session, 4, {"asi": {"feat": "Ability Score Improvement", "increase": increase}})
            self.assertEqual(session.character["max_hp"], hp + gain, increase)
            self.assertEqual(session.character["armor_class"], ac, "the Fighter's armor formula has no CON term")

    def test_level_five_has_no_choice_and_raises_nothing_but_the_applied_level(self):
        session = earned(self, 4)
        earn(session, 5)
        before = copy.deepcopy(session.character)
        step(self, session, 5)
        changed = {key for key in set(before) | set(session.character) if before.get(key) != session.character.get(key)}
        self.assertEqual(changed, {"progression_level"})
        self.assertEqual(cp.attacks_per_attack_action(session.character), 2)

    def test_pool_growth_at_level_four_adds_a_use_without_a_refill(self):
        session = earned(self, 3)
        session.character["fighter_uses"] = {"second_wind_spent": 2, "action_surge_spent": 1}
        earn(session, 4)
        step(self, session, 4)
        view = fighter_features.projection(session)
        self.assertEqual((view["second_wind"]["uses_remaining"], view["second_wind"]["max_uses"]), (1, 3))
        self.assertEqual(view["action_surge"]["uses_remaining"], 0)

    def test_level_six_stays_closed(self):
        session = earned(self, 5)
        self.assertEqual(cp.preview_level_up(session, 6)["reason"], "progression_level_not_supported")


class Rollback(unittest.TestCase):
    def test_a_failed_level_three_leaves_nothing(self):
        session = earned(self, 2)
        earn(session, 3)
        preview = cp.preview_level_up(session, 3)
        before = session._capture_runtime_snapshot()
        real = cp.validate_saved

        def fail_after_mutation(player, world, **kwargs):
            if player.get("progression_level") == 3:
                raise ValueError("synthetic")
            return real(player, world, **kwargs)
        with patch.object(cp, "validate_saved", side_effect=fail_after_mutation):
            result = cp.apply_level_choices(session, preview, {"subclass_id": "champion"})
        self.assertEqual((result["status"], result["reason"]), ("rejected", "resulting_state_invalid"))
        self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_a_failed_level_four_and_five_leave_nothing(self):
        for level in (4, 5):
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
            self.assertEqual((level, result["status"]), (level, "rejected"))
            self.assertEqual(session._capture_runtime_snapshot(), before)


class SavedState(unittest.TestCase):
    def test_round_trip_keeps_style_uses_subclass_and_choices(self):
        for level in range(1, 6):
            session = created(level, style="Archery")
            if level >= 2:
                session.character["fighter_uses"] = {"second_wind_spent": 1, "action_surge_spent": 1}
            fresh, _ = roundtrip(session)
            for key in ("fighting_style", "progression_level", "fighter_uses", "subclass_id", "asi_choices", "level", "xp"):
                self.assertEqual(fresh.character.get(key), session.character.get(key), (level, key))

    def test_a_legacy_fighter_without_the_new_fields_loads_with_nothing_spent(self):
        session = created()
        session.character.pop("fighter_uses", None)
        session.character.pop("progression_level", None)
        fresh, _ = roundtrip(session)
        self.assertNotIn("fighter_uses", fresh.character)
        self.assertEqual(fighter_features.projection(fresh)["second_wind"]["uses_remaining"], 2)

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
        uses = "fighter_uses"
        cases = [
            (1, lambda p: p.update({"subclass_id": "champion"})),
            (2, lambda p: p.update({"subclass_id": "champion"})),
            (3, lambda p: p.pop("subclass_id")),
            (3, lambda p: p.update({"subclass_id": "battle-master"})),
            (3, lambda p: p.update({"subclass_id": "berserker"})),
            (2, lambda p: p.update({"metamagic": ["quickened_spell"]})),
            (1, lambda p: p.update({uses: {"second_wind_spent": 3, "action_surge_spent": 0}})),
            (4, lambda p: p.update({uses: {"second_wind_spent": 4, "action_surge_spent": 0}})),
            (1, lambda p: p.update({uses: {"second_wind_spent": 0, "action_surge_spent": 1}})),
            (2, lambda p: p.update({uses: {"second_wind_spent": 0, "action_surge_spent": 2}})),
            (2, lambda p: p.update({uses: {"second_wind_spent": True, "action_surge_spent": 0}})),
            (2, lambda p: p.update({uses: {"second_wind_spent": -1, "action_surge_spent": 0}})),
            (2, lambda p: p.update({uses: {"second_wind_spent": 0}})),
            (2, lambda p: p.update({uses: {"second_wind_spent": 0, "action_surge_spent": 0, "extra": 0}})),
            (2, lambda p: p.update({uses: []})),
            (2, lambda p: p.update({"fighting_style": "Made Up"})),
            (2, lambda p: p.update({"fighting_style": 7})),
            (4, lambda p: p.pop("asi_choices")),
            (5, lambda p: p.update({"progression_level": 6})),
        ]
        for index, (level, change) in enumerate(cases):
            with self.subTest(index=index, level=level):
                self.forged(level, change)

    def test_fighter_fields_are_refused_on_other_classes(self):
        for field, value in (("fighter_uses", {"second_wind_spent": 0, "action_surge_spent": 0}), ("fighting_style", "Defense")):
            player = {"class": "Barbarian", "level": 1, field: value}
            with self.subTest(field), self.assertRaises(ValueError):
                cp.validate_saved(player, {})

    def test_fighter_applied_rules_are_its_own(self):
        from class_progression.base import ClassProgression
        from class_progression.fighter import HANDLER
        self.assertIsNot(type(HANDLER).validate_applied, ClassProgression.validate_applied)
        with self.assertRaises(ValueError):
            HANDLER.validate_applied({"subclass_id": "champion"}, {}, 2)
        with self.assertRaises(ValueError):
            HANDLER.validate_applied({}, {}, 3)
        HANDLER.validate_applied({"subclass_id": "champion"}, {}, 3)

    def test_a_null_style_stays_legal_for_other_classes_and_legacy_fighters(self):
        cp.validate_saved({"class": "Barbarian", "level": 1, "fighting_style": None}, {})
        cp.validate_saved({"class": "Fighter", "level": 1, "fighting_style": None}, {})

    def test_a_legacy_protection_style_still_loads(self):
        session = created()
        session.character["fighting_style"] = "Protection"
        self.assertEqual(roundtrip(session)[0].character["fighting_style"], "Protection")

    def test_applied_rules_refuse_caster_and_rage_state(self):
        session = created(2)
        for key in ("spellcasting_v1", "sorcery_points_v1", "rage_v1"):
            with self.subTest(key), self.assertRaises(ValueError):
                cp.validate_saved(session.character, {**session.world_state, key: {}})


class StartingLevels(unittest.TestCase):
    def test_every_start_reaches_the_applied_level_through_the_same_steps(self):
        expected_hp = None
        for level in range(1, 6):
            session = created(level)
            self.assertEqual((session.character["level"], session.character["progression_level"], session.character["xp"]),
                             (level, level, THRESHOLDS[level]))
            self.assertEqual(session.character["current_hp"], session.character["max_hp"])
            self.assertEqual(session.character.get("subclass_id"), "champion" if level >= 3 else None)
            if expected_hp is not None:
                self.assertGreater(session.character["max_hp"], expected_hp)
            expected_hp = session.character["max_hp"]

    def test_start_bundles_are_exact_and_leave_nothing_on_refusal(self):
        bad = [(2, {}), (2, {"2": {"x": 1}}), (3, {"2": {}}), (3, {"2": {}, "3": {}}), (3, {"2": {}, "3": {"subclass_id": "berserker"}}),
               (4, {"2": {}, "3": {"subclass_id": "champion"}}), (5, bundle(4)), (5, {**bundle(5), "5": {"x": 1}}),
               (4, {**bundle(4), "4": {"asi": {"feat": "Ability Score Improvement", "increase": {"dexterity": 3}}}}), (6, bundle(5))]
        for level, choices in bad:
            with self.subTest(level=level, choices=choices):
                session = game.create_session(seed=52)
                before = session._capture_runtime_snapshot()
                with self.assertRaises(ValueError):
                    cp.create_at_level(session, spec(), level, choices)
                self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_a_start_keeps_a_fighter_style_choice(self):
        with self.assertRaises(Exception):
            cp.create_at_level(game.create_session(seed=52), spec(None), 2, bundle(2))
        self.assertEqual(created(3, style="Archery").character["fighting_style"], "Archery")


if __name__ == "__main__":
    unittest.main()
