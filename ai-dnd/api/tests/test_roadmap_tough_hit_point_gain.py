"""Forward-only Tough hit points per level (PHB 2024 Tough feat, PDF 201 / printed 202).

Every level reached after the feat is held adds 2 Hit Points. The feat owner is feat_rules.held_feats; Tough is counted once
however many records name it. Past levels, saved characters and 0 HP characters are never repaired or revived by this rule.
"""
import copy
import unittest

import xp


def wizard(**extra):
    return {"class": "Wizard", "level": 1, "constitution_mod": 0, "max_hp": 6, "current_hp": 6, **extra}


class ToughHitPointGainTests(unittest.TestCase):
    def test_character_without_tough_gets_only_the_class_gain(self):
        self.assertEqual(xp.hit_point_gain(wizard()), 4)

    def test_background_tough_keeps_its_two_extra_points(self):
        self.assertEqual(xp.hit_point_gain(wizard(origin_feat="Tough")), 6)

    def test_human_bonus_tough_in_origin_feats_adds_two(self):
        hero = wizard(species="Human", species_bonus_feat="Tough", origin_feats=["Savage Attacker", "Tough"])
        self.assertEqual(xp.hit_point_gain(hero), 6)

    def test_other_origin_feats_alone_add_nothing(self):
        self.assertEqual(xp.hit_point_gain(wizard(origin_feats=["Alert", "Savage Attacker"])), 4)

    def test_tough_named_by_several_records_is_counted_once(self):
        hero = wizard(origin_feat="Tough", origin_feats=["Tough", "Tough"], feats=["Tough"])
        self.assertEqual(xp.hit_point_gain(hero), 6)

    def test_tough_held_only_in_feats_adds_two(self):
        self.assertEqual(xp.hit_point_gain(wizard(feats=["Tough"])), 6)

    def test_bare_string_origin_feats_is_one_feat_and_odd_entries_are_ignored(self):
        self.assertEqual(xp.hit_point_gain(wizard(origin_feats="Tough")), 6)
        self.assertEqual(xp.hit_point_gain(wizard(feats=None, origin_feats=[None, 3, "Alert"])), 4)

    def test_hit_point_gain_does_not_change_the_character(self):
        hero = wizard(origin_feats=["Tough"])
        before = copy.deepcopy(hero)
        xp.hit_point_gain(hero)
        self.assertEqual(hero, before)

    def test_level_up_adds_tough_hit_points_going_forward_only(self):
        hero = wizard(origin_feats=["Tough"])
        xp._apply_numeric_level(hero, 3)
        self.assertEqual((hero["max_hp"], hero["current_hp"]), (6 + 6 + 6, 6 + 6 + 6))

    def test_level_up_never_revives_a_character_at_zero_hit_points(self):
        hero = wizard(origin_feats=["Tough"], current_hp=0)
        xp._apply_numeric_level(hero, 2)
        self.assertEqual((hero["max_hp"], hero["current_hp"]), (12, 0))


if __name__ == "__main__":
    unittest.main()
