"""C06 (first slice): Sorcerer level 1 -> 2 progression through the real create / preview / apply / save-load flow.

Source: PHB 2024 PDF 138-141 (Sorcerer Features table, Spellcasting, Font of Magic, Metamagic), read from the page scans; the
table is `content/rules/phb2024/classes/sorcerer.json`. This slice supports level 1 and 2 only: from level 3 a second slot level
exists and the save/spell validators accept slot level 1 only, so 3-5 are explicitly BLOCKED (preview says why), not faked.
`progression_level` is the level whose choices were applied; an XP-granted level above it is a PENDING level-up: the character
keeps its previous resources and stays able to cast (the 300 XP Magic Missile counter-example) until the choices are applied once.
Not covered here (owners in HANDOFF): other classes, levels 3-20, subclass, ASI/feat choice at 4, Font of Magic / Metamagic EFFECTS,
replacing cantrips/spells on level-up, multiclass (C07), UI.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import game
import spell_registry
import spell_scope
import xp
from api.character_creation import configure_character
from api.dnd_2024_rules import CLASS_DEFINITIONS, SPELLS_CATALOG
from api.persistence.campaign_models import CampaignCorruptError
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from api.tests.test_spell_scope import caster
import character_progression as cp

ROOT = Path(__file__).resolve().parents[3]
ORACLE = json.loads((ROOT / "content" / "rules" / "phb2024" / "classes" / "sorcerer.json").read_text(encoding="utf-8"))
SCORES = {"strength": 8, "dexterity": 14, "constitution": 13, "intelligence": 10, "wisdom": 12, "charisma": 15}
METAMAGIC = ["Careful Spell", "Distant Spell", "Empowered Spell", "Extended Spell", "Heightened Spell", "Quickened Spell",
             "Seeking Spell", "Subtle Spell", "Transmuted Spell", "Twinned Spell"]
L1_SPELLS = [s["id"] for s in SPELLS_CATALOG["Sorcerer"]["spells_level_1"]]
L1_CANTRIPS = [s["id"] for s in SPELLS_CATALOG["Sorcerer"]["cantrips"]]
SPEC = dict(
    name="Vael", race="Human", species="Human", character_class="Sorcerer", background="Criminal", alignment="Neutral Good",
    ability_score_method="standard_array", ability_scores=dict(SCORES), background_ability_bonuses={"dexterity": 2, "constitution": 1},
    proficient_skills=["Arcana", "Insight", "Persuasion", "Sleight of Hand", "Stealth"], equipment_package="A", background_equipment_option="A",
    languages=["Common", "Dwarvish", "Giant"], cantrips=["Fire Bolt", *[c for c in L1_CANTRIPS if c != "Fire Bolt"][:3]],
    spells=["Magic Missile", "Shield"],
)


def created_sorcerer(seed=42):
    session = game.create_session(seed=seed)
    configure_character(session, mode="custom", **SPEC)
    return session


def level_two_choices(session):
    prepared = set(session.world_state["spellcasting_v1"]["prepared"])
    extra = [s for s in L1_SPELLS if s not in prepared][:2]
    return {"prepared_spells": extra, "metamagic": ["Quickened Spell", "Twinned Spell"]}


class OracleTests(unittest.TestCase):
    def test_table_has_twenty_levels_with_the_book_columns(self):
        rows = ORACLE["levels"]
        self.assertEqual(sorted(int(k) for k in rows), list(range(1, 21)))
        for level in range(1, 21):
            row = rows[str(level)]
            self.assertEqual(row["proficiency_bonus"], (2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6)[level - 1], level)
            self.assertEqual(row["sorcery_points"], None if level == 1 else level, level)
        # rows read by eye from the page scan (PDF 139), independent of the parser
        self.assertEqual((rows["1"]["cantrips"], rows["1"]["prepared_spells"], rows["1"]["slots"]), (4, 2, {"1": 2}))
        self.assertEqual((rows["2"]["cantrips"], rows["2"]["prepared_spells"], rows["2"]["slots"]), (4, 4, {"1": 3}))
        self.assertEqual((rows["5"]["cantrips"], rows["5"]["prepared_spells"], rows["5"]["slots"]), (5, 9, {"1": 4, "2": 3, "3": 2}))
        self.assertEqual((rows["10"]["cantrips"], rows["10"]["prepared_spells"]), (6, 15))
        self.assertEqual(rows["20"]["slots"], {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 2, "7": 2, "8": 1, "9": 1})
        self.assertEqual(rows["20"]["prepared_spells"], 22)
        self.assertEqual(rows["2"]["features"], ["Font of Magic", "Metamagic"])
        self.assertEqual(rows["4"]["features"], ["Ability Score Improvement"])
        self.assertEqual(ORACLE["metamagic_options"], METAMAGIC)

    def test_the_engine_level_one_values_agree_with_the_book(self):
        definition = CLASS_DEFINITIONS["Sorcerer"]
        row = ORACLE["levels"]["1"]
        self.assertEqual((definition["cantrips_count"], definition["spells_count"], definition["spell_slots"]),
                         (row["cantrips"], row["prepared_spells"], row["slots"]))
        self.assertEqual(definition["hit_die"], 6)


class PreviewTests(unittest.TestCase):
    def test_preview_one_to_two_is_pure_and_lists_the_new_choices(self):
        session = created_sorcerer()
        before = copy.deepcopy((session.character, session.world_state))
        preview = cp.preview_level_up(session, 2)
        self.assertEqual(before, (session.character, session.world_state), "a preview changes nothing")
        self.assertEqual((preview["status"], preview["from_level"], preview["to_level"]), ("ready", 1, 2))
        self.assertEqual(preview["features"], ["Font of Magic", "Metamagic"])
        self.assertEqual(preview["choices_required"], {"prepared_spells": 2, "metamagic": 2})
        self.assertEqual(preview["capacity"], {"cantrips": 4, "prepared_spells": 4, "slots": {"1": 3}, "sorcery_points": 2})
        self.assertEqual(preview["hit_points"], {"gain": xp.hit_point_gain(session.character), "already_applied": False})
        self.assertIn("Font of Magic: Sorcery Points are not tracked yet", preview["effects_pending"])

    def test_levels_three_to_five_and_other_classes_are_blocked_explicitly(self):
        session = created_sorcerer()
        for target in (3, 4, 5):
            preview = cp.preview_level_up(session, target)
            self.assertEqual((preview["status"], preview["reason"]), ("blocked", "slot_levels_above_1_not_supported"), target)
        self.assertEqual(cp.preview_level_up(session, 1)["reason"], "target_not_above_applied_level")
        self.assertEqual(cp.preview_level_up(session, 21)["reason"], "invalid_target_level")
        other = game.create_session(seed=3)
        other.character["class"] = "Wizard"
        self.assertEqual(cp.preview_level_up(other, 2)["reason"], "class_table_not_available")


class ApplyTests(unittest.TestCase):
    def test_level_two_keeps_old_choices_and_resources_and_opens_the_new_ones(self):
        session = created_sorcerer()
        state = session.world_state["spellcasting_v1"]
        old_cantrips, old_prepared = list(state["cantrips"]), list(state["prepared"])
        state["slots"]["1"] = 1  # one slot already spent
        choices = level_two_choices(session)
        preview = cp.preview_level_up(session, 2)
        delta = cp.apply_level_choices(session, preview, choices)
        self.assertEqual((delta["status"], delta["reason"]), ("applied", None))
        state = session.world_state["spellcasting_v1"]
        self.assertEqual(state["cantrips"], old_cantrips)
        self.assertEqual(state["prepared"], old_prepared + choices["prepared_spells"])
        self.assertEqual(state["slots"], {"1": 2}, "max 2 -> 3: one slot was spent, the new slot is added, nothing is restored")
        self.assertEqual(session.character["level"], 2)
        self.assertEqual(session.character["progression_level"], 2)
        self.assertEqual(session.character["proficiency_bonus"], 2)
        self.assertEqual(session.character["metamagic"], choices["metamagic"])
        self.assertEqual(session.character["spells"], state["prepared"], "the legacy list stays in step")
        spell_scope.validate(state, session.character)

    def test_hit_points_are_gained_once_whether_xp_or_the_apply_raised_the_level(self):
        by_apply = created_sorcerer()
        hp = by_apply.character["max_hp"]
        cp.apply_level_choices(by_apply, cp.preview_level_up(by_apply, 2), level_two_choices(by_apply))
        gain = by_apply.character["max_hp"] - hp
        self.assertEqual(gain, xp.hit_point_gain(by_apply.character))
        by_xp = created_sorcerer()
        xp.apply_xp(by_xp.character, by_xp.world_state, 300, "quest:c06")
        self.assertEqual(by_xp.character["level"], 2)
        self.assertEqual(by_xp.character.get("progression_level", 1), 1, "XP raised the level; the choices are still pending")
        hp_after_xp = by_xp.character["max_hp"]
        preview = cp.preview_level_up(by_xp, 2)
        self.assertTrue(preview["hit_points"]["already_applied"])
        self.assertEqual(cp.apply_level_choices(by_xp, preview, level_two_choices(by_xp))["status"], "applied")
        self.assertEqual(by_xp.character["max_hp"], hp_after_xp, "no second hit point gain")
        self.assertEqual(by_xp.character["max_hp"], by_apply.character["max_hp"])

    def test_invalid_choices_are_rejected_and_change_nothing(self):
        session = created_sorcerer()
        good = level_two_choices(session)
        owned = session.world_state["spellcasting_v1"]["prepared"][0]
        bad = (
            ({**good, "prepared_spells": good["prepared_spells"][:1]}, "prepared_spells_count"),
            ({**good, "prepared_spells": [good["prepared_spells"][0], good["prepared_spells"][0]]}, "prepared_spells_invalid"),
            ({**good, "prepared_spells": [owned, good["prepared_spells"][1]]}, "prepared_spells_invalid"),
            ({**good, "prepared_spells": ["Fireball", good["prepared_spells"][1]]}, "prepared_spells_invalid"),
            ({**good, "metamagic": ["Quickened Spell"]}, "metamagic_count"),
            ({**good, "metamagic": ["Quickened Spell", "Quickened Spell"]}, "metamagic_invalid"),
            ({**good, "metamagic": ["Quickened Spell", "Fancy Spell"]}, "metamagic_invalid"),
            ({**good, "replace": {"cantrip": "Fire Bolt"}}, "unsupported_choice"),
            ({"prepared_spells": good["prepared_spells"]}, "metamagic_count"),
            (None, "choices_required"),
        )
        for choices, reason in bad:
            before = copy.deepcopy((session.character, session.world_state))
            delta = cp.apply_level_choices(session, cp.preview_level_up(session, 2), choices)
            self.assertEqual((delta["status"], delta["reason"]), ("rejected", reason), choices)
            self.assertEqual(before, (session.character, session.world_state), choices)

    def test_applying_the_same_preview_twice_is_refused(self):
        session = created_sorcerer()
        preview = cp.preview_level_up(session, 2)
        choices = level_two_choices(session)
        self.assertEqual(cp.apply_level_choices(session, preview, choices)["status"], "applied")
        after = copy.deepcopy((session.character, session.world_state))
        again = cp.apply_level_choices(session, preview, choices)
        self.assertEqual((again["status"], again["reason"]), ("rejected", "already_applied"))
        self.assertEqual(after, (session.character, session.world_state))

    def test_a_stale_or_tampered_preview_is_refused(self):
        session = created_sorcerer()
        preview = cp.preview_level_up(session, 2)
        preview["capacity"]["slots"] = {"1": 9}
        before = copy.deepcopy((session.character, session.world_state))
        delta = cp.apply_level_choices(session, preview, level_two_choices(session))
        self.assertEqual((delta["status"], delta["reason"]), ("rejected", "preview_not_current"))
        self.assertEqual(before, (session.character, session.world_state))
        blocked = cp.preview_level_up(session, 3)
        self.assertEqual(cp.apply_level_choices(session, blocked, {})["reason"], "preview_not_ready")


class CastabilityAndSaveLoadTests(unittest.TestCase):
    def test_magic_missile_stays_castable_after_xp_and_after_applying_level_two(self):
        # the 300 XP counter-example: XP makes the character level 2 and the old rule refused every level-1 spell
        s, e = caster()
        xp.apply_xp(s.character, s.world_state, 300, "quest:castable")
        self.assertEqual(s.character["level"], 2)
        with patch.object(s.rng, "randint", return_value=3):
            pending = spell_registry.cast_spell("Magic Missile", {"session": s}, 1, {"target_id": e["id"]})
        self.assertEqual(pending["status"], "applied", pending)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1}, "the old capacity still applies until the choices are applied")
        s, e = caster()
        choices = level_two_choices(s)
        self.assertEqual(cp.apply_level_choices(s, cp.preview_level_up(s, 2), choices)["status"], "applied")
        with patch.object(s.rng, "randint", return_value=3):
            leveled = spell_registry.cast_spell("Magic Missile", {"session": s}, 1, {"target_id": e["id"]})
        self.assertEqual((leveled["status"], leveled["slot_level"]), ("applied", 1))
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 2}, "3 slots at level 2, one spent")

    def test_non_sourced_classes_keep_the_old_level_one_only_rule(self):
        s, e = caster(cls="Bard")  # no progression table for this class
        s.character.update(level=2, proficiency_bonus=2)
        delta = spell_registry.cast_spell("Cure Wounds", {"session": s}, 1, {"target_id": "player"})
        self.assertEqual((delta["status"], delta["reason"]), ("rejected", "unsupported_spell_progression"))

    def test_applied_level_two_survives_save_and_load_and_pending_xp_level_loads_too(self):
        session = created_sorcerer()
        session.world_state["spellcasting_v1"]["slots"]["1"] = 1
        choices = level_two_choices(session)
        self.assertEqual(cp.apply_level_choices(session, cp.preview_level_up(session, 2), choices)["status"], "applied")
        payload = serialize_campaign_payload(session)
        self.assertEqual(payload["engine_save"]["player"]["progression_level"], 2)
        restored = game.create_session(seed=7)
        restore_campaign_session(restored, copy.deepcopy(payload))
        self.assertEqual((restored.character["level"], restored.character["progression_level"]), (2, 2))
        self.assertEqual(restored.character["metamagic"], choices["metamagic"])
        self.assertEqual(restored.world_state["spellcasting_v1"], session.world_state["spellcasting_v1"])
        self.assertEqual(cp.preview_level_up(restored, 2)["reason"], "target_not_above_applied_level")
        # a save that claims slots above the applied capacity is refused, not silently clamped
        tampered = copy.deepcopy(payload)
        tampered["engine_save"]["world_state"]["spellcasting_v1"]["slots"]["1"] = 4
        with self.assertRaises(CampaignCorruptError):
            restore_campaign_session(game.create_session(seed=8), tampered)
        # an older save (no progression_level) of a level-1 character still loads as applied level 1
        fresh = created_sorcerer(seed=11)
        old = serialize_campaign_payload(fresh)
        old["engine_save"]["player"].pop("progression_level", None)
        loaded = game.create_session(seed=12)
        restore_campaign_session(loaded, old)
        self.assertEqual(loaded.character.get("progression_level", 1), 1)
        # XP-granted level 2 without applied choices: the state saved and loaded is still pending, with the old capacity
        pending = created_sorcerer(seed=13)
        xp.apply_xp(pending.character, pending.world_state, 300, "quest:pending-save")
        copy_back = game.create_session(seed=14)
        restore_campaign_session(copy_back, serialize_campaign_payload(pending))
        self.assertEqual((copy_back.character["level"], copy_back.character.get("progression_level", 1)), (2, 1))
        self.assertEqual(cp.preview_level_up(copy_back, 2)["status"], "ready")

    def test_create_at_level_one_and_two_use_the_same_apply_path(self):
        session = game.create_session(seed=42)
        cp.create_at_level(session, SPEC, level=1)
        self.assertEqual((session.character["level"], session.character["progression_level"]), (1, 1))
        extra = [s for s in L1_SPELLS if s not in ("Magic Missile", "Shield")][:2]
        two = game.create_session(seed=42)
        cp.create_at_level(two, SPEC, level=2, level_choices={"2": {"prepared_spells": extra, "metamagic": ["Quickened Spell", "Twinned Spell"]}})
        self.assertEqual((two.character["level"], two.character["progression_level"]), (2, 2))
        self.assertEqual(two.world_state["spellcasting_v1"]["slots"], {"1": 3})
        missing = game.create_session(seed=42)
        with self.assertRaises(ValueError):
            cp.create_at_level(missing, SPEC, level=2)  # no choices: no half-made level-2 character
        self.assertEqual(missing.character.get("level", 1), 1)
        with self.assertRaises(ValueError):
            cp.create_at_level(game.create_session(seed=42), SPEC, level=3)  # blocked slice


class ReviewHardeningTests(unittest.TestCase):
    """Findings of the independent C06 review."""

    def _payload(self):
        return serialize_campaign_payload(created_sorcerer(seed=21))

    def test_a_save_cannot_claim_a_level_whose_choices_were_never_made(self):
        payload = self._payload()
        payload["engine_save"]["player"].update(level=2, progression_level=2)
        payload["engine_save"]["world_state"]["spellcasting_v1"]["slots"] = {"1": 3}
        with self.assertRaises(CampaignCorruptError):  # level 2 needs 4 prepared spells and 2 Metamagic options
            restore_campaign_session(game.create_session(seed=22), payload)

    def test_progression_level_above_the_supported_slice_is_refused_on_load(self):
        payload = self._payload()
        payload["engine_save"]["player"].update(level=3, progression_level=3)
        with self.assertRaises(CampaignCorruptError):
            restore_campaign_session(game.create_session(seed=23), payload)

    def test_the_version_five_advancement_check_accepts_applied_levels_only_with_progression(self):
        world = {"xp_awarded_event_ids": []}
        base = {"xp": 0, "species": "Human", "origin_feat": None}
        xp.validate_saved_advancement({**base, "level": 2, "progression_level": 2, "proficiency_bonus": 2}, world)
        xp.validate_saved_advancement({**base, "level": 5, "progression_level": 5, "proficiency_bonus": 3, "xp": 6500}, world)
        for bad in ({"level": 2, "proficiency_bonus": 2}, {"level": 2, "progression_level": 2, "proficiency_bonus": 3},
                    {"level": 1, "progression_level": 2, "proficiency_bonus": 2}):
            with self.assertRaises(ValueError, msg=bad):
                xp.validate_saved_advancement({**base, **bad}, world)

    def test_apply_replaces_only_the_spell_state_and_keeps_other_world_references(self):
        session = created_sorcerer()
        combat, npcs = session.world_state["combat"], session.world_state["npcs"]
        cp.apply_level_choices(session, cp.preview_level_up(session, 2), level_two_choices(session))
        self.assertIs(session.world_state["combat"], combat)
        self.assertIs(session.world_state["npcs"], npcs)

    def test_a_long_rest_after_level_two_restores_three_slots_and_it_casts_again(self):
        s, e = caster()
        cp.apply_level_choices(s, cp.preview_level_up(s, 2), level_two_choices(s))
        s.world_state["spellcasting_v1"]["slots"]["1"] = 0
        spell_scope.restore_slots(s)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 3})
        with patch.object(s.rng, "randint", return_value=3):
            self.assertEqual(spell_registry.cast_spell("Magic Missile", {"session": s}, 1, {"target_id": e["id"]})["status"], "applied")

    def test_loaded_legacy_fields_stay_in_step_with_the_spell_state(self):
        session = created_sorcerer()
        cp.apply_level_choices(session, cp.preview_level_up(session, 2), level_two_choices(session))
        restored = game.create_session(seed=31)
        restore_campaign_session(restored, serialize_campaign_payload(session))
        state = restored.world_state["spellcasting_v1"]
        self.assertEqual(restored.character["spells"], state["prepared"])
        self.assertEqual(restored.character["spell_slots_remaining"], state["slots"])


class XpGuardTests(unittest.TestCase):
    def test_xp_never_demotes_a_character_above_the_xp_cap_and_proficiency_follows_the_level(self):
        s = created_sorcerer()
        s.character.update(level=5, proficiency_bonus=3, xp=6500)
        result = xp.apply_xp(s.character, s.world_state, 10, "quest:no-demotion")
        self.assertEqual(s.character["level"], 5)
        self.assertEqual(s.character["proficiency_bonus"], 3)
        self.assertEqual(result["new_level"], 5)


if __name__ == "__main__":
    unittest.main()
