"""Dilim 3, Task 18: the first ten minutes. The opening may show a happening the player can join and a piece of town
talk that the journal keeps as a trail (`duyulan`); a player still idle eight turns in hears one more, once."""
from __future__ import annotations

import tempfile
import types
import uuid
from pathlib import Path
from unittest.mock import patch

import unittest

import ambient_actions
import api.session_manager as session_manager
import quest_log
import town_knowledge
import world_happenings
import world_threads
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.journeys.runner import JourneyCase, ScriptedModel
from api.tests.journeys.schema import Step

START = {"setting_id": "forgotten_realms", "region_pack_id": "fr:pack:the_north:neverwinter:v1",
         "region_id": "fr:region:the_north", "starting_location_id": "fr:city:neverwinter"}
NUDGE = "konuşmasından bir söz"
LOOK = "etrafıma bakıyorum"
FIGHTER = {"mode": "custom", "starting_level": 1, "name": "Kadir", "race": "Human", "species": "Human",
           "class": "Fighter", "background": "Soldier", "alignment": "Chaotic Neutral",
           "ability_score_method": "standard_array",
           "ability_scores": {"strength": 15, "dexterity": 13, "constitution": 14, "intelligence": 12, "wisdom": 10,
                              "charisma": 8},
           "background_ability_bonuses": {"strength": 2, "constitution": 1},
           "proficient_skills": ["Athletics", "Intimidation", "Perception", "Insight", "Persuasion"],
           "species_bonus_skills": ["Persuasion"], "species_bonus_feat": "Alert", "origin_feat": "Savage Attacker",
           "fighting_style": "Defense", "equipment_package": "C", "background_equipment_option": "B",
           "languages": ["Dwarvish", "Goblin"], "origin": "Beşvel", "appearance": "İri yarı.",
           "personality": "Dobra.", "backstory": "Paralı askerlikten döndü."}


def seeded_ids(seed):
    """The campaign id made from this seed (the campaign seed is drawn from it); every other id stays random."""
    ids = iter([uuid.UUID(f"00000000-0000-4000-8000-{seed:012d}")])
    return patch.object(session_manager, "uuid", types.SimpleNamespace(uuid4=lambda: next(ids, None) or uuid.uuid4()))


def step(say=None, **extra):
    return Step(say=say, command=None, economic_action=None, combat_action=None, script=None, expect={},
                known_broken=(), real_chain=False, independent=False, **extra)


def scene(world):
    return world["scene_state"]["scenes"][world["location"]]


class TheOpening(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.manager = SessionManager(campaign_store=CampaignStore(Path(self.directory.name) / "c.sqlite3",
                                                                   bound_principal=TEST_PLAYER))

    def new_session(self, seed, character=None):
        with seeded_ids(seed):
            return self.manager.create_campaign(character=character, campaign_start=START,
                                                death_mode="NORMAL")[2].game_session

    def new_campaign(self, seed):
        return self.new_session(seed).world_state

    def opening_text(self, world):
        return scene(world)["opening"]["text"]

    def scene_event(self, world):
        return scene(world).get("ambient_event") or {}

    def trail_record_id(self, world, trail):
        return next(row["_to_thread_id"] for row in quest_log._trail_rows(world) if row["id"] == trail["id"])

    def test_the_opening_trail_points_at_a_live_thread(self):
        world = self.new_campaign(seed=1)
        trails = quest_log.trails(world)
        self.assertEqual([t["source"] for t in trails], ["duyulan"])
        thread = world_threads.by_id(world, self.trail_record_id(world, trails[0]))
        self.assertEqual(thread["status"], "heard")
        self.assertIn(f"Kalabalıktan bir söz kulağına çalınıyor: {thread['public_line']}", self.opening_text(world))

    def test_no_thread_no_trail(self):
        with patch("world_threads.street_talk", return_value=None):
            world = self.new_campaign(seed=1)
        self.assertEqual(quest_log.trails(world), [])
        self.assertNotIn("kulağına çalınıyor", self.opening_text(world))

    def test_a_trail_falls_when_its_job_leaves_the_street(self):
        world = self.new_campaign(seed=1)
        thread = world_threads.by_id(world, self.trail_record_id(world, quest_log.trails(world)[0]))
        self.assertTrue(world_threads.transition(thread, "filled_by_other"))
        self.assertEqual(quest_log.trails(world), [])

    def test_a_heard_job_another_trail_points_at_is_listed_once(self):
        world = self.new_campaign(seed=1)
        heard = world_threads.by_id(world, self.trail_record_id(world, quest_log.trails(world)[0]))
        state = world_threads.view(world)
        source = next(t for t in state["threads"] if t is not heard)
        world_happenings.write(state, source, "delivered", heard["opened_at"], "Teslim edildi; duyanlar var.",
                               known=True, next_thread_id=heard["thread_id"])
        self.assertEqual([t["source"] for t in quest_log.trails(world)], ["teslim"])

    def test_a_job_read_off_a_door_is_a_trail_of_its_own(self):
        # Journey 29's seed-dependent third trail: walking up to a place reads the paper of another job there.
        world = self.new_campaign(seed=1)
        [first] = quest_log.trails(world)
        other = next(t for t in world_threads.view(world)["threads"]
                     if t["status"] == "open" and t["type"] != "trouble")
        self.assertTrue(town_knowledge.notice_at(world, other["place_id"]))
        rows = quest_log._trail_rows(world)
        self.assertEqual([row["source"] for row in rows], ["duyulan", "duyulan"])
        self.assertEqual(len({row["_to_thread_id"] for row in rows}), 2)
        self.assertIn(first["id"], [row["id"] for row in rows])

    def test_the_opening_event_is_clickable_when_the_catalog_has_one(self):
        world = self.new_campaign(seed=1)
        self.assertEqual(self.scene_event(world).get("event_type"), "BLUE")  # Neverwinter's street has many
        self.assertEqual(ambient_actions.actionable(world)["can_interact"],
                         self.scene_event(world).get("event_type") == "BLUE")
        self.assertEqual(scene(world)["opening"]["event_id"], self.scene_event(world)["event_id"])

    def test_three_seeds_three_openings(self):
        texts = {self.opening_text(self.new_campaign(seed=s)) for s in (1, 2, 3)}
        self.assertEqual(len(texts), 3)

    def test_the_nudge_is_written_at_the_opening(self):
        self.assertEqual(self.new_campaign(seed=1)["flags"]["opening_nudge"], {"due_turn": 8, "done": False})

    def test_creating_a_campaign_leaves_the_purse_alone(self):
        self.assertEqual(self.new_session(1, FIGHTER).world_state["currency"]["player"], 6000)


class TheFirstTurns(JourneyCase):
    async def new_http_campaign(self, seed=1):
        with seeded_ids(seed):
            campaign = await self._journey_campaign({"campaign_start": START})
        self.session_id = self.last_session_id = campaign["session_id"]
        self.model = ScriptedModel()

    def world(self):
        return self.manager.get(self.session_id).game_session.world_state

    async def say(self, line):
        failures = await self._play(self.session_id, step(line), self.model)
        self.assertEqual(failures, [])
        return {"narration": self.last_narration, "action_id": self.last_turn_action_id}

    async def undo(self, action_id):
        self.last_turn_action_id = action_id
        self.assertEqual(await self._undo(self.session_id, step(undo=True), self.model), [])

    async def click_opening_event(self):
        self.assertEqual(await self._ambient(self.session_id, step(ambient={"action": "interact"}), self.model), [])
        self.assertEqual(self.last_ambient_result["status"], "APPLIED")

    async def test_the_world_comes_once_and_only_to_an_idle_player(self):
        await self.new_http_campaign(seed=1)
        for n in range(1, 8):
            self.assertNotIn(NUDGE, (await self.say(LOOK))["narration"], n)
        self.assertIn(NUDGE, (await self.say(LOOK))["narration"])
        self.assertTrue(self.world()["flags"]["opening_nudge"]["done"])
        heard = [t for t in world_threads.view(self.world())["threads"] if t["status"] == "heard"]
        self.assertEqual(len(heard), 2)
        for _ in range(3):
            self.assertNotIn(NUDGE, (await self.say(LOOK))["narration"])

    async def test_a_busy_player_gets_no_nudge(self):
        await self.new_http_campaign(seed=1)
        await self.click_opening_event()
        for _ in range(9):
            self.assertNotIn(NUDGE, (await self.say(LOOK))["narration"])
        self.assertTrue(self.world()["flags"]["opening_nudge"]["done"])

    async def test_undo_of_the_nudge_turn_brings_the_flag_back(self):
        await self.new_http_campaign(seed=1)
        for _ in range(7):
            await self.say(LOOK)
        turn = await self.say(LOOK)
        self.assertIn(NUDGE, turn["narration"])
        await self.undo(turn["action_id"])
        self.assertFalse(self.world()["flags"]["opening_nudge"]["done"])
        self.assertIn(NUDGE, (await self.say(LOOK))["narration"])

    async def test_an_old_save_without_the_nudge_never_nudges(self):
        await self.new_http_campaign(seed=1)
        self.world()["flags"].pop("opening_nudge")  # a save from before the opening wrote it
        for _ in range(10):
            self.assertNotIn(NUDGE, (await self.say(LOOK))["narration"])
        self.assertNotIn("opening_nudge", self.world()["flags"])


if __name__ == "__main__":
    unittest.main()
