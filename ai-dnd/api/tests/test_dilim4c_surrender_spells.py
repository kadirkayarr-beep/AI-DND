"""Dilim 4C Task 4a part 1 (D-036, D-045): a harmful spell at a surrendered foe is asked about first, like a weapon blow.

Same question, same "evet" binding to the asked creature, cleared with its fight, asked once. A healing spell is never
asked. A surrendered foe that has since gone down (D-045) is no longer "surrendered": it is not asked about, and an old
question about it strikes nothing. Engine tests on the 4C.0 fixture (monster_combat fixture, fixed session seed); the
HTTP chain (button cast, model-free "evet", replay, Undo) is in test_dilim4c_surrender_spells_http."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import action_economy
import combat_lifecycle
import spell_scope
from api.dnd_2024_rules import CLASS_DEFINITIONS, SPELLS_CATALOG
from api.tests.test_dilim4c_surrender_state import surrendered_fight


def become(s, cls):
    """The test_spell_scope caster access (creation catalog order), on this session."""
    s.character.update({"class": cls, "level": 1, "proficiency_bonus": 2, "charisma": 16, "intelligence": 16,
                        "wisdom": 16})
    catalog = SPELLS_CATALOG[cls]
    s.character["cantrips"] = [v["id"] for v in catalog["cantrips"]][:CLASS_DEFINITIONS[cls]["cantrips_count"]]
    s.character["spells"] = (["Magic Missile", "Shield"] if cls == "Sorcerer" else
                             ["Cure Wounds", *[v["id"] for v in catalog["spells_level_1"] if v["id"] != "Cure Wounds"][:3]])
    s.world_state.pop("spellcasting_v1", None)
    spell_scope.initialize(s)


def caster_fight():
    """The 4C.0 surrendered fight, the player a level-1 Sorcerer (Fire Bolt, Magic Missile) with both foes in sight."""
    s, n, other = surrendered_fight()
    become(s, "Sorcerer")
    n["conditions"] = []  # the yield fixture's fear is spent; a frightened target is a deferred spell-attack rider
    s.world_state["equipment"] = {"main_hand": None, "off_hand": None}
    s.world_state["attack_environment"] = {"pairs": {
        f"player|{foe['id']}": {"distance_ft": 30, "attacker_sees_target": True, "target_sees_attacker": True,
                                "cover": "none"} for foe in (n, other)}}
    combat = s.world_state["combat"]
    for _ in range(6):
        if combat["current_actor_id"] == "player":
            break
        s.advance_combat_turn()
    assert combat["current_actor_id"] == "player"
    return s, n, other


HELD = ("combat", "npcs", "monster_combat", "xp_awarded_event_ids", "spellcasting_v1")


def held(s):
    return copy.deepcopy(({k: s.world_state.get(k) for k in HELD}, s.character))


def magic(spell, target):
    return {"steps": [{"kind": "magic", "ability": spell, "target_id": target}]}


class HarmfulSpellAtTheSurrenderedIsAsked(unittest.TestCase):
    def test_a_typed_spell_asks_first_and_changes_nothing(self):
        s, n, other = caster_fight()
        before = held(s)
        result = s.run_player_turn("Ateş oku atıyorum", target_id=n["id"])
        self.assertEqual(result["action_result"]["status"], "clarification")
        self.assertEqual(result["action_result"]["outcome"], "surrendered_target")
        self.assertEqual(result["action_result"]["target_id"], n["id"])
        self.assertIn("teslim olmuş birine saldırıyorsun", result["narration"])
        self.assertEqual(held(s), before)

    def test_a_button_spell_asks_first_and_spends_no_slot(self):
        s, n, other = caster_fight()
        before = held(s)
        result = s.run_player_turn("Hamle.", combat_action=magic("Magic Missile", n["id"]))
        self.assertEqual(result["action_result"]["outcome"], "surrendered_target")
        self.assertEqual(held(s), before)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 2})

    def test_a_yes_casts_the_asked_spell_at_the_asked_foe_once(self):
        s, n, other = caster_fight()
        s.run_player_turn("Hamle.", combat_action=magic("Magic Missile", n["id"]))
        with patch.object(s.rng, "randint", return_value=4):
            result = s.run_player_turn("evet", target_id=other["id"])
        self.assertEqual(result["action_result"]["status"], "resolved")
        self.assertEqual(result["action_result"]["spell"], "Magic Missile")
        self.assertEqual(result["action_result"]["target_id"], n["id"])
        self.assertLess(n["current_hp"], 10)
        self.assertEqual(other["current_hp"], 8)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1})
        self.assertIsNone(s._surrender_strike_asked)

    def test_a_typed_yes_casts_the_typed_spell(self):
        s, n, other = caster_fight()
        s.run_player_turn("Ateş oku atıyorum", target_id=n["id"])
        with patch("game.roll_d20", return_value=15), patch.object(s.rng, "randint", return_value=4):
            result = s.run_player_turn("evet")
        self.assertEqual(result["action_result"].get("spell"), "Fire Bolt")
        self.assertEqual(n["current_hp"], 6)

    def test_the_same_spell_again_casts_without_a_second_question(self):
        s, n, other = caster_fight()
        s.run_player_turn("Ateş oku atıyorum", target_id=n["id"])
        with patch("game.roll_d20", return_value=15), patch.object(s.rng, "randint", return_value=4):
            result = s.run_player_turn("Ateş oku atıyorum", target_id=n["id"])
        self.assertNotEqual(result["action_result"].get("status"), "clarification")
        self.assertEqual(n["current_hp"], 6)

    def test_the_same_button_again_casts_without_a_second_question(self):
        s, n, other = caster_fight()
        s.run_player_turn("Hamle.", combat_action=magic("Magic Missile", n["id"]))
        with patch.object(s.rng, "randint", return_value=4):
            result = s.run_player_turn("Hamle.", combat_action=magic("Magic Missile", n["id"]))
        self.assertEqual(result["action_result"]["status"], "resolved")
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1})

    def test_a_no_casts_nothing(self):
        s, n, other = caster_fight()
        s.run_player_turn("Ateş oku atıyorum", target_id=n["id"])
        before = held(s)
        s.run_player_turn("hayır", target_id=n["id"])
        self.assertEqual(n["current_hp"], 10)
        self.assertEqual(s.world_state["spellcasting_v1"], before[0]["spellcasting_v1"])
        self.assertIsNone(getattr(s, "_surrender_strike_asked", None))

    def test_a_spell_at_the_fighting_foe_is_not_asked(self):
        s, n, other = caster_fight()
        with patch.object(s.rng, "randint", return_value=4):
            result = s.run_player_turn("Hamle.", combat_action=magic("Magic Missile", other["id"]))
        self.assertEqual(result["action_result"]["status"], "resolved")
        self.assertEqual(result["action_result"]["target_id"], other["id"])

    def test_a_spell_question_ends_with_the_fight(self):
        s, n, other = caster_fight()
        s.run_player_turn("Hamle.", combat_action=magic("Magic Missile", n["id"]))
        other.update(current_hp=0, combat_status="dead")
        s._combat_end_if_decided()
        self.assertFalse(s.world_state["combat"]["active"])
        self.assertIsNone(s._surrender_strike_asked)
        self.assertIsNone(combat_lifecycle.answered_surrender_question(s, "evet"))


class HealingIsNeverAsked(unittest.TestCase):
    def test_cure_wounds_on_oneself_while_a_foe_surrendered_is_not_asked(self):
        s, n, other = caster_fight()
        become(s, "Bard")
        s.character["current_hp"] = 5
        with patch.object(s.rng, "randint", return_value=4):
            result = s.run_player_turn("Hamle.", combat_action=magic("Cure Wounds", "player"))
        self.assertEqual(result["action_result"]["status"], "resolved")
        self.assertGreater(s.character["current_hp"], 5)


class FallenSurrenderedFoe(unittest.TestCase):
    """D-045: a surrendered foe that went down while the fight goes on is out, not 'surrendered'."""

    def test_a_dead_surrendered_foe_no_longer_reads_surrendered(self):
        s, n, other = caster_fight()
        self.assertTrue(action_economy._surrendered(s, n["id"]))
        n.update(current_hp=0, combat_status="dead")
        self.assertTrue(s.world_state["combat"]["active"])
        self.assertFalse(action_economy._surrendered(s, n["id"]))

    def test_a_blow_at_a_dead_surrendered_foe_is_not_the_surrender_question(self):
        s, n, other = caster_fight()
        n.update(current_hp=0, combat_status="dead")
        try:
            result = s.run_player_turn("Muhafıza saldırıyorum", target_id=n["id"])
        except combat_lifecycle.CombatRequestError:  # its own dead-target owner may refuse; never the surrender question
            result = {"action_result": {}}
        self.assertNotEqual(result["action_result"].get("outcome"), "surrendered_target")
        self.assertIsNone(getattr(s, "_surrender_strike_asked", None))

    def test_a_yes_after_the_asked_foe_died_strikes_nothing(self):
        s, n, other = caster_fight()
        s.run_player_turn("Muhafıza saldırıyorum", target_id=n["id"])
        self.assertIsNotNone(s._surrender_strike_asked)
        n.update(current_hp=0, combat_status="dead")
        self.assertIsNone(combat_lifecycle.answered_surrender_question(s, "evet"))
        self.assertIsNone(s._surrender_strike_asked)


if __name__ == "__main__":
    unittest.main()
