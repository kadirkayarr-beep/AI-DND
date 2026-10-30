"""C09: spells dispatch through one boundary that keeps the existing bounded resolvers' results and never fakes the rest.

`spell_registry.cast_spell` routes to `spell_scope.cast` (the owner of target, mitigation, slot, receipt behavior). Same inputs give
the same owner result; a cantrip reports no slot while a level-1 spell reports slot 1; a spell that is in the PHB catalog but
has no resolver is "unsupported" with a development reason and changes nothing; a rejection leaves the session unchanged.
The 391-spell catalog is C05's: nothing here marks any spell complete.
"""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import action_economy
import spell_registry
import spell_scope
from api.tests.test_spell_scope import caster
from capabilities import capability_status, manifest_rows

CASES = (("Fire Bolt", "Sorcerer", 12), ("Magic Missile", "Sorcerer", 12), ("Sacred Flame", "Cleric", 1))


def run_owner(cls, spell, d20, via_registry):
    s, enemy = caster(cls=cls)
    with patch("game.roll_d20", return_value=d20), patch.object(s.rng, "randint", return_value=3):
        if via_registry:
            delta = spell_registry.cast_spell(spell, {"session": s}, None, {"target_id": enemy["id"]})
            return s, enemy, delta
        return s, enemy, spell_scope.cast(s, spell, enemy["id"])


class DispatchTests(unittest.TestCase):
    def test_spell_kernel_preserves_existing_resolvers(self):
        for spell, cls, d20 in CASES:
            with self.subTest(spell=spell):
                s1, e1, direct = run_owner(cls, spell, d20, False)
                s2, e2, delta = run_owner(cls, spell, d20, True)
                self.assertEqual(delta["status"], "applied")
                self.assertEqual(delta["result"], direct, "the owner's own result, unchanged")
                self.assertEqual(e2["current_hp"], e1["current_hp"])
                self.assertEqual(s2.world_state["spellcasting_v1"]["slots"], s1.world_state["spellcasting_v1"]["slots"])  # combat ids differ

    def test_cure_wounds_self_heal_goes_through_the_same_owner(self):
        s, _ = caster(cls="Bard")
        s.character["current_hp"] = 1
        with patch.object(s.rng, "randint", return_value=4):
            delta = spell_registry.cast_spell("Cure Wounds", {"session": s}, 1, {"target_id": "player"})
        self.assertEqual(delta["status"], "applied")
        self.assertGreater(delta["result"]["healing"], 0)
        self.assertEqual([c["kind"] for c in delta["changes"]], ["spell_slot", "healing"])

    def test_cantrip_has_no_slot_and_leveled_spell_reports_its_level(self):
        s, e = caster()
        with patch("game.roll_d20", return_value=12), patch.object(s.rng, "randint", return_value=3):
            cantrip = spell_registry.cast_spell("Fire Bolt", {"session": s}, None, {"target_id": e["id"]})
        self.assertIsNone(cantrip["slot_level"])
        self.assertNotIn("spell_slot", [c["kind"] for c in cantrip["changes"]])
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 2})
        s, e = caster()
        with patch.object(s.rng, "randint", return_value=3):
            leveled = spell_registry.cast_spell("Magic Missile", {"session": s}, 1, {"target_id": e["id"]})
        self.assertEqual(leveled["slot_level"], 1)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1})

    def test_unsupported_slot_level_is_rejected_and_spends_nothing(self):
        s, e = caster()
        before = copy.deepcopy(s.world_state)
        # Selected C06 now supports earned slots2/3; slot4 remains genuinely unsupported.
        delta = spell_registry.cast_spell("Magic Missile", {"session": s}, 4, {"target_id": e["id"]})
        self.assertEqual((delta["status"], delta["reason"]), ("rejected", "unsupported_spell_mode"))
        self.assertEqual(s.world_state, before)
        self.assertEqual(delta["changes"], [])

    def test_rejections_keep_the_session_unchanged(self):
        s, e = caster()
        before = copy.deepcopy(s.world_state)
        for choice, reason in (({}, "spell_target_required"), ({"target_id": "nobody"}, "invalid_spell_target"), (None, "spell_target_required")):
            delta = spell_registry.cast_spell("Fire Bolt", {"session": s}, None, choice)
            self.assertEqual((delta["status"], delta["reason"], delta["result"]), ("rejected", reason, None), choice)
            self.assertEqual(s.world_state, before, choice)
        self.assertEqual(spell_registry.cast_spell("Fire Bolt", {}, None, {})["reason"], "session_required")
        self.assertFalse(action_economy.ensure(s)["player"]["base_action_spent"])


class ReviewHardeningTests(unittest.TestCase):
    def test_a_player_who_cannot_act_gets_a_rejection_not_an_exception(self):
        s, e = caster()
        s.character["current_hp"] = 0
        before = copy.deepcopy(s.world_state)
        delta = spell_registry.cast_spell("Fire Bolt", {"session": s}, None, {"target_id": e["id"]})
        self.assertEqual((delta["status"], delta["result"], delta["changes"]), ("rejected", None, []))
        self.assertEqual(s.world_state, before)

    def test_invalid_saved_spell_state_is_a_rejection(self):
        s, e = caster()
        s.world_state["spellcasting_v1"]["version"] = 99
        delta = spell_registry.cast_spell("Fire Bolt", {"session": s}, None, {"target_id": e["id"]})
        self.assertEqual((delta["status"], delta["reason"]), ("rejected", "invalid_spell_state"))

    def test_a_miss_and_a_saved_throw_are_explicit_no_effect_receipts(self):
        s, e = caster()
        with patch("game.roll_d20", return_value=2), patch.object(s.rng, "randint", return_value=3):
            miss = spell_registry.cast_spell("Fire Bolt", {"session": s}, None, {"target_id": e["id"]})
        self.assertEqual(miss["changes"], [{"kind": "no_effect", "target_id": e["id"], "reason": "miss_or_save_succeeded"}])
        s, e = caster(cls="Cleric")
        with patch("game.roll_d20", return_value=20), patch.object(s.rng, "randint", return_value=3):
            saved = spell_registry.cast_spell("Sacred Flame", {"session": s}, None, {"target_id": e["id"]})
        self.assertEqual(saved["changes"][0]["kind"], "no_effect")
        self.assertEqual(e["current_hp"], 100)

    def test_cure_wounds_on_another_target_is_rejected_and_no_slot_reported_for_unsupported(self):
        s, e = caster(cls="Bard")
        delta = spell_registry.cast_spell("Cure Wounds", {"session": s}, None, {"target_id": e["id"]})
        self.assertEqual((delta["status"], delta["reason"], delta["slot_level"]), ("rejected", "unsupported_spell_mode", 1))
        self.assertIsNone(spell_registry.cast_spell("Fireball", {"session": s}, 3, {})["slot_level"])
        self.assertEqual(spell_registry.cast_spell("Fire Bolt", None, None, {})["reason"], "session_required")
        self.assertEqual(spell_registry.cast_spell("ateş oku", {"session": s}, None, {})["reason"], "unknown_spell",
                         "aliases stay in spell_scope.natural_command; the registry takes canonical ids")

    def test_name_collisions_use_the_spell_category(self):
        self.assertEqual(spell_registry.spell_state("Shield"), "catalog_only")  # also an equipment row
        self.assertEqual(spell_registry.spell_state("Longsword"), "unknown")  # equipment only


class HonestCoverageTests(unittest.TestCase):
    def test_a_catalog_spell_without_a_resolver_is_unsupported_not_success(self):
        spells = {r["name"] for r in manifest_rows() if r["category"] == "spell"}
        self.assertTrue({"Fire Bolt", "Magic Missile", "Sacred Flame", "Cure Wounds", "Fireball"} <= spells)
        s, e = caster()
        before = copy.deepcopy(s.world_state)
        delta = spell_registry.cast_spell("Fireball", {"session": s}, 3, {"target_id": e["id"]})
        self.assertEqual((delta["status"], delta["reason"], delta["result"], delta["changes"]),
                         ("unsupported", "spell_resolver_missing", None, []))
        self.assertEqual(s.world_state, before)
        unknown = spell_registry.cast_spell("Not A Spell", {"session": s}, None, {})
        self.assertEqual((unknown["status"], unknown["reason"]), ("unsupported", "unknown_spell"))
        self.assertEqual(spell_registry.cast_spell(None, {"session": s}, None, {})["reason"], "unknown_spell")

    def test_registry_lists_exactly_the_four_real_resolvers_and_completes_none(self):
        self.assertEqual(spell_registry.resolvers(), {"Fire Bolt": 0, "Magic Missile": 1, "Cure Wounds": 1, "Sacred Flame": 0})
        rows = [r for r in manifest_rows() if r["category"] == "spell"]
        states = [spell_registry.spell_state(r["name"]) for r in rows]
        self.assertEqual((states.count("resolver"), states.count("catalog_only"), len(rows)), (4, len(rows) - 4, 391))
        for row in rows:
            self.assertNotEqual(capability_status(row["id"], {})["status"], "COMPLETE", row["name"])


if __name__ == "__main__":
    unittest.main()
