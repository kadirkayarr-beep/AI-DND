"""4C.1: every damage event names its damage_type, every healing event its heal_source (event fields only, no saved key)."""
import copy
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
    """No new saved key: a full before/after comparison of the serialized game after a spell and after a rest."""

    def diff(self, before, after, path=""):
        """Every leaf that differs, every added and every removed key, with its path."""
        if isinstance(before, dict) and isinstance(after, dict):
            for key in sorted(set(before) | set(after), key=str):
                if key not in before:
                    yield f"{path}/{key}", "added"
                elif key not in after:
                    yield f"{path}/{key}", "removed"
                else:
                    yield from self.diff(before[key], after[key], f"{path}/{key}")
        elif isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
            for index, (old, new) in enumerate(zip(before, after)):
                yield from self.diff(old, new, f"{path}/{index}")
        elif before != after:
            yield path, "changed"

    def test_a_spell_changes_only_the_rules_own_saved_state(self):
        s, e = caster(cls="Cleric")
        before = copy.deepcopy(s.serialize_game_state())
        spell_turn(s, "Sacred Flame", e["id"], d20=1)
        after = s.serialize_game_state()
        target = next(i for i, n in enumerate(after["world_state"]["npcs"]) if n["id"] == e["id"])
        records = {r["id"]: i for i, r in enumerate(after["world_state"]["combat"]["participant_records"])}
        self.assertEqual(set(self.diff(before, after)), {
            ("/world_state/combat/actions_used", "changed"),
            ("/world_state/combat/turn_resources/player/base_action_spent", "changed"),
            ("/world_state/flags/turn_index", "changed"),
            (f"/world_state/npcs/{target}/current_hp", "changed"),
            (f"/world_state/combat/participant_records/{records['player']}/primary_action_available", "changed"),
            (f"/world_state/combat/participant_records/{records[e['id']]}/current_hp", "changed"),
        })

    def test_a_long_rest_changes_only_the_rules_own_saved_state(self):
        s = hit_dice_fighter()
        before = copy.deepcopy(s.serialize_game_state())
        s.resolve_species_trait_action("long_rest")
        self.assertEqual(set(self.diff(before, s.serialize_game_state())), {
            ("/player/current_hp", "changed"),
            ("/player/hit_dice", "added"),
            ("/world_state/campaign_time/elapsed_seconds", "changed"),
            ("/world_state/last_long_rest_completed_at", "added"),
        })


class ReplayStability(unittest.TestCase):
    """A receipt stored before 4C.1 must replay exactly as stored: the new fields stay absent when they have no value."""

    def test_old_stored_combat_receipt_gains_no_new_key(self):
        stored = {"action": "attack", "status": "resolved", "damage": 3, "damage_type": "slashing", "spell": None,
                  "healing": None, "slot_spent": None}
        replay = CombatTurnResult.model_validate(stored, strict=True).model_dump(mode="json")
        self.assertNotIn("heal_source", replay)
        self.assertEqual({k: v for k, v in replay.items() if k in stored}, stored)
        self.assertNotIn("heal_source", TurnOutcome().model_dump(mode="json"))
        self.assertEqual(CombatTurnResult(heal_source="spell").model_dump(mode="json")["heal_source"], "spell")
