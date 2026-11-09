"""Walking toward an enemy in a fight (Dilim 2, Task 16; item 40): it is combat movement that Python measures (the
distance less 5 feet, held to the movement left), two enemies and no named one get a which-one question, and only
walking somewhere that is not in the fight is still refused as travel. No real model is called."""
from __future__ import annotations

import copy
import os
from unittest.mock import patch

import action_economy
import combat_lifecycle
import front_proposal
import refusals
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedModel, apply_setup
from api.tests.journeys.schema import Step, load_scenario

_TO_THE_ARCHER = {"intent": "travel", "action": "approach",
                  "target": {"type": "npc", "reference": "okçu", "npc_id": "archer", "evidence_quote": "okçuya"}}
_TO_THE_RIVAL = {"intent": "travel",
                 "target": {"type": "npc", "reference": "rakip", "npc_id": "", "evidence_quote": "rakibin"}}


class CombatApproach(JourneyCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.setup = copy.deepcopy(load_scenario(SCENARIO_DIR / "06_combat_actions.json").setup)
        campaign = await self._journey_campaign(self.setup)
        apply_setup(self, campaign, self.setup)
        self.campaign_id = campaign["campaign_id"]
        self.session_id = self.last_session_id = campaign["session_id"]
        self.last_turn_action_id = None
        self._before = copy.deepcopy((self.session.world_state, self.session.character))

    @property
    def session(self):
        return self.manager.get(self.session_id).game_session

    def fight(self, enemies, speed):
        """Scenario 06's setup, only the named enemies, each at the given feet; the fight starts on the player's turn."""
        world, character = copy.deepcopy(self._before)
        self.session.world_state.clear()
        self.session.world_state.update(world)
        self.session.character.clear()
        self.session.character.update(character, speed_ft=speed)
        npcs = [npc for npc in self.session.world_state["npcs"] if npc["id"] in enemies]
        for npc in npcs:
            npc["distance_ft"] = enemies[npc["id"]]
        self.session.world_state["npcs"] = npcs
        with patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1):
            self.session.start_combat(npcs[0])
        self.assertEqual(self.session.world_state["combat"]["current_actor_id"], "player")
        self.manager.save_campaign(self.campaign_id)
        return self.session

    def used(self):
        return action_economy.ensure(self.session)["player"]["movement_used"]

    def distance(self, identity):
        return next(npc for npc in self.session.world_state["npcs"] if npc["id"] == identity)["distance_ft"]

    def notes(self):
        return [text for _, text in getattr(self.session, "_turn_notes", None) or []]

    async def say(self, line, intent=None, front=None):
        script = {key: value for key, value in (("intent", intent), ("front", front)) if value}
        step = Step(say=line, command=None, economic_action=None, combat_action=None, script=script or None,
                    expect={}, known_broken=(), real_chain=False, independent=True)
        with patch.dict(os.environ, {front_proposal.FLAG: "1" if front else "0"}):
            failures = await self._play(self.session_id, step, ScriptedModel())
        self.assertEqual(failures, [])
        return self.last_narration

    # --- Step 1 of the plan ---------------------------------------------------------------------------------------
    def test_the_approach_decision(self):
        s = self.fight(enemies={"bandit": 5, "archer": 30}, speed=30)
        r = combat_lifecycle.approach(s, "archer", named=True)
        self.assertEqual((r.status, r.moved_ft, r.left_ft, r.target_id), ("moved", 25, 5, "archer"))
        s = self.fight(enemies={"bandit": 5, "archer": 30}, speed=30)
        r = combat_lifecycle.approach(s, None, named=True)
        self.assertEqual((r.status, r.moved_ft, r.names), ("which", 0, ("Haydut", "Okçu")))
        s = self.fight(enemies={"bandit": 5, "archer": 30}, speed=30)
        self.assertEqual(combat_lifecycle.approach(s, "door", named=True).status, "not_a_participant")

    async def test_approaching_the_archer_moves_25_feet(self):
        self.fight(enemies={"bandit": 5, "archer": 30}, speed=30)
        await self.say("okçuya yaklaşıyorum", intent=_TO_THE_ARCHER)
        self.assertEqual((self.used(), self.distance("archer")), (25, 5))
        self.assertEqual(self.distance("bandit"), 5)                     # nobody else is moved

    async def test_two_enemies_and_no_target_asks_which(self):
        self.fight(enemies={"bandit": 5, "archer": 30}, speed=30)
        text = await self.say("rakibin yanına gidiyorum", intent=_TO_THE_RIVAL)
        self.assertEqual(self.used(), 0)
        self.assertEqual((self.distance("bandit"), self.distance("archer")), (5, 30))
        self.assertTrue(text.startswith("Hangisine yaklaşıyorsun:"), text)
        self.assertEqual(text, refusals.text_for("which_enemy", names="Haydut mu, Okçu mu"))
        self.assertNotIn("yürüyüp gidemezsin", text)

    async def test_one_enemy_and_no_target_goes_to_it(self):
        self.fight(enemies={"archer": 30}, speed=30)
        await self.say("rakibin yanına gidiyorum", intent=_TO_THE_RIVAL)
        self.assertEqual((self.used(), self.distance("archer")), (25, 5))

    async def test_not_enough_movement_goes_as_far_as_it_can(self):
        self.fight(enemies={"archer": 60}, speed=30)
        text = await self.say("okçuya yaklaşıyorum", intent=_TO_THE_ARCHER)
        self.assertEqual((self.used(), self.distance("archer")), (30, 30))
        self.assertIn("25", text)                                         # how far is left to reach it (55 needed − 30)
        self.assertEqual(text, refusals.text_for("approach_short", left=25))
        self.assertIn("olmadı: " + refusals.text_for("approach_short", left=25), self.notes())

    async def test_walking_to_the_door_is_still_combat_travel(self):
        self.fight(enemies={"bandit": 5}, speed=30)
        text = await self.say("kapıya yürüyorum", intent={"intent": "travel", "target": {"type": "location", "reference": "kapı"}})
        self.assertEqual(self.used(), 0)
        self.assertEqual(text, refusals.REFUSAL_TEXT["combat_travel"])

    # --- the movement rules stay the fight's own ------------------------------------------------------------------
    async def test_a_prone_player_crawls_at_double_cost(self):
        self.fight(enemies={"archer": 30}, speed=30)
        self.session.character["conditions"] = [*self.session.character.get("conditions", []), "prone"]
        self.manager.save_campaign(self.campaign_id)
        text = await self.say("okçuya yaklaşıyorum", intent=_TO_THE_ARCHER)
        self.assertEqual((self.used(), self.distance("archer")), (30, 15))   # 15 feet crawled cost all 30 of Speed
        self.assertEqual(text, refusals.text_for("approach_short", left=10))

    async def test_movement_already_spent_is_not_given_back(self):
        self.fight(enemies={"archer": 30}, speed=30)
        action_economy.move(self.session, "player", 20)
        self.manager.save_campaign(self.campaign_id)
        await self.say("okçuya yaklaşıyorum", intent=_TO_THE_ARCHER)
        self.assertEqual((self.used(), self.distance("archer")), (30, 20))

    async def test_the_front_reading_go_to_a_participant_is_an_approach(self):
        self.fight(enemies={"bandit": 5, "archer": 30}, speed=30)
        await self.say("okçuya doğru koşuyorum", intent={"intent": "narrative"},
                       front={"kind": "go_to", "person_id": "archer"})
        self.assertEqual((self.used(), self.distance("archer")), (25, 5))

    # --- save and Undo --------------------------------------------------------------------------------------------
    async def test_undo_takes_the_approach_back_and_a_save_keeps_it(self):
        self.fight(enemies={"bandit": 5, "archer": 30}, speed=30)
        await self.say("okçuya yaklaşıyorum", intent=_TO_THE_ARCHER)
        self.assertEqual((self.used(), self.distance("archer")), (25, 5))
        step = Step(say=None, command=None, economic_action=None, combat_action=None, script=None, expect={},
                    known_broken=(), real_chain=False, independent=True, undo=True)
        self.assertEqual(await self._undo(self.session_id, step, ScriptedModel()), [])
        self.assertEqual((self.used(), self.distance("archer")), (0, 30))
        await self.say("okçuya yaklaşıyorum", intent=_TO_THE_ARCHER)
        step = Step(say=None, command=None, economic_action=None, combat_action=None, script=None, expect={},
                    known_broken=(), real_chain=False, independent=True, reload=True)
        failures, _ = await self._reload(self.session_id, step, ScriptedModel())   # live and saved compared key by key
        self.assertEqual(failures, [])
        self.session_id = self.last_session_id
        self.assertEqual((self.used(), self.distance("archer")), (25, 5))


if __name__ == "__main__":
    import unittest
    unittest.main()
