"""Missing cross-owner contracts only; production mechanics are never replaced."""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import action_economy as economy
import campaign_time
import game
import monster_combat
import spell_scope
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as campaigns
from api.tests import test_campaign_time as clocks
from api.tests import test_death_system as death
from api.tests import test_monster_combat as monsters
from api.tests import test_spell_scope as spells


class CombatMatrixEngineTests(unittest.TestCase):
    def test_spell_lethal_damage_preserves_surviving_opponent_and_cursor(self):
        s, victim = spells.caster(clocks.scene())
        s.world_state["monster_perception"] = {victim["id"]: {"player": {"visible": True}}}
        survivor = monsters.add_creature(s, victim)
        victim["current_hp"] = 1
        s.ensure_combat_state()
        combat_id = s.world_state["combat"]["combat_id"]
        before_time = s.world_state["campaign_time"]["elapsed_seconds"]
        with patch("game.apply_npc_damage", wraps=game.apply_npc_damage) as damage:
            result = economy.execute(s, {"steps": [
                {"kind": "magic", "ability": "Magic Missile", "target_id": victim["id"]},
            ]})
        self.assertEqual(damage.call_count, 1)
        self.assertGreater(result["action_economy_result"]["steps"][0]["result"]["damage"], 0)
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(victim["combat_status"], "dead")
        self.assertNotIn("death_state", victim)
        combat = s.world_state["combat"]
        self.assertTrue(combat["active"])
        self.assertEqual(combat["combat_id"], combat_id)
        self.assertEqual(combat["current_actor_id"], "player")
        self.assertIn(survivor["id"], combat["initiative_order"])
        self.assertFalse(economy.can_act(s, victim["id"]))
        self.assertTrue(economy.ensure(s)["player"]["base_action_spent"])
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], 1)
        self.assertEqual(s.world_state["campaign_time"]["elapsed_seconds"], before_time)
        s.advance_combat_turn()
        self.assertEqual(s.world_state["combat"]["current_actor_id"], survivor["id"])

    def test_native_monster_damage_keeps_player_slot_and_schedules_death_save(self):
        s, enemy = monsters.fixture()
        s.character.update(current_hp=5, max_hp=20, armor_class=10)
        s.ensure_death_state()["mode"] = "PERMADEATH"
        monsters.activate(s, enemy)
        with patch("game.roll_d20", return_value=12), patch.object(
            s.rng, "randint", return_value=4
        ), patch("game._apply_attack_damage_to_player", wraps=game._apply_attack_damage_to_player) as owner:
            result = monster_combat.run_turn(s, enemy["id"])
        self.assertEqual(owner.call_count, 1)
        self.assertEqual(result["outcomes"][0]["hp_damage"], 6)
        self.assertEqual(s.character["current_hp"], 0)
        self.assertEqual(s.world_state["player_combat_status"], "unconscious")
        self.assertIn("player", s.world_state["combat"]["initiative_order"])
        with patch("game.roll_d20", return_value=12) as saving_die:
            s.advance_combat_turn()
            self.assertEqual(s.world_state["combat"]["current_actor_id"], "player")
            game._resolve_player_death_turn(session=s)
        self.assertEqual(saving_die.call_count, 1)
        self.assertEqual(s.ensure_death_state()["successes"], 1)
        self.assertEqual(s.ensure_death_state()["failures"], 0)

    def test_multiattack_stops_after_first_component_kills_npc(self):
        multi = {"capability_id": "multi", "kind": "multiattack", "action_source": "action",
                 "attack_slots": [["claw"], ["claw"], ["claw"]]}
        s, enemy = monsters.fixture([monsters.claw(), multi])
        victim = monsters.add_creature(s, enemy, current_hp=1)
        s.world_state["monster_perception"][enemy["id"]]["player"]["visible"] = False
        s.character["hidden"] = True
        monsters.activate(s, enemy)
        with patch("game.roll_d20", return_value=12), patch.object(
            s.rng, "randint", return_value=4
        ), patch("game.apply_npc_damage", wraps=game.apply_npc_damage) as damage:
            result = monster_combat.run_turn(s, enemy["id"])
        self.assertEqual(result["decisions"][0]["attack_sequence"], ["claw"] * 3)
        self.assertEqual(result["decisions"][0]["target_ids"], [victim["id"]])
        self.assertEqual(len(result["outcomes"]), 1)
        self.assertEqual(damage.call_count, 1)
        self.assertEqual(victim["combat_status"], "dead")
        self.assertNotIn("death_state", victim)
        self.assertTrue(economy.ensure(s)[enemy["id"]]["base_action_spent"])
        before = s.serialize_game_state(), s.rng.getstate()
        replay = monster_combat.run_turn(s, enemy["id"], expected_turn_id=result["turn_id"])
        self.assertEqual(replay, result)
        self.assertEqual((s.serialize_game_state(), s.rng.getstate()), before)

    def test_sequential_death_counters_reach_stable_or_dead_through_owner(self):
        for roll, field, terminal in ((10, "successes", "stable"), (9, "failures", "dead")):
            with self.subTest(terminal=terminal):
                s = death.make_session()
                campaign_time.initialize(s.world_state)
                s.ensure_death_state()["mode"] = "PERMADEATH"
                s._apply_player_damage(s.character["current_hp"], took_damage=True)
                with patch("game.roll_d20", return_value=roll) as d20:
                    for count in (1, 2, 3):
                        game._resolve_player_death_turn(session=s, noncombat_key=f"ctm-{terminal}-{count}")
                        # Becoming Stable clears both counters through the Death owner.
                        self.assertEqual(s.ensure_death_state()[field], 0 if terminal == "stable" and count == 3 else count)
                        self.assertEqual(s.ensure_death_state()["failures" if field == "successes" else "successes"], 0)
                        self.assertEqual(s.ensure_death_state()[terminal], count == 3)
                self.assertEqual(d20.call_count, 3)
                self.assertEqual(s.character["current_hp"], 0)
                self.assertTrue(s.ensure_death_state()["prone"])

    def test_long_rest_reaches_spell_resource_hook_and_authoritative_clock(self):
        s, enemy = spells.caster()
        campaign_time.initialize(s.world_state)
        spell_scope.cast(s, "Magic Missile", enemy["id"])
        marker = copy.deepcopy(s.world_state["spellcasting_v1"]["slot_turn"])
        s.end_combat("test_rest_boundary")
        before_time = s.world_state["campaign_time"]["elapsed_seconds"]
        s.resolve_species_trait_action("long_rest")
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], 2)
        self.assertEqual(s.world_state["spellcasting_v1"]["slot_turn"], marker)
        self.assertEqual(s.world_state["campaign_time"]["elapsed_seconds"] - before_time, 8 * 3600)
        game._validate_save_payload(s.serialize_game_state())


class CombatMatrixApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown
    create_campaign = campaigns.CampaignApiTests.create_campaign

    async def test_stable_resume_preserves_spent_spell_action_and_recovery_episode(self):
        a = await self.create_campaign()
        s, enemy = spells.caster(self.manager.get(a["session_id"]).game_session)
        campaign_time.initialize(s.world_state)
        economy.execute(s, {"steps": [
            {"kind": "magic", "ability": "Magic Missile", "target_id": enemy["id"]},
        ]})
        s._apply_player_damage(s.character["current_hp"], took_damage=True)
        with patch.object(s.rng, "randint", return_value=2) as recovery_die:
            s.stabilize_player()
        self.assertEqual(recovery_die.call_count, 1)
        s.ensure_combat_state()
        snapshot = s.serialize_game_state()
        rng = s.rng.getstate()
        self.manager.save_campaign(a["campaign_id"])
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path))
        _, record, *_ = fresh.resume_campaign(a["campaign_id"])
        resumed = record.game_session
        self.assertEqual(resumed.rng.getstate(), rng)
        for key in ("combat", "spellcasting_v1", "death_state", "campaign_time"):
            self.assertEqual(resumed.world_state[key], snapshot["world_state"][key])
        self.assertTrue(economy.ensure(resumed)["player"]["base_action_spent"])
        self.assertEqual(resumed.world_state["spellcasting_v1"]["slots"]["1"], 1)
        with patch.object(resumed.rng, "randint", side_effect=AssertionError("recovery rerolled")):
            resumed.advance_campaign_time(7199, "wait")
            self.assertEqual(resumed.character["current_hp"], 0)
            resumed.advance_campaign_time(1, "wait")
            self.assertEqual(resumed.character["current_hp"], 1)
            resumed.advance_campaign_time(3600, "wait")
        self.assertTrue(resumed.ensure_death_state()["prone"])
        self.assertEqual(resumed.rng.getstate(), rng)

    async def test_spell_autosave_failure_restores_damage_healing_slots_rng_and_receipt(self):
        for cls, name in (("Sorcerer", "Magic Missile"), ("Bard", "Cure Wounds")):
            with self.subTest(spell=name):
                a, b = await self.create_campaign(), await self.create_campaign()
                record = self.manager.get(a["session_id"])
                s, enemy = spells.caster(record.game_session, cls)
                other = self.manager.get(b["session_id"]).game_session
                if name == "Cure Wounds":
                    s.character["current_hp"] = 1
                s.ensure_combat_state()
                command = {"message": "Resolve the selected spell.", "action_id": str(uuid4()),
                           "combat_action": {"steps": [{"kind": "magic", "ability": name,
                               "target_id": "player" if name == "Cure Wounds" else enemy["id"]}]}}
                self.app.state.ollama_adapter = None
                url = f"/api/game/sessions/{a['session_id']}/turn"
                before = s.serialize_game_state(), s.rng.getstate(), self.store.get_campaign(a["campaign_id"])
                isolated = other.serialize_game_state(), other.rng.getstate(), self.store.get_campaign(b["campaign_id"])
                owner_name = "game.heal_player" if name == "Cure Wounds" else "game.apply_npc_damage"
                owner = game.heal_player if name == "Cure Wounds" else game.apply_npc_damage
                with patch(owner_name, wraps=owner) as handoff, patch.object(
                    s.rng, "randint", wraps=s.rng.randint
                ) as dice, patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("matrix failure")):
                    failed = await self.http.post(url, json=command)
                self.assertEqual(failed.status_code, 503, failed.text)
                self.assertEqual(handoff.call_count, 1)
                self.assertEqual(dice.call_count, 2 if name == "Cure Wounds" else 3)
                self.assertEqual((s.serialize_game_state(), s.rng.getstate(), self.store.get_campaign(a["campaign_id"])), before)
                self.assertIsNone(self.manager.get_turn_action(record, command["action_id"]))
                self.assertEqual((other.serialize_game_state(), other.rng.getstate(), self.store.get_campaign(b["campaign_id"])), isolated)
                successful = await self.http.post(url, json=command)
                self.assertEqual(successful.status_code, 200, successful.text)
                self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], 1)
                committed = s.serialize_game_state(), s.rng.getstate(), self.store.get_campaign(a["campaign_id"])
                replay = await self.http.post(url, json=command)
                self.assertEqual(replay.json(), successful.json())
                self.assertEqual((s.serialize_game_state(), s.rng.getstate(), self.store.get_campaign(a["campaign_id"])), committed)