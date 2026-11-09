"""The order a counter-attack is told in (Dilim 2, Task 17; item 121): an enemy who won initiative and acted before the
player's move is told before that move, without the counter-attack name; only attacks that come after the player's move
are called counter-attacks, worded as today. No real model is called."""
from __future__ import annotations

import copy
import os
from unittest.mock import patch

import front_proposal
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedModel, apply_setup
from api.tests.journeys.schema import load_scenario

# Recorded from the base commit (3dc830ec, before this task's change): scenario 22's punch turn with the player
# winning initiative. The enemy acts only after the punch, so today's words must stay byte for byte the same.
TODAY_AFTER_PLAYER = "Saldırın hedefi ıskalar. Rakibinin karşı saldırısı sana isabet eder; 1 hasar alırsın."


class CounterOrder(JourneyCase):
    maxDiff = None
    seed_where_the_player_wins_initiative = 1  # scenario 22's seed; the player's win is fixed by the initiative rolls

    async def punch_marek(self, seed, player_first=False):
        """Scenario 22's setup with the given seed; plays its punch turn and returns the turn's narration."""
        scenario = load_scenario(SCENARIO_DIR / "22_one_counter_per_move.json")
        setup = copy.deepcopy(scenario.setup)
        setup["seed"] = seed
        campaign = await self._journey_campaign(setup)
        apply_setup(self, campaign, setup)
        self.campaign_id = campaign["campaign_id"]
        self.session_id = self.last_session_id = campaign["session_id"]
        self.last_turn_action_id = None
        rolls = ((patch("game.roll_initiative_player", return_value=20), patch("game.roll_initiative", return_value=1))
                 if player_first else ())
        with patch.dict(os.environ, {front_proposal.FLAG: "0"}):
            for roll in rolls:
                roll.start()
            try:
                failures = await self._play(self.session_id, scenario.steps[0], ScriptedModel())
            finally:
                for roll in rolls:
                    roll.stop()
        self.assertEqual(failures, [])
        return self.last_narration

    async def test_an_enemy_who_won_initiative_is_told_before_the_punch(self):
        text = await self.punch_marek(seed=1)
        self.assertLess(text.index("senden önce davranıp"), text.index("Saldırın"))
        self.assertEqual(text.count("karşı saldırısı"), 1)

    async def test_one_enemy_after_the_player_keeps_todays_words(self):
        before = TODAY_AFTER_PLAYER  # recorded from the base commit
        self.assertEqual(await self.punch_marek(seed=self.seed_where_the_player_wins_initiative, player_first=True),
                         before)
        self.assertNotIn("senden önce davranıp", before)
        self.assertEqual(before.count("karşı saldırısı"), 1)
