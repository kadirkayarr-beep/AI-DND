"""Whoever saw a killing answers that turn by name (Dilim 3, Task 6): they run to the way out, into the crowd
outside, or cry out where they stand; a killing inside a fight is answered when the fight ends.

The worlds are scenario 15's own street (and scenario 09b's locked cellar, 09a's inn), built through the journey
harness on the real app; no model call is answered except the scripted ones."""

from __future__ import annotations

import copy
import dataclasses
import json

import bold_acts
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase
from api.tests.journeys.schema import _load_step, load_scenario

CITY = "fr:city:neverwinter"
SIDE = "fr:city:neverwinter:side_street"
FERUMEL = {"id": "ferumel", "name": "Ferumel", "role": "Seyyar satıcı", "current_hp": 1, "max_hp": 8, "armor_class": 5}
ORSIK = {"id": "orsik", "name": "Orsik", "role": "Yolcu", "current_hp": 8}
GUARD = {"id": "guard", "name": "Brissa", "role": "Muhafız", "current_hp": 40, "max_hp": 40, "armor_class": 12}
BANDIT = {"role": "Bandit", "current_hp": 1, "max_hp": 8, "armor_class": 5, "hostile": True, "distance_ft": 5}
BANDITS = ({"id": "bandit_1", "name": "Haydut", **BANDIT}, {"id": "bandit_2", "name": "Kuzgun", **BANDIT})
CELLAR = {"kind": "smithy", "name": "Kilitli Mahzen", "no_exit": True}
INN = {"kind": "smithy", "name": "Göl Sofrası Hanı", "scene_kind": "tavern", "place_kind": "tavern"}


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
        self.assertIs(session.world_state["flags"].get("fresh_killing"), True)
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
        self.assertIs(session.world_state["flags"].get("fresh_killing"), True)
        self.assertEqual(self.npc(session, "orsik")["location"], session.world_state["location"])
        json.dumps(session.world_state)
