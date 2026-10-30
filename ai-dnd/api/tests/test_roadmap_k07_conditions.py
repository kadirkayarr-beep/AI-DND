"""K07 conditions: Speed, acting, movement, attack rolls and saves, through the real mechanic owners.

Source: K07 release_v2 glossary.md (condition entries; printed pages are the PDF ordinal + 1 except the Unconscious entry whose
printed label is [?]): Blinded PDF 360, Exhaustion 365, Grappled 366, Incapacitated 368, Paralyzed 370, Petrified/Poisoned/Prone 371,
Restrained 372, Stunned 375, Unconscious 376, Speed 373, Dodge 365.
Speed is 0 only for Grappled, Paralyzed, Petrified, Restrained and Unconscious. Incapacitated (and Stunned, which only grants
Incapacitated) does NOT set Speed to 0: it prevents actions, Bonus Actions and Reactions, not movement. Exhaustion lowers Speed by
5 ft per level. Petrified: attacks against it have Advantage and it automatically fails Strength and Dexterity saves. Restrained:
Disadvantage on Dexterity saves. Not covered (owners in HANDOFF): Charmed/Deafened/Frightened details, Invisible, Prone crawling cost,
Unconscious dropping items, Exhaustion D20 penalty and death at 6 (other owners), Concentration, and every condition source that is
not in release_v2.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import action_economy as ae
import weapon_attack as attack
from api.tests.test_campaign_time import scene
from api.tests.test_weapon_attack import armed, resolve
from combat_lifecycle import CombatRequestError

SPEED = 30  # the premise of every case below: the creature's base Speed is set explicitly, never inherited from a default
SPEED_ZERO = ("grappled", "restrained", "paralyzed", "petrified", "unconscious")
SPEED_KEPT = ("incapacitated", "stunned", "prone", "poisoned", "blinded", "charmed", "deafened", "frightened", "invisible")
CANNOT_ACT = ("incapacitated", "stunned", "paralyzed", "petrified", "unconscious")


def fighter_with(*names, exhaustion=0):
    session, enemy = armed()
    session.character.update(speed_ft=SPEED, conditions=list(names), exhaustion=exhaustion)
    return session, enemy


def code_of(callable_, *args):
    try:
        callable_(*args)
    except CombatRequestError as error:
        return error.code
    return "ok"


class SpeedTests(unittest.TestCase):
    def test_speed_is_zero_only_for_the_five_conditions_that_say_so(self):
        for name in SPEED_ZERO:
            with self.subTest(name=name):
                session, _ = fighter_with(name)
                self.assertEqual(ae.speed(session, "player"), 0)
        for name in SPEED_KEPT:
            with self.subTest(name=name):
                session, _ = fighter_with(name)
                self.assertEqual(ae.speed(session, "player"), SPEED)

    def test_a_second_condition_that_sets_speed_to_zero_still_wins_over_incapacitated(self):
        for other in SPEED_ZERO:
            with self.subTest(other=other):
                session, _ = fighter_with("incapacitated", other)
                self.assertEqual(ae.speed(session, "player"), 0)

    def test_exhaustion_lowers_speed_by_five_feet_per_level_with_or_without_incapacitated(self):
        for levels, expected in ((1, 25), (2, 20), (3, 15)):
            with self.subTest(levels=levels):
                self.assertEqual(ae.speed(fighter_with(exhaustion=levels)[0], "player"), expected)
                self.assertEqual(ae.speed(fighter_with("incapacitated", exhaustion=levels)[0], "player"), expected)

    def test_the_same_rule_holds_outside_combat(self):
        for name, expected in (("incapacitated", SPEED), ("stunned", SPEED), ("grappled", 0), ("paralyzed", 0), ("unconscious", 0)):
            with self.subTest(name=name):
                session = scene()
                session.character.update(speed_ft=SPEED, conditions=[name])
                self.assertEqual(ae.speed(session, "player"), expected)


class MovementAndActionsTests(unittest.TestCase):
    def test_incapacitated_and_stunned_creatures_can_still_move_but_cannot_act(self):
        for name in ("incapacitated", "stunned"):
            with self.subTest(name=name):
                session, _ = fighter_with(name)
                self.assertEqual(code_of(ae.move, session, "player", 10), "ok")
                self.assertEqual(code_of(ae.consume_action, session, "player", "attack", "action"), "actor_cannot_act")
                self.assertEqual(code_of(ae.dash, session, "player"), "actor_cannot_act")

    def test_every_condition_that_prevents_actions_refuses_them(self):
        for name in CANNOT_ACT:
            with self.subTest(name=name):
                session, _ = fighter_with(name)
                self.assertEqual(code_of(ae.consume_action, session, "player", "attack", "action"), "actor_cannot_act")

    def test_conditions_that_set_speed_to_zero_refuse_movement_for_the_budget_reason(self):
        for name in SPEED_ZERO:
            with self.subTest(name=name):
                session, _ = fighter_with(name)
                self.assertEqual(code_of(ae.move, session, "player", 5), "movement_unavailable")

    def test_incapacitated_plus_grappled_cannot_move_because_of_grappled_not_incapacitated(self):
        session, _ = fighter_with("incapacitated", "grappled")
        self.assertEqual(code_of(ae.move, session, "player", 5), "movement_unavailable")
        session, _ = fighter_with("incapacitated")
        self.assertEqual(code_of(ae.move, session, "player", 30), "ok")
        self.assertEqual(code_of(ae.move, session, "player", 5), "movement_unavailable")  # the Speed budget, not the condition

    def test_the_game_projection_shows_movement_for_incapacitated_but_not_for_speed_zero(self):
        for name, remaining, acts in (("incapacitated", SPEED, False), ("stunned", SPEED, False), ("grappled", 0, True), ("paralyzed", 0, False)):
            with self.subTest(name=name):
                session, _ = fighter_with(name)
                row = ae.projection(session)["actors"]["player"]
                self.assertEqual((row["speed_ft"], row["movement_remaining"]), (SPEED if remaining else 0, remaining))
                self.assertEqual(row["action_available"], acts)

    def test_an_out_of_turn_creature_still_cannot_move(self):
        session, _ = fighter_with("incapacitated")
        session.world_state["combat"]["current_actor_id"] = "someone-else"
        self.assertEqual(code_of(ae.move, session, "player", 5), "out_of_turn")


class AttackAndSaveTests(unittest.TestCase):
    def test_petrified_target_gives_attack_rolls_advantage(self):
        session, enemy = armed()
        enemy["conditions"] = ["petrified"]
        result = resolve(session, enemy, rolls=(10, 15))
        self.assertIn("target_petrified", result["advantage_sources"])

    def test_strength_and_dexterity_saves_fail_automatically_for_paralyzed_petrified_stunned_unconscious_only(self):
        for name, auto in (("paralyzed", True), ("petrified", True), ("stunned", True), ("unconscious", True),
                           ("incapacitated", False), ("restrained", False), ("grappled", False)):
            for ability in ("strength", "dexterity", "wisdom"):
                with self.subTest(name=name, ability=ability):
                    session, enemy = armed()
                    enemy["conditions"] = [name]
                    with patch.object(session, "roll_d20", return_value=20):
                        result = attack.save(session, enemy["id"], [ability], 10, ability)
                    self.assertEqual(result.get("automatic_failure", False), auto and ability != "wisdom")

    def test_restrained_has_disadvantage_on_dexterity_saves_only(self):
        session, enemy = armed()
        enemy["conditions"] = ["restrained"]
        with patch.object(session, "roll_d20", side_effect=[18, 4]):
            dex = attack.save(session, enemy["id"], ["dexterity"], 10, "dexterity")
        self.assertEqual(dex["outcome"], "FAILURE")  # the lower of two rolls counts
        with patch.object(session, "roll_d20", side_effect=[18, 4]):
            strength = attack.save(session, enemy["id"], ["strength"], 10, "strength")
        self.assertEqual(strength["outcome"], "SUCCESS")  # one roll only: no Disadvantage on Strength saves
        other, enemy2 = armed()
        with patch.object(other, "roll_d20", side_effect=[18, 4]):
            free = attack.save(other, enemy2["id"], ["dexterity"], 10, "dexterity")
        self.assertEqual(free["outcome"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
