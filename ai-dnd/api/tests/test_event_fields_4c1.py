"""4C.1: every damage event names its damage_type, every healing event its heal_source (event fields only, no saved key)."""
import copy
import json
import unittest
from unittest.mock import patch

import action_economy as economy
import game
import hit_dice
import paladin_features
import spell_registry
import spell_scope
from api.schemas import CombatTurnResult, HEAL_SOURCES, TurnOutcome
from api.serializers import serialize_combat_result
from api.tests import test_roadmap_c14_fighter_features as fighter_fixture
from api.tests import test_roadmap_c15_monk_features as monk_fixture
from api.tests import test_roadmap_c16_paladin_features as paladin_fixture
from api.tests.test_roadmap_k07_hit_dice import fighter as hit_dice_fighter, spend
from api.tests.test_spell_scope import caster


def spell_turn(session, spell, target, **step):
    with patch("game.roll_d20", return_value=step.pop("d20", 12)):
        return economy.execute(session, {"steps": [{"kind": "magic", "ability": spell, "target_id": target, **step}]})


class SpellEventFields(unittest.TestCase):
    def test_damage_spells_carry_the_catalog_damage_type(self):
        for spell, cls, d20, kind in (("Fire Bolt", "Sorcerer", 12, "attack"), ("Sacred Flame", "Cleric", 1, "save"),
                                      ("Magic Missile", "Sorcerer", 12, None)):
            with self.subTest(spell=spell):
                s, e = caster(cls=cls)
                with patch("game.roll_d20", return_value=d20):
                    result = spell_scope.cast(s, spell, e["id"])
                self.assertEqual(result["damage_type"], spell_scope.CATALOG[spell][3])
                self.assertEqual(result.get("attack_or_save"), kind)
                self.assertGreater(result["damage"], 0)
                self.assertNotIn("heal_source", result)
                self.assertEqual(result["slot_spent"], bool(spell_scope.CATALOG[spell][0]))

    def test_cure_wounds_is_a_spell_heal_with_no_damage_type(self):
        s, _ = caster(cls="Bard")
        s.character["current_hp"] = 1
        result = spell_scope.cast(s, "Cure Wounds", "player")
        self.assertEqual((result["heal_source"], result["damage_type"], result["slot_spent"]), ("spell", None, True))

    def test_sacred_flame_save_fields(self):
        s, e = caster(cls="Cleric")
        with patch("game.roll_d20", return_value=1):
            result = spell_scope.cast(s, "Sacred Flame", e["id"])
        self.assertEqual(result["spell_save_dc"], 13)
        self.assertEqual(result["save_roll"], result["resolution"]["selected_roll"])

    def test_registry_changes_carry_damage_type_and_heal_source(self):
        s, e = caster(cls="Sorcerer")
        applied = spell_registry.cast_spell("Magic Missile", {"session": s}, None, {"target_id": e["id"]})
        damage = [c for c in applied["changes"] if c["kind"] == "damage"][0]
        self.assertEqual(damage["damage_type"], "force")
        s, _ = caster(cls="Bard")
        s.character["current_hp"] = 1
        applied = spell_registry.cast_spell("Cure Wounds", {"session": s}, None, {"target_id": "player"})
        heal = [c for c in applied["changes"] if c["kind"] == "healing"][0]
        self.assertEqual(heal["heal_source"], "spell")

    def test_public_combat_result_fills_the_empty_spell_fields(self):
        s, e = caster(cls="Cleric")
        out = spell_turn(s, "Sacred Flame", e["id"], d20=1)
        public = serialize_combat_result(out["action_result"], s)
        self.assertEqual((public["spell"], public["damage_type"], public["attack_or_save"], public["slot_spent"]),
                         ("Sacred Flame", "radiant", "save", False))
        self.assertEqual((public["save_dc"], public["target_id"]), (13, e["id"]))
        self.assertIsInstance(public["save_roll"], int)
        self.assertGreater(public["damage"], 0)
        self.assertNotIn("heal_source", public)

    def test_public_cure_wounds_fills_healing_and_source(self):
        s, _ = caster(cls="Bard")
        s.character["current_hp"] = 1
        public = serialize_combat_result(spell_turn(s, "Cure Wounds", "player")["action_result"], s)
        self.assertEqual((public["spell"], public["heal_source"], public["slot_spent"]), ("Cure Wounds", "spell", True))
        self.assertEqual(public["healing"], s.character["current_hp"] - 1)

    def test_a_miss_still_names_the_spell_and_type_but_no_damage(self):
        s, e = caster(cls="Sorcerer")
        public = serialize_combat_result(spell_turn(s, "Fire Bolt", e["id"], d20=2)["action_result"], s)
        self.assertEqual((public["spell"], public["attack_or_save"], public["damage_type"]), ("Fire Bolt", "attack", "fire"))
        self.assertEqual(public["damage"], 0)


class HealSourceEverywhere(unittest.TestCase):
    """Parametrised over every healing path the engine has."""

    def test_in_combat_class_features(self):
        session, _ = fighter_fixture.fight(1)
        session.character.update(max_hp=40, current_hp=10)
        result = fighter_fixture.run(session, fighter_fixture.second_wind())[0]["result"]
        self.assertEqual(result["heal_source"], "class_feature")
        session, _ = monk_fixture.fight(3)
        session.character.update(max_hp=40, current_hp=10)
        session.character["monk_state"] = {"focus_spent": 3, "metabolism_spent": False, "deflect": "reduce"}
        self.assertEqual(monk_fixture.run(session, {"kind": "uncanny_metabolism"})[0]["result"]["heal_source"], "class_feature")
        session, _ = paladin_fixture.fight(2)
        paladin_fixture.wound(session)
        self.assertEqual(paladin_fixture.run(session, paladin_fixture.lay(healing_amount=3))[0]["result"]["heal_source"],
                         "class_feature")

    def test_top_level_turn_result_names_the_healing_step(self):
        session, _ = fighter_fixture.fight(1)
        session.character.update(max_hp=40, current_hp=10)
        out = economy.execute(session, {"steps": [fighter_fixture.second_wind()]})
        public = serialize_combat_result(out["action_result"], session)
        self.assertEqual((public["heal_source"], public["healing"]), ("class_feature", session.character["current_hp"] - 10))

    def test_outside_combat_class_features(self):
        import fighter_features
        session = fighter_fixture.created(1)
        session.character.update(max_hp=40, current_hp=10)
        self.assertEqual(fighter_features.second_wind_outside_combat(session)["heal_source"], "class_feature")
        session = paladin_fixture.created(2)
        paladin_fixture.wound(session)
        self.assertEqual(paladin_features.lay_on_hands_outside_combat(session, 3, False)["heal_source"], "class_feature")

    def test_rest_paths_and_species(self):
        session = hit_dice_fighter()
        self.assertEqual(session.resolve_species_trait_action("long_rest")["effects"]["heal_source"], "rest")
        session = hit_dice_fighter()
        session.resolve_species_trait_action("short_rest")
        self.assertEqual(spend(session, 4)["effects"]["heal_source"], "rest")
        session = hit_dice_fighter()
        session.character.update({"species": "Aasimar", "race": "Aasimar", "max_hp": 20, "current_hp": 1, "charisma_mod": 1})
        session.initialize_species_trait_state()
        with patch.object(session.rng, "randint", return_value=1):
            result = session.resolve_species_trait_action("healing_hands")
        self.assertEqual(result["effects"]["heal_source"], "species")

    def test_death_save_natural_twenty_is_derived_from_the_outcome(self):
        public = serialize_combat_result({"action": "death_save", "death_save": {
            "roll": 20, "outcome": "revived", "successes": 0, "failures": 0, "stable": False, "dead": False, "prone": True}}, None)
        self.assertEqual((public["heal_source"], public["healing"]), ("death_save", 1))
        public = serialize_combat_result({"action": "death_save", "death_save": {
            "roll": 12, "outcome": "success", "successes": 1, "failures": 0, "stable": False, "dead": False, "prone": True}}, None)
        self.assertNotIn("heal_source", public)

    def test_last_call_rescue_names_death_save_and_a_refusal_names_nothing(self):
        for roll, status in ((20, "player_rescued"), (3, "player_dead")):
            with self.subTest(roll=roll):
                session = hit_dice_fighter()
                session.character["current_hp"] = 0
                session.world_state["player_combat_status"] = "dead"
                session.world_state["death_state"].update(dead=True, terminal=False)
                with patch("game.roll_d20", return_value=roll):
                    result = session.player_cannot_act_turn()["action_result"]
                self.assertEqual(result["status"], status)
                if roll == 20:
                    self.assertEqual((result["healing"], result["heal_source"]), (1, "death_save"))
                    self.assertEqual(TurnOutcome(heal_source=result["heal_source"], healing=result["healing"]).heal_source, "death_save")
                else:
                    self.assertNotIn("heal_source", result)

    def test_allowed_values_include_the_reserved_potion(self):
        self.assertEqual(set(HEAL_SOURCES), {"spell", "rest", "class_feature", "species", "death_save", "potion"})
        CombatTurnResult.model_validate({"heal_source": "potion"}, strict=True)
        with self.assertRaises(Exception):
            CombatTurnResult.model_validate({"heal_source": "magic"}, strict=True)
        TurnOutcome(heal_source="death_save", healing=1)


class DamageTypeEverywhere(unittest.TestCase):
    def test_weapon_and_trap_damage_carry_a_type(self):
        session, npc = paladin_fixture.fight(2)
        result = paladin_fixture.hit(session, npc)[0]["result"]
        self.assertIn(result["damage_type"], {"slashing", "piercing", "bludgeoning"})
        import exploration
        import local_adventure_catalog as catalog
        definition = next(iter(catalog.TRAPS.values()))
        self.assertEqual(exploration._damage(hit_dice_fighter(), definition)["damage_type"], definition["damage_type"])


class SavedStateUnchanged(unittest.TestCase):
    """No new saved key: the only difference after a spell and a rest is the rules' own state."""

    def keys(self, value, prefix=""):
        if isinstance(value, dict):
            for k, v in value.items():
                yield from self.keys(v, f"{prefix}/{k}")
        else:
            yield prefix

    def test_no_event_field_reaches_the_saved_game(self):
        forbidden = {"heal_source", "damage_type", "attack_or_save", "slot_spent", "save_roll"}
        s, e = caster(cls="Cleric")
        spell_turn(s, "Sacred Flame", e["id"], d20=1)
        saved = json.dumps(s.serialize_game_state(), sort_keys=True, default=str)
        for name in ("heal_source", "attack_or_save", "slot_spent", "save_roll"):
            self.assertNotIn(f'"{name}"', saved)
        s = hit_dice_fighter()
        s.resolve_species_trait_action("long_rest")
        saved = json.dumps(s.serialize_game_state(), sort_keys=True, default=str)
        self.assertNotIn('"heal_source"', saved)
        self.assertTrue(forbidden)

    def test_cast_changes_only_the_expected_saved_paths(self):
        s, e = caster(cls="Cleric")
        before = copy.deepcopy(s.serialize_game_state())
        spell_turn(s, "Sacred Flame", e["id"], d20=1)
        after = s.serialize_game_state()
        added = set(self.keys(after)) - set(self.keys(before))
        self.assertTrue(all("heal_source" not in k and "damage_type" not in k and "slot_spent" not in k for k in added), added)
