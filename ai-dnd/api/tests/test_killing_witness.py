"""Whoever saw a killing answers that turn by name (Dilim 3, Task 6): they run to the way out, into the crowd
outside, or cry out where they stand; a killing inside a fight is answered when the fight ends.

The worlds are scenario 15's own street (and scenario 09b's locked cellar, 09a's inn), built through the journey
harness on the real app; no model call is answered except the scripted ones."""

from __future__ import annotations

import copy
import dataclasses
import json

from unittest.mock import patch

import bold_acts
import combat_lifecycle
import talk_mode
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedModel
from api.tests.journeys.schema import _load_step, load_scenario

CITY = "fr:city:neverwinter"
SIDE = "fr:city:neverwinter:side_street"
FERUMEL = {"id": "ferumel", "name": "Ferumel", "role": "Seyyar satıcı", "current_hp": 1, "max_hp": 8, "armor_class": 5}
ORSIK = {"id": "orsik", "name": "Orsik", "role": "Yolcu", "current_hp": 8}
GUARD = {"id": "guard", "name": "Brissa", "role": "Muhafız", "current_hp": 40, "max_hp": 40, "armor_class": 12}
BANDIT = {"role": "Bandit", "current_hp": 1, "max_hp": 8, "armor_class": 5, "hostile": True, "distance_ft": 5}
BANDITS = ({"id": "bandit_1", "name": "Haydut", **BANDIT}, {"id": "bandit_2", "name": "Kuzgun", **BANDIT})
CELLAR = {"kind": "smithy", "name": "Kilitli Mahzen", "no_exit": True}
INN = {"kind": "hall", "name": "Göl Sofrası Salonu", "scene_kind": "tavern"}
SUCCESS = {"result": "BAŞARILI", "roll": 20, "total": 25, "dc": 12}


def attack(npc_id, name):
    return {"say": f"{name}'i kılıçla öldürüyorum",
            "script": {"intent": {"intent": "attack", "action": "attack", "completion": "complete",
                                  "target": {"type": "npc", "reference": name, "npc_id": npc_id,
                                             "evidence_quote": name}}}}


def talk(npc_id, name):
    return {"say": f"{name}'e selam veriyorum",
            "script": {"intent": {"intent": "talk", "action": "talk", "completion": "complete",
                                  "target": {"type": "npc", "reference": name, "npc_id": npc_id,
                                             "evidence_quote": name}}}}


class KillingWitnessTests(JourneyCase):
    async def play(self, npcs, steps, *, place=None):
        """Scenario 15's setup with ``npcs`` (and ``place``), the raw ``steps`` played; (narrations, session)."""
        scenario = load_scenario(SCENARIO_DIR / "15_murder_consequence.json")
        setup = copy.deepcopy(scenario.setup)
        setup["npcs"] = [copy.deepcopy(npc) for npc in npcs]
        if place is not None:
            setup["place"] = dict(place)
        loaded = tuple(_load_step(raw, f"görev 6, adım {number}", False) for number, raw in enumerate(steps, 1))
        results = await self.run_scenario(dataclasses.replace(scenario, setup=setup, steps=loaded))
        self.assertEqual([failure for result in results for failure in result.failures], [])
        return [result.narration for result in results], self.manager.get(self.last_session_id).game_session

    async def more(self, raw):
        """One more turn on the live session; its narration."""
        step = _load_step(raw, "görev 6, ek adım", False)
        failures = await self._play(self.last_session_id, step, ScriptedModel())
        self.assertEqual(failures, [])
        return self.last_narration

    def npc(self, session, npc_id):
        return next(npc for npc in session.world_state["npcs"] if npc["id"] == npc_id)

    async def reloaded(self, session):
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager
        from api.tests.auth_fixture import TEST_PLAYER
        self.manager.save_campaign(self.manager.get(self.last_session_id).campaign_id)
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        session_id, *_ = fresh.resume_campaign(self.manager.get(self.last_session_id).campaign_id)
        return fresh.get(session_id).game_session

    async def test_in_the_street_the_witness_runs_into_the_crowd(self):
        (narration,), session = await self.play([FERUMEL, ORSIK], [attack("ferumel", "Ferumel")])
        self.assertIn("Orsik bağırarak kalabalığın içine koşuyor.", narration)
        self.assertNotIn("kapıya", narration)
        self.assertEqual(self.npc(session, "orsik")["location"], SIDE)

    async def test_with_no_way_out_the_witness_stays_and_cries_out(self):
        (narration,), session = await self.play([FERUMEL, ORSIK], [attack("ferumel", "Ferumel")], place=CELLAR)
        self.assertIn("Orsik geri çekilip bağırıyor; gözünü senden ayırmıyor.", narration)
        self.assertEqual(self.npc(session, "orsik")["location"], session.world_state["location"])
        self.assertIsInstance(self.npc(session, "orsik")["frightened_by_player"], int)

    async def test_in_a_closed_place_the_witness_runs_to_the_door(self):
        (narration,), session = await self.play([FERUMEL, ORSIK], [attack("ferumel", "Ferumel")], place=INN)
        self.assertIn("Orsik bağırarak kapıya koşuyor.", narration)
        self.assertNotIn("kalabalığın", narration)
        self.assertEqual(self.npc(session, "orsik")["location"], CITY)

    async def test_a_killing_inside_a_fight_is_answered_when_the_fight_ends(self):
        first, second = BANDITS
        (one, two), session = await self.play(
            [first, second, ORSIK], [attack("bandit_1", "Haydut"), attack("bandit_2", "Kuzgun")], place=INN)
        self.assertNotIn("Orsik", one)
        self.assertEqual(two.count("Orsik bağırarak kapıya koşuyor."), 1)
        self.assertNotIn("fresh_killing", session.world_state["flags"])

    async def test_the_flag_waits_while_the_fight_goes_on(self):
        _, session = await self.play([*BANDITS, ORSIK], [attack("bandit_1", "Haydut")], place=INN)
        self.assertIs(session.world_state["combat"]["active"], True)
        self.assertTrue(session.world_state["flags"].get("fresh_killing"))
        self.assertEqual(self.npc(session, "orsik")["location"], session.world_state["location"])

    async def test_the_witness_still_knows_after_reload(self):
        _, session = await self.play([FERUMEL, ORSIK], [attack("ferumel", "Ferumel")])
        again = await self.reloaded(session)
        self.assertEqual(self.npc(again, "orsik")["location"], SIDE)
        self.assertIn("kendi gözünle gördün", bold_acts.speech_note(again.world_state, self.npc(again, "orsik")))
        self.assertIn(SIDE, again.world_state["locations"])

    async def test_a_fleeing_witness_in_talk_closes_the_talk(self):
        _, session = await self.play([FERUMEL, ORSIK], [talk("orsik", "Orsik"), attack("ferumel", "Ferumel")])
        self.assertIsNone(session.world_state["flags"].get("active_npc_id"))

    async def test_an_old_save_without_the_flag_loads(self):
        _, session = await self.play([ORSIK], [])
        self.assertNotIn("fresh_killing", session.world_state["flags"])
        self.assertIsNotNone(await self.reloaded(session))

    async def test_no_side_street_is_written_when_nobody_runs(self):
        # only a guard sees it: he draws; nobody runs, so the town keeps its streets as they were
        (narration,), session = await self.play([FERUMEL, GUARD], [attack("ferumel", "Ferumel")])
        self.assertIn("silahını çekip üstüne yürüyor", narration)
        self.assertNotIn(SIDE, session.world_state["locations"])
        # and nobody saw it at all
        _, alone = await self.play([FERUMEL], [attack("ferumel", "Ferumel")])
        self.assertNotIn(SIDE, alone.world_state["locations"])

    async def test_a_guard_draws_and_the_unarmed_witness_runs(self):
        (narration,), session = await self.play([FERUMEL, GUARD, ORSIK], [attack("ferumel", "Ferumel")])
        self.assertIn("Brissa silahını çekip üstüne yürüyor", narration)
        self.assertIn("Orsik bağırarak kalabalığın içine koşuyor.", narration)
        self.assertIn(SIDE, session.world_state["locations"])

    async def test_undo_of_the_fight_end_brings_the_flag_back(self):
        first, second = BANDITS
        _, session = await self.play(
            [first, second, ORSIK], [attack("bandit_1", "Haydut"), attack("bandit_2", "Kuzgun"), {"undo": True}],
            place=INN)
        self.assertTrue(session.world_state["flags"].get("fresh_killing"))
        self.assertEqual(self.npc(session, "orsik")["location"], session.world_state["location"])
        json.dumps(session.world_state)

    async def test_a_fight_that_ends_without_a_killing_answers_the_earlier_one_once(self):
        # the first Haydut died inside the fight; the second gives up (no new killing): the answer comes then, once
        first, second = BANDITS
        (one,), session = await self.play([first, second, ORSIK], [attack("bandit_1", "Haydut")], place=INN)
        self.assertNotIn("Orsik", one)
        self.assertTrue(session.world_state["flags"].get("fresh_killing"))
        session.end_combat("enemy_fled")
        look = {"say": "etrafıma bakıyorum"}
        after = await self.more(look)
        self.assertEqual(after.count("Orsik bağırarak kapıya koşuyor."), 1)
        self.assertNotIn("fresh_killing", session.world_state["flags"])
        self.assertNotIn("Orsik", await self.more(look))

    async def test_a_witness_in_the_fight_never_opens_a_new_one(self):
        # defending against the one who attacked is no crime: the guard in the room does not draw at the fight's end
        first, second = BANDITS
        (_, end), session = await self.play(
            [first, second, GUARD, ORSIK], [attack("bandit_1", "Haydut"), attack("bandit_2", "Kuzgun")], place=INN)
        self.assertNotIn("silahını çekip", end)
        self.assertIs(session.world_state["combat"]["active"], False)
        self.assertIn("Orsik bağırarak kapıya koşuyor.", end)

    async def test_a_fight_that_ended_elsewhere_answers_nothing(self):
        # the first Haydut dies in the inn; the player slips out to the street, where a guard stands
        first, second = BANDITS
        street_guard = {**GUARD, "location": CITY}
        _, session = await self.play([first, second, ORSIK, street_guard], [attack("bandit_1", "Haydut")],
                                     place=INN)
        self.assertEqual(session.world_state["combat"]["current_actor_id"], "player")
        with patch.object(session, "perform_skill_check", create=True, return_value=dict(SUCCESS)):
            result = combat_lifecycle.flee(session)
        bold_acts.answer_to_killing(session, result)
        self.assertEqual(session.world_state["location"], CITY)
        self.assertNotIn("katil", result["narration"])
        self.assertNotIn("bağırarak", result["narration"])
        self.assertIs(session.world_state["combat"]["active"], False)
        self.assertNotIn(SIDE, session.world_state["locations"])
        self.assertNotIn("fresh_killing", session.world_state["flags"])
        self.assertNotEqual(self.npc(session, "orsik")["location"], CITY)

    async def test_a_witness_who_flees_ends_the_talk_with_the_reason(self):
        _, session = await self.play([FERUMEL, ORSIK], [talk("orsik", "Orsik")])
        world = session.world_state
        self.assertEqual(world["flags"].get("active_npc_id"), "orsik")
        victim = self.npc(session, "ferumel")
        victim.update(current_hp=0, combat_status="dead")
        bold_acts.killed(session, victim)  # a killing outside any fight
        with patch.object(talk_mode, "close", wraps=talk_mode.close) as close:
            bold_acts.answer_to_killing(session, {"narration": ""})
        close.assert_called_once_with(world, "witness_fled")
        self.assertIsNone(world["flags"].get("active_npc_id"))

    async def test_the_answer_comes_once_when_the_fight_end_is_played_again_after_undo(self):
        first, second = BANDITS
        results, _ = await self.play(
            [first, second, ORSIK],
            [attack("bandit_1", "Haydut"), attack("bandit_2", "Kuzgun"), {"undo": True}, attack("bandit_2", "Kuzgun")],
            place=INN)
        self.assertEqual(results[1].count("Orsik bağırarak kapıya koşuyor."), 1)
        self.assertEqual(results[3].count("Orsik bağırarak kapıya koşuyor."), 1)

    async def test_the_flag_survives_a_save_in_the_middle_of_the_fight(self):
        first, second = BANDITS
        results, session = await self.play(
            [first, second, ORSIK], [attack("bandit_1", "Haydut"), {"reload": True}, attack("bandit_2", "Kuzgun")],
            place=INN)
        self.assertEqual(results[2].count("Orsik bağırarak kapıya koşuyor."), 1)
        self.assertNotIn("Orsik", results[0])

    async def test_a_person_in_the_room_is_named_by_a_look(self):
        # the control for scenario 33's last step: a look names whoever is there
        _, session = await self.play([ORSIK], [], place=INN)
        self.assertIn("Orsik", await self.more({"say": "etrafıma bakıyorum"}))

    async def test_an_innocent_killed_on_the_second_turn_of_a_fight_is_still_a_crime(self):
        # the fight began on an earlier turn, but the victim never was an enemy: the guard draws
        sturdy = {**FERUMEL, "current_hp": 9}
        (one, two), session = await self.play(
            [sturdy, GUARD, ORSIK], [attack("ferumel", "Ferumel"), attack("ferumel", "Ferumel")])
        self.assertNotIn("Ferumel ölür", one)
        self.assertIn("Ferumel ölür", two)
        self.assertIn("silahını çekip üstüne yürüyor", two)
        self.assertNotIn(True, [deed.get("in_fight") for deed in session.world_state["flags"]["deeds"]
                                if deed.get("kind") == "killing"])
