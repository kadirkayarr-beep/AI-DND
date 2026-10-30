"""Paladin (C16) earned 1->5 and starting levels 1-5: literal source oracles, spell state, persistence, rollback.

Values only, read from the page renders (no book text): Paladin Features table PDF ordinal 109 (level 1-5: PB 2/2/2/2/3, Channel
Divinity -/-/2/2/2, Prepared Spells 2/3/4/5/6, slots {1:2}/{1:2}/{1:3}/{1:3}/{1:4,2:2}), core traits and Spellcasting PDF 108,
Oath of Devotion spells PDF 112. Effects are in test_roadmap_c16_paladin_features. Synthetic faults are unit boundaries, not campaign evidence.
"""
import copy
import unittest
from unittest.mock import patch

import character_progression as cp
import class_tables
import game
import paladin_features as features
import spell_scope
import xp
from api.dnd_2024_rules import SPELLS_CATALOG
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from api.tests.test_roadmap_c06_barbarian import spec as barbarian_spec

CHA_ASI = {"feat": "Ability Score Improvement", "increase": {"charisma": 2}}
CHOICES = {"2": {"prepared_spells": ["Bless"], "fighting_style": "Defense"},
           "3": {"prepared_spells": ["Heroism"], "subclass_id": "oath_of_devotion"},
           "4": {"prepared_spells": ["Divine Favor"], "asi": CHA_ASI},
           "5": {"prepared_spells": ["Lesser Restoration"]}}
THRESHOLDS = dict(xp.LEVEL_THRESHOLDS)


def spec():
    request = barbarian_spec()
    request.update(character_class="Paladin", proficient_skills=["Athletics", "Persuasion", "Perception", "Sleight of Hand", "Stealth"],
                   spells=["Cure Wounds", "Command"], equipment_package="A")
    return request


def bundle(level, **two):
    result = {str(n): copy.deepcopy(CHOICES[str(n)]) for n in range(2, level + 1)}
    if two and level >= 2:
        result["2"] = {"prepared_spells": ["Bless"], **two}
    return result


def created(level=1, *, request=None, **two):
    session = game.create_session(seed=52)
    cp.create_at_level(session, request or spec(), level, bundle(level, **two) if level > 1 else None)
    session.commit_location_change("tavern")
    session.ensure_campaign_clock()
    return session


def earn(session, level):
    gained = THRESHOLDS[level] - session.character["xp"]
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state, gained, f"quest:paladin-{level}")


def step(test, session, level, choices=None):
    preview = cp.preview_level_up(session, level)
    test.assertEqual(preview["status"], "ready", preview)
    result = cp.apply_level_choices(session, preview, copy.deepcopy(CHOICES[str(level)]) if choices is None else choices)
    test.assertEqual(result["status"], "applied", result)
    return result


def earned(test, level, choices=None):
    session = created()
    for target in range(2, level + 1):
        earn(session, target)
        step(test, session, target, (choices or {}).get(target))
    return session


def roundtrip(session, seed=19):
    payload = serialize_campaign_payload(session)
    fresh = game.create_session(seed=seed)
    restore_campaign_session(fresh, payload)
    return fresh, payload


def spells(session):
    return session.world_state["spellcasting_v1"]


class SourceTable(unittest.TestCase):
    def test_table_moved_to_the_class_directory_with_the_literal_rows(self):
        table = cp.table("Paladin")
        rows = [table["levels"][str(n)] for n in range(1, 6)]
        self.assertEqual([row["proficiency_bonus"] for row in rows], [2, 2, 2, 2, 3])
        self.assertEqual([row["channel_divinity"] for row in rows], [None, None, 2, 2, 2])
        self.assertEqual([row["prepared_spells"] for row in rows], [2, 3, 4, 5, 6])
        self.assertEqual([row["slots"] for row in rows], [{"1": 2}, {"1": 2}, {"1": 3}, {"1": 3}, {"1": 4, "2": 2}])
        self.assertEqual(rows[4]["features"], ["Extra Attack", "Faithful Steed"])
        self.assertEqual(class_tables.table("Paladin"), table, "the data oracle keeps reading the one moved file")
        self.assertEqual(table["source"]["class_rules"]["divine_smite"]["pdf_page"], 264)

    def test_supported_level_and_class_constants(self):
        self.assertEqual(cp._supported_level("Paladin"), 5)
        self.assertTrue(cp.for_class("Paladin").selected_asi)
        self.assertEqual(game.CLASS_HIT_DICE["Paladin"], 10)
        self.assertEqual(xp.FIXED_HP_BY_CLASS["Paladin"], 6)

    def test_the_prepared_lists_are_the_source_paladin_lists(self):
        catalog = SPELLS_CATALOG["Paladin"]
        self.assertEqual(sorted(s["id"] for s in catalog["spells_level_1"]), sorted([
            "Bless", "Command", "Compelled Duel", "Cure Wounds", "Detect Evil and Good", "Detect Magic", "Detect Poison and Disease",
            "Divine Favor", "Divine Smite", "Heroism", "Protection from Evil and Good", "Purify Food and Drink", "Searing Smite",
            "Shield of Faith", "Thunderous Smite", "Wrathful Smite"]))
        self.assertEqual(sorted(s["id"] for s in catalog["spells_level_2"]), sorted([
            "Aid", "Find Steed", "Gentle Repose", "Lesser Restoration", "Locate Object", "Magic Weapon", "Prayer of Healing",
            "Protection from Poison", "Shining Smite", "Warding Bond", "Zone of Truth"]))
        import spell_registry
        for spell in catalog["spells_level_1"] + catalog["spells_level_2"]:
            self.assertIn(spell_registry.spell_state(spell["id"]), {"resolver", "catalog_only"}, spell["id"])


class EarnedProgression(unittest.TestCase):
    def test_level_one_is_created_applied_with_table_resources(self):
        session = created()
        character = session.character
        self.assertEqual((character["level"], character["progression_level"], character["xp"]), (1, 1, 0))
        self.assertEqual(cp.capacity(character), {"cantrips": 0, "prepared_spells": 2, "slots": {"1": 2}})
        self.assertEqual(spells(session)["prepared"], ["Cure Wounds", "Command"])
        self.assertEqual(spells(session)["slots"], {"1": 2})

    def test_each_step_is_previewed_pure_and_lists_the_features(self):
        session = created()
        wanted = {2: {"prepared_spells": 1, "fighting_style": 1, "cantrips": 2}, 3: {"prepared_spells": 1, "subclass_id": 1},
                  4: {"prepared_spells": 1, "asi": 1}, 5: {"prepared_spells": 1}}
        for target in range(2, 6):
            earn(session, target)
            before = session._capture_runtime_snapshot()
            preview = cp.preview_level_up(session, target)
            self.assertEqual(session._capture_runtime_snapshot(), before)
            self.assertEqual(preview["choices_required"], wanted[target])
            self.assertEqual(preview["features"], cp.table("Paladin")["levels"][str(target)]["features"])
            step(self, session, target)
        self.assertEqual(session.character["progression_level"], 5)

    def test_slots_follow_the_table_and_keep_what_was_spent(self):
        session = earned(self, 2)
        spells(session)["slots"]["1"] = 0
        earn(session, 3)
        step(self, session, 3)
        self.assertEqual(spells(session)["slots"], {"1": 1}, "the table adds one slot and refills nothing")
        self.assertEqual(session.character["spell_slots_remaining"], {"1": 1})
        earn(session, 4)
        step(self, session, 4)
        earn(session, 5)
        step(self, session, 5)
        self.assertEqual(spells(session)["slots"], {"1": 2, "2": 2})

    def test_prepared_counts_reach_the_table_and_mirror_the_character(self):
        session = earned(self, 5)
        self.assertEqual(spells(session)["prepared"], ["Cure Wounds", "Command", "Bless", "Heroism", "Divine Favor", "Lesser Restoration"])
        self.assertEqual(session.character["spells"], spells(session)["prepared"])

    def test_hit_points_are_paid_once_by_xp_and_never_again_by_the_step(self):
        session = created()
        earn(session, 2)
        paid = session.character["max_hp"]
        step(self, session, 2)
        self.assertEqual(session.character["max_hp"], paid)

    def test_hit_points_are_paid_by_the_step_when_it_runs_ahead_of_xp(self):
        session = created()
        before = session.character["max_hp"]
        step(self, session, 2)
        self.assertEqual(session.character["max_hp"], before + xp.hit_point_gain(session.character))
        self.assertEqual(session.character["level"], 2)

    def test_xp_level_is_not_applied_progression(self):
        session = created()
        earn(session, 3)
        self.assertEqual((session.character["level"], session.character["progression_level"]), (3, 1))
        self.assertEqual(cp.capacity(session.character)["prepared_spells"], 2)
        self.assertEqual(cp.preview_level_up(session, 3)["reason"], "previous_level_choices_required")

    def test_a_step_applies_once(self):
        session = created()
        earn(session, 2)
        preview = cp.preview_level_up(session, 2)
        self.assertEqual(cp.apply_level_choices(session, preview, copy.deepcopy(CHOICES["2"]))["status"], "applied")
        self.assertEqual(cp.apply_level_choices(session, preview, copy.deepcopy(CHOICES["2"]))["reason"], "already_applied")

    def test_choice_refusals_change_nothing(self):
        session = created()
        earn(session, 2)
        preview = cp.preview_level_up(session, 2)
        bad = [({"prepared_spells": ["Bless"]}, "fighting_style_invalid"),
               ({"prepared_spells": ["Bless"], "fighting_style": "Protection"}, "fighting_style_invalid"),
               ({"prepared_spells": ["Bless"], "fighting_style": "Blessed Warrior"}, "blessed_warrior_cantrips_invalid"),
               ({"prepared_spells": ["Bless"], "fighting_style": "Blessed Warrior", "cantrips": ["Guidance"]}, "blessed_warrior_cantrips_invalid"),
               ({"prepared_spells": ["Bless"], "fighting_style": "Blessed Warrior", "cantrips": ["Guidance", "Fire Bolt"]}, "blessed_warrior_cantrips_invalid"),
               ({"prepared_spells": ["Bless"], "fighting_style": "Blessed Warrior", "cantrips": ["Guidance", "Guidance"]}, "blessed_warrior_cantrips_invalid"),
               ({"prepared_spells": ["Bless"], "fighting_style": "Defense", "cantrips": ["Guidance", "Sacred Flame"]}, "blessed_warrior_cantrips_invalid"),
               ({"prepared_spells": ["Cure Wounds"], "fighting_style": "Defense"}, "prepared_spells_invalid"),
               ({"prepared_spells": ["Aid"], "fighting_style": "Defense"}, "prepared_spells_invalid"),
               ({"prepared_spells": ["Bless", "Heroism"], "fighting_style": "Defense"}, "prepared_spells_count"),
               ({"prepared_spells": ["Fire Bolt"], "fighting_style": "Defense"}, "prepared_spells_invalid")]
        before = session._capture_runtime_snapshot()
        for choices, reason in bad:
            with self.subTest(choices):
                self.assertEqual(cp.apply_level_choices(session, preview, choices)["reason"], reason)
                self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_level_two_spells_open_only_with_level_two_slots(self):
        session = earned(self, 4)
        earn(session, 5)
        preview = cp.preview_level_up(session, 5)
        self.assertIn("Lesser Restoration", preview["prepared_spell_ids"])
        self.assertNotIn("Find Steed", preview["prepared_spell_ids"], "always prepared at level 5")
        self.assertNotIn("Aid", preview["prepared_spell_ids"], "always prepared for the Oath at level 5")
        self.assertEqual(cp.apply_level_choices(session, preview, {"prepared_spells": ["Aid"]})["reason"], "prepared_spells_invalid")

    def test_defense_adds_one_with_armor_and_nothing_else_does(self):
        session = created()
        before = session.character["armor_class"]
        step(self, session, 2)
        self.assertEqual(session.character["armor_class"], before + 1)
        other = created()
        before = other.character["armor_class"]
        step(self, other, 2, {"prepared_spells": ["Bless"], "fighting_style": "Dueling"})
        self.assertEqual(other.character["armor_class"], before)
        self.assertEqual(other.character["fighting_style"], "Dueling")

    def test_defense_without_armor_adds_nothing(self):
        session = created()
        session.character["equipment_choices"] = []
        before = session.character["armor_class"]
        step(self, session, 2)
        self.assertEqual(session.character["armor_class"], before)

    def test_blessed_warrior_learns_two_cleric_cantrips_with_charisma(self):
        session = created()
        step(self, session, 2, {"prepared_spells": ["Bless"], "fighting_style": "Blessed Warrior", "cantrips": ["Guidance", "Sacred Flame"]})
        self.assertEqual(spells(session)["cantrips"], ["Guidance", "Sacred Flame"])
        self.assertEqual(session.character["cantrips"], ["Guidance", "Sacred Flame"])
        self.assertEqual(cp.capacity(session.character)["cantrips"], 2)
        self.assertEqual(session.character["fighting_style"], "Blessed Warrior")
        spell_scope.validate(spells(session), session.character)

    def test_level_three_takes_exactly_the_supported_oath(self):
        session = earned(self, 2)
        earn(session, 3)
        preview = cp.preview_level_up(session, 3)
        self.assertEqual(preview["subclass_options"], [{"id": "oath_of_devotion", "name": "Oath of Devotion"}])
        self.assertEqual(cp.apply_level_choices(session, preview, {"prepared_spells": ["Heroism"], "subclass_id": "oath_of_glory"})["reason"],
                         "selected_paladin_subclass_required")
        step(self, session, 3)
        self.assertEqual(session.character["subclass_id"], "oath_of_devotion")

    def test_level_four_reuses_the_shared_asi_family(self):
        session = earned(self, 3)
        earn(session, 4)
        preview = cp.preview_level_up(session, 4)
        self.assertEqual(len(preview["supported_asi_choices"]), len(cp.supported_asi_choices(session.character)))
        dex = {"prepared_spells": ["Divine Favor"], "asi": {"feat": "Ability Score Improvement", "increase": {"dexterity": 2}}}
        self.assertEqual(cp.apply_level_choices(session, preview, dex)["reason"], "selected_asi_not_supported")
        cha = session.character["charisma"]
        step(self, session, 4)
        self.assertEqual(session.character["charisma"], cha + 2)
        self.assertEqual(session.character["charisma_mod"], (cha + 2 - 10) // 2)
        self.assertEqual(session.character["asi_choices"][0]["class_level"], 4)

    def test_constitution_asi_pays_retroactive_hit_points_and_leaves_armor_class(self):
        session = earned(self, 3)
        earn(session, 4)
        before = copy.deepcopy(session.character)
        step(self, session, 4, {"prepared_spells": ["Divine Favor"], "asi": {"feat": "Ability Score Improvement", "increase": {"constitution": 2}}})
        gained = ((before["constitution"] + 2 - 10) // 2 - (before["constitution"] - 10) // 2) * 4
        self.assertEqual(session.character["max_hp"], before["max_hp"] + gained)
        self.assertEqual(session.character["current_hp"], before["current_hp"], "a retroactive maximum never heals")
        self.assertEqual(session.character["armor_class"], before["armor_class"])

    def test_level_five_opens_extra_attack_only_when_applied(self):
        session = earned(self, 4)
        self.assertEqual(cp.attacks_per_attack_action(session.character), 1)
        earn(session, 5)
        self.assertEqual(cp.attacks_per_attack_action(session.character), 1, "XP alone grants nothing")
        step(self, session, 5)
        self.assertEqual(cp.attacks_per_attack_action(session.character), 2)
        session.character.pop("subclass_id")
        self.assertEqual(cp.attacks_per_attack_action(session.character), 1)

    def test_level_six_stays_closed(self):
        session = earned(self, 5)
        self.assertEqual(cp.preview_level_up(session, 6)["reason"], "progression_level_not_supported")

    def test_a_character_without_a_spell_state_is_blocked_not_granted_one(self):
        session = created()
        earn(session, 2)
        del session.world_state["spellcasting_v1"]
        self.assertEqual(cp.preview_level_up(session, 2)["reason"], "paladin_spell_state_required")


class Rollback(unittest.TestCase):
    def test_a_failed_step_leaves_nothing(self):
        for level in (2, 3, 4, 5):
            with self.subTest(level):
                session = earned(self, level - 1)
                earn(session, level)
                preview = cp.preview_level_up(session, level)
                before = session._capture_runtime_snapshot()
                with patch.object(cp, "validate_saved", side_effect=ValueError("forced")):
                    result = cp.for_class("Paladin").apply_level(session, preview, copy.deepcopy(CHOICES[str(level)]))
                self.assertEqual(result["reason"], "resulting_state_invalid")
                self.assertEqual(session._capture_runtime_snapshot(), before)


class SavedState(unittest.TestCase):
    def test_round_trip_keeps_choices_spells_and_uses(self):
        session = earned(self, 5)
        session.character[features.KEY] = {**features.fresh_uses(), "lay_on_hands_spent": 7, "channel_divinity_spent": 1, "free_smite_spent": 1}
        fresh, _ = roundtrip(session)
        for field in ("progression_level", "subclass_id", "fighting_style", features.KEY, "asi_choices", "spells"):
            self.assertEqual(fresh.character[field], session.character[field], field)
        self.assertEqual(fresh.world_state["spellcasting_v1"], spells(session))

    def test_a_legacy_paladin_without_the_new_fields_loads_and_can_advance(self):
        session = created()
        session.character.pop("progression_level")
        fresh, _ = roundtrip(session)
        self.assertNotIn(features.KEY, fresh.character)
        self.assertEqual(cp.applied_level(fresh.character), 1)
        self.assertEqual(features.projection(fresh)["lay_on_hands"]["pool_remaining"], 5)
        earn(fresh, 2)
        step(self, fresh, 2)
        self.assertEqual(fresh.character["progression_level"], 2)

    def test_a_legacy_paladin_with_a_numeric_level_keeps_applied_one(self):
        session = created()
        session.character.pop("progression_level")
        earn(session, 3)
        self.assertEqual(cp.applied_level(session.character), 1)
        self.assertEqual(cp.capacity(session.character)["slots"], {"1": 2})
        step(self, session, 2)
        step(self, session, 3)
        self.assertEqual(cp.capacity(session.character)["slots"], {"1": 3})

    def forged(self, level, mutate):
        session = earned(self, level)
        mutate(session)
        with self.assertRaises(ValueError):
            cp.validate_saved(session.character, session.world_state)

    def test_forged_saves_fail_closed(self):
        uses = features.fresh_uses
        cases = [
            (1, lambda s: s.character.update(fighting_style="Defense")),
            (2, lambda s: s.character.update(fighting_style=None)),
            (2, lambda s: s.character.update(fighting_style="Protection")),
            (2, lambda s: s.character.update(subclass_id="oath_of_devotion")),
            (3, lambda s: s.character.pop("subclass_id")),
            (3, lambda s: s.character.update(subclass_id="oath_of_glory")),
            (2, lambda s: spells(s)["prepared"].pop()),
            (2, lambda s: spells(s)["cantrips"].append("Guidance")),
            (2, lambda s: spells(s)["prepared"].append("Aid")),
            (2, lambda s: s.world_state.update(rage_v1={"version": 1})),
            (2, lambda s: s.world_state.pop("spellcasting_v1")),
            (1, lambda s: s.character.update({features.KEY: {**uses(), "lay_on_hands_spent": 6}})),
            (1, lambda s: s.character.update({features.KEY: {**uses(), "free_smite_spent": 1}})),
            (2, lambda s: s.character.update({features.KEY: {**uses(), "channel_divinity_spent": 1}})),
            (3, lambda s: s.character.update({features.KEY: {**uses(), "channel_divinity_spent": 3}})),
            (3, lambda s: s.character.update({features.KEY: {**uses(), "lay_on_hands_spent": True}})),
            (3, lambda s: s.character.update({features.KEY: {**uses(), "extra": 1}})),
            (2, lambda s: s.character.update({features.KEY: {**uses(), "divine_sense_until": 5}})),
            (2, lambda s: s.character.update({features.KEY: {**uses(), "sacred_weapon": {"until": 5, "weapon_id": "longsword"}}})),
            (3, lambda s: s.character.update({features.KEY: {**uses(), "sacred_weapon": {"until": 5}}})),
            (3, lambda s: s.character.update({features.KEY: {**uses(), "divine_sense_until": s.world_state["campaign_time"]["elapsed_seconds"] + 601}})),
        ]
        for index, (level, mutate) in enumerate(cases):
            with self.subTest(index):
                self.forged(level, mutate)

    def test_paladin_fields_are_refused_on_other_classes(self):
        from api.tests.test_roadmap_c14_fighter import created as fighter
        session = fighter()
        session.character[features.KEY] = features.fresh_uses()
        with self.assertRaises(ValueError):
            cp.validate_saved(session.character, session.world_state)


class StartingLevels(unittest.TestCase):
    def test_every_start_reaches_the_applied_level_through_the_same_steps(self):
        for level in range(1, 6):
            with self.subTest(level):
                session = created(level)
                self.assertEqual(session.character["progression_level"], level)
                self.assertEqual(session.character["xp"], THRESHOLDS[level])
                row = cp.table("Paladin")["levels"][str(level)]
                self.assertEqual(len(spells(session)["prepared"]), row["prepared_spells"])
                self.assertEqual(spells(session)["slots"], row["slots"])
                cp.validate_saved(session.character, session.world_state)

    def test_a_start_with_blessed_warrior_round_trips(self):
        session = created(3, fighting_style="Blessed Warrior", cantrips=["Sacred Flame", "Guidance"])
        fresh, _ = roundtrip(session)
        self.assertEqual(fresh.world_state["spellcasting_v1"]["cantrips"], ["Sacred Flame", "Guidance"])

    def test_start_bundles_are_exact_and_leave_nothing_on_refusal(self):
        cases = [(2, None), (2, {}), (3, {"2": CHOICES["2"]}), (2, {"2": {"prepared_spells": ["Bless"]}}),
                 (2, {"2": {**CHOICES["2"], "extra": 1}}), (3, {"2": CHOICES["2"], "3": {"subclass_id": "oath_of_devotion"}})]
        for level, choices in cases:
            with self.subTest(choices):
                session = game.create_session(seed=3)
                before = copy.deepcopy(session.character)
                with self.assertRaises(ValueError):
                    cp.create_at_level(session, spec(), level, copy.deepcopy(choices))
                self.assertEqual(session.character, before)

    def test_starts_above_five_stay_closed(self):
        with self.assertRaises(ValueError):
            cp.create_at_level(game.create_session(seed=3), spec(), 6, bundle(5))


if __name__ == "__main__":
    unittest.main()
