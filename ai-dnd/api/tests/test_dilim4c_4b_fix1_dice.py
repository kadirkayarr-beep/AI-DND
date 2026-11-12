"""Dilim 4C Task 4b fix round 1 (review), part 2: die sizes and the Bless d4 are
pinned by the dice the engine asks for, the DC cap, Relentless Endurance's save, a real ability check, Bless lasting
ten full rounds whatever the caster's place in initiative, and a stale record never narrated or dropped.
Fixture: test_spell_scope.caster (fixed session seed 17; no campaign, no town)."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import combat_lifecycle
import spell_concentration
import spell_registry
import spell_scope
import weapon_attack
from api.tests.test_dilim4c_spell_resolvers import cleric, held, magic, next_turn, turn, typed, wizard

class Spy:
    """rng.randint stand-in: records the sides asked for and answers a fixed face (never above the die)."""

    def __init__(self, face=1):
        self.face, self.asked = face, []

    def __call__(self, low, high):
        self.asked.append((low, high))
        return min(self.face, high)


def blessed():
    s, enemy = cleric()
    turn(s, magic("Bless", "player"))
    return s, enemy


class DiceArePinned(unittest.TestCase):
    def test_healing_word_rolls_d4s(self):
        s, enemy = cleric()
        s.character["current_hp"] = 10
        spy = Spy(2)
        with patch.object(s.rng, "randint", side_effect=spy):
            s.run_player_turn("Hamle.", combat_action=magic("Healing Word", "player"))
        self.assertEqual(spy.asked, [(1, 4), (1, 4)])

    def test_the_bless_die_is_a_d4_on_a_save(self):
        s, enemy = blessed()
        spy = Spy(4)
        with patch("game.roll_d20", return_value=10), patch.object(s.rng, "randint", side_effect=spy):
            save = weapon_attack.save(s, "player", ["wisdom"], 10)
        self.assertEqual((spy.asked, save["bless_roll"]), ([(1, 4)], 4))

    def test_the_bless_die_is_added_to_a_spell_attack_roll(self):
        s, enemy = wizard()
        spell_concentration.start(s, "Bless", 1, ["player"])  # a blessed Wizard (a Cleric's Bless on them)
        spy = Spy(3)
        with patch("game.roll_d20", return_value=10), patch.object(s.rng, "randint", side_effect=spy):
            result = spell_scope.cast(s, "Ray of Frost", enemy["id"])
        resolution = result["resolution"]
        self.assertEqual(spy.asked[0], (1, 4))
        self.assertEqual(resolution["bless_roll"], 3)
        self.assertEqual(resolution["total"], 10 + result["spell_attack_modifier"] + 3)

    def test_the_save_dc_is_capped_at_thirty(self):
        self.assertEqual([spell_concentration.save_dc(d) for d in (62, 63, 100, 1000)], [30, 30, 30, 30])
        s, enemy = blessed()
        s.character.update(max_hp=500, current_hp=500)
        with patch("game.roll_d20", return_value=20), patch.object(s.rng, "randint", return_value=1):
            hit = s._apply_attack_damage_to_player(100, False, True)
        self.assertEqual(hit["concentration_check"]["dc"], 30)

    def test_relentless_endurance_still_asks_the_save(self):
        s, enemy = blessed()
        s.character.update(species="Orc", race="Orc", current_hp=5)
        s._species_trait_state()["relentless_endurance_available"] = True
        with patch("game.roll_d20", return_value=2), patch.object(s.rng, "randint", return_value=1):
            hit = s._apply_attack_damage_to_player(10, False, True)
        self.assertEqual(s.character["current_hp"], 1)
        self.assertEqual({k: hit["concentration_check"][k] for k in ("dc", "kept")}, {"dc": 10, "kept": False})
        self.assertIsNone(spell_concentration.current(s.world_state))

    def test_an_ability_check_gets_no_bless_die(self):
        s, enemy = blessed()
        plain, _ = cleric()
        modifiers = {name: 0 for name in ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")}
        totals = []
        for session in (s, plain):
            spy = Spy(4)
            with patch("game.roll_d20", return_value=10), patch.object(session.rng, "randint", side_effect=spy):
                totals.append(session.perform_skill_check("Athletics", 10, modifiers, [], 2)["resolution"]["total"])
            self.assertEqual(spy.asked, [])
        self.assertEqual(totals[0], totals[1])


class BlessLastsTenFullRounds(unittest.TestCase):
    def test_a_caster_later_in_initiative_keeps_it_until_its_own_turn_ten_rounds_on(self):
        s, enemy = blessed()
        combat = s.world_state["combat"]
        started = spell_concentration.current(s.world_state)["started_round"]
        combat["round"] = started + 10
        combat["current_actor_id"] = enemy["id"]  # a creature acting before the caster in that round
        self.assertIsNotNone(spell_concentration.holds(s))
        self.assertIsNone(spell_concentration.settle(s))
        combat["current_actor_id"] = "player"
        self.assertIsNone(spell_concentration.holds(s))
        combat["current_actor_id"] = enemy["id"]
        combat["round"] = started + 11
        self.assertIsNone(spell_concentration.holds(s))  # a caster who lost its turn: over by the next round


class StaleRecord(unittest.TestCase):
    def stale(self):
        s, enemy = cleric()
        turn(s, magic("Bless", "player"))
        next_turn(s)  # a fresh turn (and slot use) for the next cast
        record = copy.deepcopy(spell_concentration.current(s.world_state))
        s.world_state[spell_concentration.KEY] = {**record, "combat_id": "an-old-fight"}  # a record of a finished fight
        return s, enemy

    def test_a_stale_record_is_not_narrated_as_ended(self):
        s, enemy = self.stale()
        result = turn(s, magic("Bless", "player"))
        self.assertNotIn("konsantrasyonun biter", result["narration"])
        self.assertIsNone(result["action_result"]["economy_steps"][0]["result"]["concentration_ended"])

    def test_a_stale_record_cannot_be_dropped(self):
        s, enemy = self.stale()
        before = held(s)
        with self.assertRaises(combat_lifecycle.CombatRequestError) as raised:
            typed(s, "Konsantrasyonu bırakıyorum")
        self.assertEqual(raised.exception.code, "concentration_not_held")
        self.assertEqual(held(s), before)


class RegistryDeltaRows(unittest.TestCase):
    def test_rider_and_concentration_rows(self):
        s, enemy = wizard()
        with patch("game.roll_d20", return_value=19), patch.object(s.rng, "randint", return_value=2):
            ray = spell_registry.cast_spell("Ray of Frost", {"session": s}, None, {"target_id": enemy["id"]})
        self.assertIn({"kind": "spell_rider", "target_id": enemy["id"], "rider": "ray_of_frost"}, ray["changes"])
        c, _ = cleric()
        bless = spell_registry.cast_spell("Bless", {"session": c}, None, {"target_id": "player"})
        self.assertIn({"kind": "concentration", "spell_id": "Bless", "targets": ["player"]}, bless["changes"])


if __name__ == "__main__":
    unittest.main()
