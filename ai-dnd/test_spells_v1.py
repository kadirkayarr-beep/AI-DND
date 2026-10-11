"""Spells V1 persistence, plus the spell_scope contract for casts.

Casts are resolved by spell_scope. execute_intent does not own a second resolver.
"""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import game
import spell_scope
import spells
from api.tests.test_spell_scope import caster


def _character(session, class_name, *, cantrips=(), known=(), slots=2, level=1,
               intelligence_mod=3, wisdom_mod=3):
    session.character.update(
        name="Ari",
        race="Human",
        **{"class": class_name},
        strength=10,
        dexterity=12,
        constitution=12,
        intelligence=16,
        wisdom=16,
        charisma=10,
        proficient_skills=["Arcana"],
        level=level,
        proficiency_bonus=2,
        max_hp=20,
        current_hp=10,
        armor_class=12,
        strength_mod=0,
        dexterity_mod=1,
        constitution_mod=1,
        intelligence_mod=intelligence_mod,
        wisdom_mod=wisdom_mod,
        charisma_mod=0,
        modifiers={
            "strength": 0,
            "dexterity": 1,
            "constitution": 1,
            "intelligence": intelligence_mod,
            "wisdom": wisdom_mod,
            "charisma": 0,
        },
        cantrips=list(cantrips),
        spells=list(known),
        spell_slots_remaining={"1": slots},
    )


class SpellCastTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=5)
        self.world = self.session.world_state
        self.world.update(location="tavern", npcs=[], player_combat_status="active")
        self.npc = {
            "id": "npc_test",
            "name": "Sentinel",
            "role": "guard",
            "location": "tavern",
            "max_hp": 30,
            "current_hp": 30,
            "armor_class": 10,
            "combat_status": "active",
            "dexterity_mod": 0,
            "attack_bonus": 0,
            "damage_die": 6,
            "damage_dice": 1,
            "damage_modifier": 0,
            "memory": [],
        }
        self.world["npcs"].append(self.npc)

    def test_fire_bolt_hits_and_cantrip_spends_no_slot(self):
        session, enemy = caster(cls="Wizard")
        before_hp = enemy["current_hp"]
        with patch("game.roll_d20", return_value=12), patch.object(session.rng, "randint", return_value=4):
            result = spell_scope.cast(session, "Fire Bolt", enemy["id"])
        self.assertTrue(result["hit"])
        self.assertEqual(result["damage"], 4)
        self.assertEqual(result["spell_attack_modifier"], 5)
        self.assertEqual(result["slot_level"], 0)
        self.assertEqual(session.world_state["spellcasting_v1"]["slots"], {"1": 2})
        self.assertEqual(enemy["current_hp"], before_hp - 4)

    def test_fire_bolt_miss_and_critical(self):
        session, enemy = caster(cls="Wizard")
        before_hp = enemy["current_hp"]
        with patch("game.roll_d20", return_value=1):
            missed = spell_scope.cast(session, "Fire Bolt", enemy["id"])
        self.assertFalse(missed["hit"])
        self.assertEqual(missed["resolution"]["outcome"], "MISS")
        self.assertEqual(missed["damage"], 0)
        self.assertEqual(enemy["current_hp"], before_hp)
        self.assertEqual(session.world_state["spellcasting_v1"]["slots"], {"1": 2})

        session, enemy = caster(cls="Wizard")
        before_hp = enemy["current_hp"]
        with patch("game.roll_d20", return_value=20), patch.object(session.rng, "randint", return_value=4):
            critical = spell_scope.cast(session, "Fire Bolt", enemy["id"])
        self.assertTrue(critical["hit"])
        self.assertEqual(critical["resolution"]["outcome"], "CRITICAL_HIT")
        self.assertEqual(critical["damage"], 8)
        self.assertEqual(enemy["current_hp"], before_hp - 8)

    def test_sacred_flame_save_and_failure(self):
        session, enemy = caster(cls="Cleric")
        before_hp = enemy["current_hp"]
        with patch("game.roll_d20", return_value=20):
            saved = spell_scope.cast(session, "Sacred Flame", enemy["id"])
        self.assertFalse(saved["hit"])
        self.assertEqual(saved["spell_save_dc"], 13)
        self.assertEqual(saved["damage"], 0)
        self.assertEqual(enemy["current_hp"], before_hp)
        self.assertEqual(session.world_state["spellcasting_v1"]["slots"], {"1": 2})

        session, enemy = caster(cls="Cleric")
        before_hp = enemy["current_hp"]
        with patch("game.roll_d20", return_value=1), patch.object(session.rng, "randint", return_value=5):
            failed = spell_scope.cast(session, "Sacred Flame", enemy["id"])
        self.assertTrue(failed["hit"])
        self.assertEqual(failed["resolution"]["outcome"], "FAILURE")
        self.assertEqual(failed["damage"], 5)
        self.assertEqual(enemy["current_hp"], before_hp - 5)
        self.assertEqual(failed["slot_level"], 0)

    def test_magic_missile_spends_a_slot_on_an_automatic_hit(self):
        session, enemy = caster(cls="Sorcerer")
        before_hp = enemy["current_hp"]
        with patch("game.roll_d20", side_effect=AssertionError("No attack roll")), patch.object(
            session.rng, "randint", return_value=2
        ):
            result = spell_scope.cast(session, "Magic Missile", enemy["id"])
        self.assertEqual(result["darts"], [3, 3, 3])
        self.assertTrue(result["hit"])
        self.assertEqual(result["damage"], 9)
        self.assertEqual(result["slot_level"], 1)
        self.assertEqual(session.world_state["spellcasting_v1"]["slots"], {"1": 1})
        self.assertEqual(enemy["current_hp"], before_hp - 9)

    def test_empty_slot_rejects_without_mutation(self):
        session, enemy = caster(cls="Sorcerer")
        session.world_state["spellcasting_v1"]["slots"]["1"] = 0
        before = (copy.deepcopy(session.world_state), copy.deepcopy(session.character), session.rng.getstate())
        with self.assertRaises(ValueError):
            spell_scope.cast(session, "Magic Missile", enemy["id"])
        self.assertEqual(
            (session.world_state, session.character, session.rng.getstate()),
            before,
        )

    def test_cure_wounds_heals_during_combat_and_refuses_to_open_combat(self):
        session, _enemy = caster(cls="Bard")
        session.end_combat("test")
        before = (copy.deepcopy(session.world_state), copy.deepcopy(session.character), session.rng.getstate())
        with self.assertRaises(ValueError):
            spell_scope.cast(session, "Cure Wounds", "player")
        self.assertEqual((session.world_state, session.character, session.rng.getstate()), before)

        session, _enemy = caster(cls="Bard")
        session.character["current_hp"] = 1
        with patch.object(session.rng, "randint", return_value=8):
            result = spell_scope.cast(session, "Cure Wounds", "player")
        self.assertEqual(result["rolled_healing"], 19)
        self.assertEqual(result["healing"], session.character["max_hp"] - 1)
        self.assertEqual(session.character["current_hp"], session.character["max_hp"])
        self.assertEqual(session.world_state["spellcasting_v1"]["slots"]["1"], 1)
        self.assertTrue(session.world_state["combat"]["active"])

    def test_rejections_do_not_spend_or_change_hp(self):
        session, enemy = caster(cls="Wizard")
        session.world_state["spellcasting_v1"]["cantrips"] = []
        before = (copy.deepcopy(session.world_state), copy.deepcopy(session.character), enemy["current_hp"])
        with self.assertRaises(ValueError):
            spell_scope.cast(session, "Fire Bolt", enemy["id"])
        self.assertEqual(
            (session.world_state, session.character, enemy["current_hp"]),
            before,
        )
        with self.assertRaises(ValueError):
            spell_scope.cast(session, "Sleep", enemy["id"])
        self.assertEqual(enemy["current_hp"], before[2])

        session, enemy = caster(cls="Wizard")
        session.character["level"] = 0
        before = (copy.deepcopy(session.world_state), copy.deepcopy(session.character), enemy["current_hp"])
        with self.assertRaises(ValueError):
            spell_scope.cast(session, "Fire Bolt", enemy["id"])
        self.assertEqual(
            (session.world_state, session.character, enemy["current_hp"]),
            before,
        )
        with self.assertRaises(ValueError):
            spell_scope.natural_command("büyü yapıyorum", enemy["id"])
        self.assertEqual(session.character["current_hp"], before[1]["current_hp"])

    def test_model_cannot_relabel_a_cast_or_author_damage(self):
        session, enemy = caster(cls="Wizard")
        before_hp = enemy["current_hp"]
        with patch.object(game, "parse_player_intent", side_effect=AssertionError("model")), patch(
            "game.roll_d20", return_value=12
        ), patch.object(session.rng, "randint", return_value=4):
            result = session.run_player_turn("I cast Fire Bolt", target_id=enemy["id"])
        spell_result = result["action_result"]["economy_steps"][0]["result"]
        self.assertEqual(spell_result["spell_id"], "Fire Bolt")
        self.assertEqual(spell_result["damage"], 4)
        self.assertEqual(enemy["current_hp"], before_hp - 4)
        self.assertEqual(result["model_calls"], 0)

    def test_save_load_and_legacy_migration(self):
        _character(self.session, "Wizard", cantrips=["Fire Bolt"], known=["Magic Missile"], slots=2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spell.json"
            self.session.save_game(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], game.SAVE_FORMAT_VERSION)
            self.assertEqual(payload["player"]["cantrips"], ["Fire Bolt"])
            self.assertEqual(payload["player"]["spell_slots_remaining"], {"1": 2})
            self.session.character["spell_slots_remaining"] = {"1": 0}
            self.session.character["cantrips"] = []
            self.session.load_game(path)
            self.assertEqual(self.session.character["cantrips"], ["Fire Bolt"])
            self.assertEqual(spells.remaining_slots(self.session.character), 2)

            for version in (1, 2, 3):
                legacy = copy.deepcopy(payload)
                legacy["version"] = version
                legacy["player"].pop("cantrips")
                legacy["player"].pop("spells")
                legacy["player"].pop("spell_slots_remaining")
                path.write_text(json.dumps(legacy), encoding="utf-8")
                self.session.character["cantrips"] = ["Fire Bolt"]
                self.session.character["spell_slots_remaining"] = {"1": 2}
                self.session.load_game(path)
                self.assertEqual(self.session.character["cantrips"], [])
                self.assertEqual(self.session.character["spells"], [])
                self.assertEqual(spells.remaining_slots(self.session.character), 0)

    def test_sessions_do_not_share_slots(self):
        session, enemy = caster(cls="Sorcerer")
        other, _other_enemy = caster(cls="Sorcerer")
        with patch.object(session.rng, "randint", return_value=2):
            spell_scope.cast(session, "Magic Missile", enemy["id"])
        self.assertEqual(session.world_state["spellcasting_v1"]["slots"], {"1": 1})
        self.assertEqual(other.world_state["spellcasting_v1"]["slots"], {"1": 2})


if __name__ == "__main__":
    unittest.main()
