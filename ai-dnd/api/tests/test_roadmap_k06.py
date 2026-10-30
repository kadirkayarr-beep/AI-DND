"""K06: movement cost, range and cover come from ONE spatial owner and match an independent hand-computed oracle.

Sources (D&D 5e - Players Handbook 2024.pdf): p.24 "Every foot of movement in Difficult Terrain costs 1 extra foot, even if
multiple things count as Difficult Terrain"; p.363 crawling and p.362 climbing "each foot costs 1 extra foot (2 extra feet in
Difficult Terrain)", the climbing surcharge ignored with a Climb Speed; p.25 cover: Half +2 AC, Three-Quarters +5 AC, Total can't
be targeted, only the most protective degree applies. The oracle values below are written by hand from those lines, not read
back from the engine. The map is only a projection of these canonical facts; there is no second geometry engine.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import action_economy as ae
import game
import spatial_rules
from api.tests.test_species_traits import attack_fixture, make_session
from combat_lifecycle import CombatRequestError


# (crawling, climbing, climb_speed, difficult) -> cost of 5 ft, hand computed from the quoted rules
ORACLE_5FT = {
    (False, False, False, False): 5,
    (False, False, False, True): 10,   # +1 per foot in Difficult Terrain
    (True, False, False, False): 10,   # crawling +1 per foot
    (True, False, False, True): 15,    # crawling in Difficult Terrain: +2 per foot
    (False, True, False, False): 10,   # climbing +1 per foot
    (False, True, False, True): 15,    # climbing in Difficult Terrain: +2 per foot
    (False, True, True, False): 5,     # a Climb Speed ignores the extra cost
    (False, True, True, True): 10,     # ...but Difficult Terrain still costs +1
}


def target_at(session, distance_ft=5, **facts):
    target = {"id": "t", "name": "T", "current_hp": 20, "max_hp": 20, "armor_class": 10, "combat_status": "active"}
    target.update(facts)
    attack_fixture(session, target)
    target["distance_ft"] = distance_ft
    return target


class SpatialOracleTests(unittest.TestCase):
    def test_movement_cost_matches_the_independent_oracle(self):
        for (crawling, climbing, climb_speed, difficult), expected in ORACLE_5FT.items():
            with self.subTest(crawling=crawling, climbing=climbing, climb_speed=climb_speed, difficult=difficult):
                actual = spatial_rules.movement_cost(
                    5, crawling=crawling, climbing=climbing, has_climb_speed=climb_speed, difficult_terrain=difficult)
                self.assertEqual(actual, expected)

    def test_the_real_move_action_spends_the_oracle_cost(self):
        session = make_session("Aasimar", level=3)
        session.world_state["npcs"].clear()
        target = {"id": "foe", "name": "Foe", "location": session.world_state["location"], "combat_status": "active",
                  "current_hp": 10, "max_hp": 10, "armor_class": 10, "distance_ft": 5, "attack_damage_type": "bludgeoning"}
        session.world_state["npcs"].append(target)
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            session.start_combat(target)
        session.character["prone"] = True
        used_before = ae.ensure(session)["player"]["movement_used"]
        ae.move(session, "player", 5)
        self.assertEqual(ae.ensure(session)["player"]["movement_used"] - used_before, ORACLE_5FT[(True, False, False, False)])

    def test_cover_changes_armor_class_exactly_as_the_table_says_and_total_cover_blocks(self):
        for cover, bonus in (("none", 0), ("half", 2), ("three_quarters", 5)):
            with self.subTest(cover=cover):
                session = make_session("Aasimar", level=3)
                target = target_at(session)
                session.world_state["attack_environment"] = {"pairs": {"player|t": {"distance_ft": 5, "cover": cover}}}
                with patch("game.roll_attack", return_value=15), patch("game.roll_damage", return_value=1):
                    result = session.resolve_attack("attack", "Kılıç", game.WEAPONS["Kılıç"], target)
                self.assertEqual(result["target_ac"], 10 + bonus)
        session = make_session("Aasimar", level=3)
        target = target_at(session)
        session.world_state["attack_environment"] = {"pairs": {"player|t": {"distance_ft": 5, "cover": "total"}}}
        with self.assertRaises(CombatRequestError) as caught:
            session.resolve_attack("attack", "Kılıç", game.WEAPONS["Kılıç"], target)
        self.assertEqual(caught.exception.code, "total_cover")

    def test_only_the_most_protective_cover_applies_and_the_degrees_never_add(self):
        session = make_session("Aasimar", level=3)
        target = target_at(session)
        session.world_state["attack_environment"] = {"pairs": {"player|t": {"distance_ft": 5, "cover": ["half", "three_quarters"]}}}
        with patch("game.roll_attack", return_value=15), patch("game.roll_damage", return_value=1):
            result = session.resolve_attack("attack", "Kılıç", game.WEAPONS["Kılıç"], target)
        self.assertEqual(result["target_ac"], 15, "Three-Quarters (+5) only; 2 + 5 would be wrong")

    def test_an_unknown_distance_is_never_invented(self):
        session = make_session("Aasimar", level=3)
        target = target_at(session)
        del target["distance_ft"]
        with patch("game.roll_attack", return_value=15) as roll:
            with self.assertRaises(CombatRequestError) as caught:
                session.resolve_attack("attack", "Kılıç", game.WEAPONS["Kılıç"], target)
        self.assertEqual(caught.exception.code, "distance_unknown")
        roll.assert_not_called()

    def test_starting_combat_is_not_a_hit(self):
        session = make_session("Aasimar", level=3)
        session.world_state["npcs"].clear()
        target = {"id": "t", "name": "T", "location": session.world_state["location"], "combat_status": "active",
                  "current_hp": 20, "max_hp": 20, "armor_class": 10, "distance_ft": 5, "attack_damage_type": "bludgeoning"}
        session.world_state["npcs"].append(target)
        before = (target["current_hp"], session.character["current_hp"])
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            session.start_combat(target)
        self.assertEqual((target["current_hp"], session.character["current_hp"]), before)
        self.assertTrue(session.world_state["combat"]["active"])

    def test_one_owner_serves_every_caller(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[2]
        for name in ("action_economy.py", "weapon_attack.py", "spell_scope.py"):
            text = (root / name).read_text(encoding="utf-8")
            self.assertNotRegex(text, r'\{"none": 0, "half": 2, "three_quarters": 5', f"{name} keeps its own cover table")
            self.assertNotRegex(text, r'int\(route\.get\("difficult_terrain"\) is True\)', f"{name} keeps its own movement formula")


if __name__ == "__main__":
    unittest.main()
