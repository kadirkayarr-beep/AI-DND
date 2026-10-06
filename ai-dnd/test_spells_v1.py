"""Spells V1: Python owns the cast, the slot, and the hit points."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import game
import spells


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

    def rolls(self, *expected):
        remaining = iter(expected)

        def randint(low, high):
            roll = next(remaining, None)
            self.assertIsNotNone(roll, f"Unexpected d{high} roll")
            sides, value = roll
            self.assertEqual((low, high), (1, sides))
            self.assertTrue(low <= value <= high)
            return value

        return patch.object(self.session.rng, "randint", side_effect=randint), remaining

    def cast(self, text, *dice, target_id=None):
        patcher, remaining = self.rolls(*dice)
        with patcher:
            result = self.session.execute_intent(
                {"intent": "cast"},
                text,
                target_id=target_id,
            )
        self.assertIsNone(next(remaining, None), "Unused scripted dice")
        return result

    def test_fire_bolt_hits_and_cantrip_spends_no_slot(self):
        _character(self.session, "Wizard", cantrips=["Fire Bolt"], slots=0)
        result = self.cast(
            "I cast Fire Bolt at Sentinel",
            (20, 15), (20, 5), (20, 10), (10, 4), (20, 1),
        )
        self.assertEqual(result["outcome"], "hit")
        self.assertEqual(result["damage"], 4)
        self.assertEqual(result["attack_bonus"], 5)
        self.assertFalse(result["slot_spent"])
        self.assertEqual(self.npc["current_hp"], 26)
        self.assertEqual(spells.remaining_slots(self.session.character), 0)
        self.assertTrue(result["combat_started"])

    def test_fire_bolt_miss_and_critical(self):
        _character(self.session, "Wizard", cantrips=["Fire Bolt"], slots=2)
        missed = self.cast(
            "I cast Fire Bolt at Sentinel",
            (20, 15), (20, 5), (20, 1), (20, 1),
        )
        self.assertEqual(missed["outcome"], "miss")
        self.assertEqual(self.npc["current_hp"], 30)
        self.assertEqual(spells.remaining_slots(self.session.character), 2)
        self.session.end_combat()
        self.npc["current_hp"] = 30
        self.npc["combat_status"] = "active"
        critical = self.cast(
            "Ateş oku büyüsü yapıyorum Sentinel",
            (20, 15), (20, 5), (20, 20), (10, 4), (10, 3), (20, 1),
        )
        self.assertEqual(critical["outcome"], "critical_hit")
        self.assertEqual(critical["damage"], 7)
        self.assertEqual(self.npc["current_hp"], 23)

    def test_sacred_flame_save_and_failure(self):
        _character(self.session, "Cleric", cantrips=["Sacred Flame"])
        saved = self.cast(
            "I cast Sacred Flame at Sentinel",
            (20, 15), (20, 5), (20, 18), (20, 1),
        )
        self.assertEqual(saved["outcome"], "saved")
        self.assertEqual(saved["save_dc"], 13)
        self.assertEqual(saved["damage"], 0)
        self.assertEqual(self.npc["current_hp"], 30)
        self.session.end_combat()
        failed = self.cast(
            "Kutsal alev büyüsü yapıyorum Sentinel",
            (20, 15), (20, 5), (20, 10), (8, 5), (20, 1),
        )
        self.assertEqual(failed["outcome"], "failed_save")
        self.assertEqual(failed["damage"], 5)
        self.assertEqual(self.npc["current_hp"], 25)
        self.assertFalse(failed["slot_spent"])

    def test_magic_missile_spends_a_slot_on_an_automatic_hit(self):
        _character(self.session, "Sorcerer", known=["Magic Missile"], slots=2)
        result = self.cast(
            "I cast Magic Missile at Sentinel",
            (20, 15), (20, 5), (4, 1), (4, 2), (4, 3), (20, 1),
        )
        self.assertEqual(result["outcome"], "automatic_hit")
        self.assertEqual(result["damage"], 9)
        self.assertTrue(result["slot_spent"])
        self.assertEqual(spells.remaining_slots(self.session.character), 1)
        self.assertEqual(self.npc["current_hp"], 21)

    def test_empty_slot_rejects_without_mutation(self):
        _character(self.session, "Wizard", known=["Magic Missile"], slots=0)
        before = self.session.serialize_game_state()
        result = self.cast("I cast Magic Missile at Sentinel")
        self.assertEqual(result["outcome"], "no_slot")
        self.assertFalse(result["slot_spent"])
        self.assertFalse(self.world["combat"]["active"])
        self.assertEqual(self.npc["current_hp"], 30)
        self.assertEqual(
            self.session.serialize_game_state()["player"]["spell_slots_remaining"],
            before["player"]["spell_slots_remaining"],
        )

    def test_cure_wounds_heals_self_and_does_not_start_combat(self):
        _character(self.session, "Cleric", known=["Cure Wounds"], slots=1, wisdom_mod=3)
        result = self.cast("I cast Cure Wounds on myself", (8, 2), (8, 3))
        self.assertEqual(result["outcome"], "healed")
        self.assertEqual(result["healing"], 8)
        self.assertEqual(self.session.character["current_hp"], 18)
        self.assertTrue(result["slot_spent"])
        self.assertFalse(self.world["combat"]["active"])
        self.assertEqual(spells.remaining_slots(self.session.character), 0)

    def test_rejections_do_not_spend_or_change_hp(self):
        _character(self.session, "Fighter", cantrips=["Fire Bolt"], slots=2)
        wrong_class = self.cast("I cast Fire Bolt at Sentinel")
        self.assertEqual(wrong_class["outcome"], "invalid_class")
        _character(self.session, "Wizard", cantrips=[], known=["Shield"], slots=2)
        unknown = self.cast("I cast Fire Bolt at Sentinel")
        self.assertEqual(unknown["outcome"], "not_known")
        unsupported = self.cast("I cast Shield")
        self.assertEqual(unsupported["outcome"], "unsupported")
        _character(self.session, "Wizard", cantrips=["Fire Bolt"], slots=2, level=0)
        low_level = self.cast("I cast Fire Bolt at Sentinel")
        self.assertEqual(low_level["outcome"], "invalid_level")
        missing = self.cast("büyü yapıyorum")
        self.assertEqual(missing["outcome"], "unknown_spell")
        self.assertEqual(self.npc["current_hp"], 30)
        self.assertEqual(self.session.character["current_hp"], 10)
        self.assertFalse(self.world["combat"]["active"])

    def test_model_cannot_relabel_a_cast_or_author_damage(self):
        _character(self.session, "Wizard", cantrips=["Fire Bolt"], slots=2)
        with patch.object(game, "parse_player_intent", side_effect=AssertionError("model")):
            intent = self.session.validate_intent(
                self.session.normalize_intent({"intent": "attack"}, "I cast Fire Bolt at Sentinel"),
                "I cast Fire Bolt at Sentinel",
            )
        self.assertEqual(intent["intent"], "cast")
        result = self.cast(
            "I cast Fire Bolt at Sentinel",
            (20, 15), (20, 5), (20, 10), (10, 4), (20, 1),
        )
        self.assertEqual(result["damage"], 4)
        self.assertEqual(self.npc["current_hp"], 26)

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
        _character(self.session, "Wizard", known=["Magic Missile"], slots=2)
        other = game.create_session(seed=9)
        _character(other, "Wizard", known=["Magic Missile"], slots=2)
        self.cast(
            "I cast Magic Missile at Sentinel",
            (20, 15), (20, 5), (4, 1), (4, 1), (4, 1), (20, 1),
        )
        self.assertEqual(spells.remaining_slots(self.session.character), 1)
        self.assertEqual(spells.remaining_slots(other.character), 2)


if __name__ == "__main__":
    unittest.main()
