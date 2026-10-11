"""Tier 1 XP: Python owns the total, the level, and the hit-point gain."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import game
import quest_catalog
import xp


def _character(session, class_name="Fighter", *, constitution=14, race="Human", **extra):
    modifier = (constitution - 10) // 2
    session.character.update(
        name="Ari",
        race=race,
        **{"class": class_name},
        strength=16,
        dexterity=14,
        constitution=constitution,
        intelligence=10,
        wisdom=12,
        charisma=10,
        proficient_skills=["Athletics"],
        level=1,
        proficiency_bonus=2,
        max_hp=12,
        current_hp=5,
        armor_class=16,
        strength_mod=3,
        dexterity_mod=2,
        constitution_mod=modifier,
        intelligence_mod=0,
        wisdom_mod=1,
        charisma_mod=0,
        cantrips=[],
        spells=["Magic Missile"] if class_name == "Wizard" else [],
        spell_slots_remaining={"1": 2},
        spell_save_dc=13,
        spell_attack_bonus=5,
        xp=0,
    )
    session.character.update(extra)
    session.world_state["location"] = "tavern"
    session.world_state["xp_awarded_event_ids"] = []
    session.world_state["flags"]["turn_index"] = 3


def _enemy(session, reward=300, hp=8):
    npc = {
        "id": "npc_test",
        "name": "Sentinel",
        "role": "guard",
        "location": "tavern",
        "max_hp": hp,
        "current_hp": hp,
        "armor_class": 10,
        "combat_status": "active",
        "dexterity_mod": 0,
        "hostile": True,
    }
    if reward is not None:
        npc["xp_reward"] = reward
    session.world_state["npcs"] = [npc]
    return npc


def _defeat(session):
    session.start_combat(session.world_state["npcs"][0])
    npc = session.world_state["npcs"][0]
    npc["current_hp"] = 0
    npc["combat_status"] = "unconscious"
    session.ensure_combat_state()
    return session._combat_end_if_decided()


class ExperienceRuleTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=6)
        _character(self.session)

    def test_thresholds_fixed_hit_points_and_the_level_four_cap(self):
        character = self.session.character
        self.assertEqual(xp.level_for_xp(299), 1)
        below = xp.apply_xp(character, self.session.world_state, 299, "quest:below")
        self.assertEqual(character["level"], 1)
        self.assertEqual(character["xp"], 299)
        self.assertEqual(below["hit_points_gained"], 0)
        self.assertEqual(character["max_hp"], 12)
        self.assertEqual(character["current_hp"], 5)

        reached = xp.apply_xp(character, self.session.world_state, 1, "quest:exact-2")
        self.assertEqual(character["xp"], 300)
        self.assertEqual(character["level"], 2)
        self.assertEqual(reached["hit_points_gained"], 8)
        self.assertEqual(character["max_hp"], 20)
        self.assertEqual(character["current_hp"], 13)

        character["xp"] = 899
        character["level"] = 2
        self.assertIsNotNone(
            xp.apply_xp(character, self.session.world_state, 1, "quest:exact-3")
        )
        self.assertEqual(character["level"], 3)
        self.assertEqual(character["xp"], 900)

        character["xp"] = 2699
        character["level"] = 3
        self.assertIsNotNone(
            xp.apply_xp(character, self.session.world_state, 1, "quest:exact-4")
        )
        self.assertEqual(character["level"], 4)
        self.assertEqual(character["xp"], 2700)
        self.assertEqual(character["proficiency_bonus"], 2)

        fresh = game.create_session(seed=6)
        _character(fresh)
        crossed = xp.apply_xp(fresh.character, fresh.world_state, 900, "quest:two-levels")
        self.assertEqual(fresh.character["level"], 3)
        self.assertEqual(crossed["previous_level"], 1)
        self.assertEqual(crossed["new_level"], 3)
        self.assertEqual(crossed["hit_points_gained"], 16)
        self.assertEqual(fresh.character["max_hp"], 28)

        capped = game.create_session(seed=6)
        _character(capped)
        overflow = xp.apply_xp(capped.character, capped.world_state, 10000, "quest:overflow")
        self.assertEqual(capped.character["level"], 4)
        self.assertEqual(capped.character["xp"], 10000)
        self.assertEqual(capped.character["proficiency_bonus"], 2)
        self.assertEqual(overflow["hit_points_gained"], 24)
        self.assertEqual(capped.character["spell_slots_remaining"], {"1": 2})
        self.assertEqual(capped.character["spells"], [])
        self.assertEqual(capped.character["spell_attack_bonus"], 5)

    def test_negative_constitution_dwarf_and_tough_use_the_fixed_table(self):
        wizard = self.session.character
        wizard["class"] = "Wizard"
        wizard["constitution"] = 8
        wizard["constitution_mod"] = 99
        self.assertEqual(xp.hit_point_gain(wizard), 3)
        wizard["constitution"] = 1
        self.assertEqual(xp.hit_point_gain(wizard), 1)

        wizard["constitution"] = 10
        wizard["race"] = "Dwarf"
        self.assertEqual(xp.hit_point_gain(wizard), 5)
        wizard["species"] = "Human"
        wizard["race"] = "Human"
        wizard["origin_feat"] = "Tough"
        self.assertEqual(xp.hit_point_gain(wizard), 6)
        wizard["species"] = "Dwarf"
        self.assertEqual(xp.hit_point_gain(wizard), 7)

        granted = xp.apply_xp(wizard, self.session.world_state, 300, "quest:tough-dwarf")
        self.assertEqual(granted["hit_points_gained"], 7)
        self.assertEqual(wizard["level"], 2)
        self.assertEqual(wizard["spell_slots_remaining"], {"1": 2})
        self.assertEqual(wizard["spells"], [])

    def test_level_one_hit_points_are_not_recalculated(self):
        before = self.session.character["max_hp"]
        xp.apply_xp(self.session.character, self.session.world_state, 300, "quest:keep-base")
        self.assertEqual(self.session.character["max_hp"], before + 8)


class ExperienceAwardTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=6)
        _character(self.session)

    def test_combat_pays_only_a_server_reward_for_target_defeated_once(self):
        _enemy(self.session, 300)
        ended = _defeat(self.session)
        self.assertEqual(ended["reason"], "target_defeated")
        self.assertEqual(self.session.character["xp"], 300)
        self.assertEqual(self.session.character["level"], 2)
        self.assertEqual(
            self.session.world_state["xp_awarded_event_ids"],
            ["combat:3:npc_test"],
        )
        published = {}
        self.session._publish_level_up(published)
        self.assertEqual(published["level_up"]["previous_level"], 1)
        self.assertEqual(published["level_up"]["new_level"], 2)
        self.assertEqual(published["level_up"]["xp_gained"], 300)
        self.assertEqual(published["level_up"]["hit_points_gained"], 8)

        self.session.end_combat("target_defeated")
        self.assertEqual(self.session.character["xp"], 300)

        self.session._xp_level_up = None
        npc = self.session.world_state["npcs"][0]
        npc["current_hp"] = 8
        npc["combat_status"] = "active"
        self.session.world_state["flags"]["turn_index"] = 4
        _defeat(self.session)
        self.assertEqual(self.session.character["xp"], 600)
        self.assertEqual(self.session.character["level"], 2)

    def test_leaving_or_falling_unconscious_pays_nothing(self):
        _enemy(self.session, 300)
        self.session.start_combat(self.session.world_state["npcs"][0])
        npc = self.session.world_state["npcs"][0]
        npc["current_hp"] = 0
        npc["combat_status"] = "unconscious"
        self.session.end_combat("location_changed")
        self.assertEqual(self.session.character["xp"], 0)
        self.assertEqual(self.session.world_state["xp_awarded_event_ids"], [])

        npc["current_hp"] = 8
        npc["combat_status"] = "active"
        self.session.start_combat(npc)
        self.session.character["current_hp"] = 0
        self.session.world_state["player_combat_status"] = "unconscious"
        ended = self.session._combat_end_if_decided()
        self.assertIsNone(ended)
        self.assertTrue(self.session.world_state["combat"]["active"])
        self.assertNotEqual(
            self.session.world_state["combat"].get("end_reason"),
            "player_defeated",
        )
        self.assertEqual(self.session.character["xp"], 0)

    def test_a_creature_without_a_server_reward_pays_nothing(self):
        _enemy(self.session, None)
        _defeat(self.session)
        self.assertEqual(self.session.character["xp"], 0)
        self.assertFalse(hasattr(self.session, "_xp_level_up") and self.session._xp_level_up)
        untouched = {"action": "attack"}
        self.session._publish_level_up(untouched)
        self.assertNotIn("level_up", untouched)

    def test_quest_xp_is_paid_once_and_narration_is_not_a_source(self):
        self.assertEqual(quest_catalog.CATALOG, ())
        definition = {
            "quest_id": "quest.xp",
            "title": "Road",
            "description": "Walk to the forest.",
            "objectives": [{
                "objective_id": "visit",
                "description": "Visit the forest",
                "type": "visit_location",
                "target": "forest",
            }],
            "xp": 300,
        }
        with patch.object(quest_catalog, "CATALOG", (definition,)):
            self.session.accept_quest("quest.xp")
            before = copy.deepcopy(self.session.world_state)
            self.assertEqual(
                self.session.evaluate_quest_events(
                    before,
                    {"narration": "You gain 500 XP and the quest is complete."},
                ),
                [],
            )
            self.assertEqual(self.session.character["xp"], 0)

            before = copy.deepcopy(self.session.world_state)
            self.session.world_state["location"] = "forest"
            outcomes = self.session.evaluate_quest_events(before, {"action": "travel"})
            self.assertEqual(outcomes[-1]["transition"], "completed")
            self.assertEqual(self.session.character["xp"], 300)
            self.assertEqual(self.session.character["level"], 2)

            again = self.session.evaluate_quest_events(
                copy.deepcopy(self.session.world_state),
                {"action": "travel"},
            )
            self.assertEqual(again, [])
            self.assertEqual(self.session.character["xp"], 300)

        no_reward = game.create_session(seed=6)
        _character(no_reward)
        plain = {
            "quest_id": "quest.plain",
            "title": "Road",
            "description": "Walk to the forest.",
            "objectives": [{
                "objective_id": "visit",
                "description": "Visit the forest",
                "type": "visit_location",
                "target": "forest",
            }],
        }
        with patch.object(quest_catalog, "CATALOG", (plain,)):
            no_reward.accept_quest("quest.plain")
            before = copy.deepcopy(no_reward.world_state)
            no_reward.world_state["location"] = "forest"
            no_reward.evaluate_quest_events(before, {"action": "travel"})
        self.assertEqual(no_reward.character["xp"], 0)
        with self.assertRaises(ValueError):
            quest_catalog.validate_catalog(({**plain, "xp": "300"},))

    def test_the_model_cannot_attach_a_creature_reward(self):
        self.session.world_state["location"] = "tavern"
        npc = self.session.create_npc_from_ai({
            "name": "Darian",
            "role": "Yolcu",
            "location": "tavern",
            "personality": "Kibar.",
            "appearance": "Sade bir pelerin giymiş.",
            "relationship": "neutral",
            "xp_reward": 2700,
        })
        self.assertIsNotNone(npc)
        self.assertNotIn("xp_reward", npc)

    def test_rollback_allows_the_same_event_to_pay_again(self):
        character = copy.deepcopy(self.session.character)
        world = copy.deepcopy(self.session.world_state)
        xp.apply_xp(self.session.character, self.session.world_state, 300, "quest:once")
        self.assertEqual(self.session.character["xp"], 300)
        self.session.character.clear()
        self.session.character.update(character)
        self.session.world_state.clear()
        self.session.world_state.update(world)
        self.assertIsNotNone(
            xp.apply_xp(self.session.character, self.session.world_state, 300, "quest:once")
        )
        self.assertIsNone(
            xp.apply_xp(self.session.character, self.session.world_state, 300, "quest:once")
        )
        self.assertEqual(self.session.character["xp"], 300)

    def test_save_load_migration_restart_and_session_isolation(self):
        _enemy(self.session, 300)
        _defeat(self.session)
        self.session.character["species"] = "Dwarf"
        self.session.character["origin_feat"] = "Tough"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "xp.json"
            self.session.save_game(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 4)
            self.assertEqual(payload["player"]["xp"], 300)
            self.assertEqual(payload["player"]["level"], 2)
            self.assertEqual(payload["player"]["cantrips"], [])
            self.assertEqual(payload["player"]["spell_slots_remaining"], {"1": 2})
            self.assertEqual(payload["player"]["origin_feat"], "Tough")
            self.session.character["xp"] = 0
            self.session.character["level"] = 1
            self.session.load_game(path)
            self.assertEqual(self.session.character["xp"], 300)
            self.assertEqual(self.session.character["level"], 2)
            self.assertEqual(self.session.character["species"], "Dwarf")
            self.assertEqual(self.session.character["origin_feat"], "Tough")
            self.assertIsNone(
                xp.apply_xp(
                    self.session.character,
                    self.session.world_state,
                    300,
                    "combat:3:npc_test",
                )
            )

            restarted = game.create_session(seed=8)
            restarted.load_game(path)
            self.assertEqual(restarted.character["xp"], 300)
            self.assertEqual(restarted.character["level"], 2)
            self.assertEqual(self.session.character["current_hp"], restarted.character["current_hp"])

            other = game.create_session(seed=9)
            _character(other)
            self.assertEqual(other.character["xp"], 0)
            self.assertEqual(other.world_state["xp_awarded_event_ids"], [])

            saved_level = payload["player"]["level"]
            saved_hp = payload["player"]["max_hp"]
            saved_current = payload["player"]["current_hp"]
            for version in (1, 2, 3, 4):
                legacy = copy.deepcopy(payload)
                legacy["version"] = version
                legacy["player"].pop("xp")
                legacy["player"]["level"] = saved_level
                legacy["player"]["max_hp"] = saved_hp
                legacy["player"]["current_hp"] = saved_current
                legacy["world_state"].pop("xp_awarded_event_ids")
                if version < 4:
                    legacy["player"].pop("cantrips")
                    legacy["player"].pop("spells")
                    legacy["player"].pop("spell_slots_remaining")
                path.write_text(json.dumps(legacy), encoding="utf-8")
                self.session.load_game(path)
                self.assertEqual(self.session.character["xp"], 0)
                self.assertEqual(self.session.character["level"], saved_level)
                self.assertEqual(self.session.character["max_hp"], saved_hp)
                self.assertEqual(self.session.character["current_hp"], saved_current)
                self.assertEqual(self.session.world_state.get("xp_awarded_event_ids", []), [])

            forged = copy.deepcopy(payload)
            forged["version"] = 4
            forged["player"]["xp"] = 6500
            forged["player"]["level"] = 1
            path.write_text(json.dumps(forged), encoding="utf-8")
            self.session.load_game(path)
            self.assertEqual(self.session.character["xp"], 6500)
            self.assertEqual(self.session.character["level"], 1)
            self.assertEqual(self.session._persisted_engine_format, 4)

            broken = copy.deepcopy(payload)
            broken["version"] = 5
            broken["player"]["xp"] = 0
            broken["player"]["level"] = 4
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.session.load_game(path)
            self.assertEqual(self.session.character["xp"], 6500)
            self.assertEqual(self.session.character["level"], 1)
            broken["version"] = 6
            broken["player"]["xp"] = 300
            broken["player"]["level"] = 2
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.session.load_game(path)

    def test_v3_award_survives_restart_without_a_format_change(self):
        self.session._persisted_engine_format = 3
        _enemy(self.session, 300)
        ended = _defeat(self.session)
        self.assertEqual(ended["reason"], "target_defeated")
        self.assertEqual(self.session.character["xp"], 300)
        self.assertEqual(self.session.character["level"], 2)
        max_hp = self.session.character["max_hp"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v3-xp.json"
            self.session.save_game(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 3)
            self.assertEqual(payload["player"]["xp"], 300)
            self.assertEqual(payload["player"]["level"], 2)
            self.assertEqual(payload["player"]["max_hp"], max_hp)
            self.assertNotIn("spell_slots_remaining", payload["player"])
            self.assertNotIn("origin_feat", payload["player"])
            restarted = game.create_session(seed=11)
            restarted.load_game(path)
        self.assertEqual(restarted.character["xp"], 300)
        self.assertEqual(restarted.character["level"], 2)
        self.assertEqual(restarted.character["max_hp"], max_hp)
        self.assertEqual(
            restarted.world_state["xp_awarded_event_ids"],
            ["combat:3:npc_test"],
        )
        self.assertIsNone(
            xp.apply_xp(
                restarted.character,
                restarted.world_state,
                300,
                "combat:3:npc_test",
            )
        )
        self.assertEqual(self.session.character["xp"], 300)
        self.assertEqual(restarted._persisted_engine_format, 3)
        with tempfile.TemporaryDirectory() as directory:
            again = Path(directory) / "v3-again.json"
            restarted.save_game(again)
            rewritten = json.loads(again.read_text(encoding="utf-8"))
        self.assertEqual(rewritten["version"], 3)
        self.assertEqual(rewritten["player"]["xp"], 300)
        self.assertNotIn("cantrips", rewritten["player"])

    def test_fresh_v4_save_restores_slots_feat_and_advancement(self):
        self.session.character["cantrips"] = ["Fire Bolt"]
        self.session.character["spells"] = ["Magic Missile"]
        self.session.character["spell_slots_remaining"] = {"1": 1}
        self.session.character["origin_feat"] = "Tough"
        _enemy(self.session, 300)
        _defeat(self.session)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fresh-v4.json"
            self.session.save_game(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 4)
            self.assertEqual(payload["player"]["spell_slots_remaining"], {"1": 1})
            self.assertEqual(payload["player"]["origin_feat"], "Tough")
            self.assertEqual(payload["player"]["xp"], 300)
            restarted = game.create_session(seed=12)
            restarted.character["xp"] = 50
            restarted.character["spell_slots_remaining"] = {"1": 9}
            restarted.load_game(path)
        self.assertEqual(restarted._persisted_engine_format, 4)
        self.assertEqual(restarted.character["cantrips"], ["Fire Bolt"])
        self.assertEqual(restarted.character["spells"], ["Magic Missile"])
        self.assertEqual(restarted.character["spell_slots_remaining"], {"1": 1})
        self.assertEqual(restarted.character["origin_feat"], "Tough")
        self.assertEqual(restarted.character["xp"], 300)
        self.assertEqual(restarted.character["level"], 2)
        self.assertEqual(
            restarted.world_state["xp_awarded_event_ids"],
            ["combat:3:npc_test"],
        )

    def test_missing_xp_does_not_keep_another_sessions_total(self):
        self.session._persisted_engine_format = 3
        level = self.session.character["level"]
        max_hp = self.session.character["max_hp"]
        current_hp = self.session.character["current_hp"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "no-xp.json"
            self.session.save_game(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 3)
            payload["player"].pop("xp")
            path.write_text(json.dumps(payload), encoding="utf-8")
            donor = game.create_session(seed=13)
            _character(donor)
            donor.character["xp"] = 777
            other = game.create_session(seed=14)
            _character(other)
            other.character["xp"] = 400
            donor.load_game(path)
            self.assertEqual(donor.character["xp"], 0)
            self.assertEqual(donor.character["level"], level)
            self.assertEqual(donor.character["max_hp"], max_hp)
            self.assertEqual(donor.character["current_hp"], current_hp)
            self.assertEqual(other.character["xp"], 400)

    def test_combat_and_quest_awards_merge_and_roll_back(self):
        snapshot = self.session._capture_runtime_snapshot()
        _enemy(self.session, 300)
        _defeat(self.session)
        definition = {
            "quest_id": "quest.both",
            "title": "Road",
            "description": "Walk to the forest.",
            "objectives": [{
                "objective_id": "visit",
                "description": "Visit the forest",
                "type": "visit_location",
                "target": "forest",
            }],
            "xp": 600,
        }
        with patch.object(quest_catalog, "CATALOG", (definition,)):
            self.session.accept_quest("quest.both")
            before = copy.deepcopy(self.session.world_state)
            self.session.world_state["location"] = "forest"
            self.session.evaluate_quest_events(before, {"action": "travel"})
        self.assertEqual(self.session.character["xp"], 900)
        self.assertEqual(self.session.character["level"], 3)
        self.assertEqual(self.session.character["max_hp"], 28)
        self.assertEqual(self.session.character["current_hp"], 21)
        published = {"action": "attack"}
        self.session._publish_level_up(published)
        self.assertEqual(
            published["level_up"],
            {
                "previous_level": 1,
                "new_level": 3,
                "xp_gained": 900,
                "hit_points_gained": 16,
            },
        )
        self.assertIsNone(self.session._xp_level_up)
        again = {"action": "attack"}
        self.session._publish_level_up(again)
        self.assertNotIn("level_up", again)
        self.assertIsNone(
            xp.apply_xp(
                self.session.character,
                self.session.world_state,
                300,
                "combat:3:npc_test",
            )
        )
        self.assertIsNone(
            xp.apply_xp(
                self.session.character,
                self.session.world_state,
                600,
                "quest:quest.both",
            )
        )
        self.session._restore_runtime_snapshot(snapshot)
        self.assertEqual(self.session.character["xp"], 0)
        self.assertEqual(self.session.character["level"], 1)
        self.assertEqual(self.session.character["max_hp"], 12)
        self.assertEqual(self.session.character["current_hp"], 5)
        self.assertEqual(self.session.world_state["xp_awarded_event_ids"], [])
        self.assertIsNone(self.session._xp_level_up)


if __name__ == "__main__":
    unittest.main()
